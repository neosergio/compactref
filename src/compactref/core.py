from __future__ import annotations

from datetime import datetime
from hashlib import blake2b
from math import exp, log, sqrt
from typing import TypeAlias
from uuid import UUID


SourceIdentifier: TypeAlias = str | bytes | int | UUID

DEFAULT_SUFFIX_LENGTH = 6
DEFAULT_DATE_FORMAT = "%Y%m%d"

# blake2b takes at most 16 bytes of salt, which is where the attempt goes.
MAX_ATTEMPT = 2**128 - 1


def generate_reference(
    source: SourceIdentifier,
    *,
    generated_at: datetime | None = None,
    suffix_length: int = DEFAULT_SUFFIX_LENGTH,
    date_format: str = DEFAULT_DATE_FORMAT,
    prefix: str = "",
    separator: str = "",
    attempt: int = 0,
) -> str:
    """
    Generate a compact human-facing reference from a stable identifier.

    The same source, date, attempt and configuration always produce the
    same reference.

    Args:
        source:
            Stable internal identifier. It can be a ULID string, UUID,
            integer or bytes.

        generated_at:
            Date and time used to create the date portion. Defaults to
            the current local date and time.

        suffix_length:
            Number of decimal digits used after the date.

        date_format:
            Format passed to datetime.strftime(). Defaults to YYYYMMDD.

        prefix:
            Optional value placed before the date.

        separator:
            Optional value placed between the prefix, date and suffix.

        attempt:
            Which reference to derive for this source. Because the
            suffix is derived from the source, the same source always
            yields the same reference, and retrying a rejected one is
            pointless. Raising the attempt derives a different reference
            from the same source, so a caller whose unique constraint
            rejected attempt 0 can offer attempt 1, and so on. Every
            attempt is itself deterministic, so a reference can be
            recomputed later from the source and the attempt that won.

    Returns:
        A compact reference such as ``20260710482731`` or
        ``INC-20260710-482731``.

    Raises:
        TypeError:
            If source has an unsupported type, including bool. A type
            checker will not catch that one: bool subclasses int, so the
            annotation admits True, and Python has no way to spell "int
            but not bool". The check is made at runtime instead, because
            True would otherwise return the reference belonging to 1.

        ValueError:
            If source is empty, suffix_length is less than one, or
            attempt is negative or larger than MAX_ATTEMPT.

    Warning:
        Shortening an identifier reduces its uniqueness space. This
        function does not mathematically guarantee that two different
        source identifiers cannot produce the same compact reference.
        See collision_probability() and expected_collisions().
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if attempt < 0:
        raise ValueError("attempt must not be negative")
    if attempt > MAX_ATTEMPT:
        raise ValueError(f"attempt must not be greater than {MAX_ATTEMPT}")

    source_bytes = _normalize_source(source)

    current_datetime = generated_at or datetime.now()
    date_part = current_datetime.strftime(date_format)

    numeric_value = _source_to_integer(source_bytes, attempt)
    numeric_suffix = numeric_value % (10**suffix_length)
    suffix = f"{numeric_suffix:0{suffix_length}d}"

    parts = [part for part in (prefix, date_part, suffix) if part]

    return separator.join(parts)


def collision_probability(reference_count: int, suffix_length: int) -> float:
    """
    Approximate the probability that at least two of ``reference_count``
    references share the same numeric suffix, within a single date and
    prefix bucket.

    Uses the standard birthday-collision approximation over a space of
    ``10 ** suffix_length`` possible suffixes.
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if reference_count < 0:
        raise ValueError("reference_count must not be negative")
    if reference_count < 2:
        return 0.0

    space = 10**suffix_length
    exponent = -reference_count * (reference_count - 1) / (2 * space)
    return 1.0 - exp(exponent)


def expected_collisions(reference_count: int, suffix_length: int) -> float:
    """
    Approximate the number of *colliding pairs* among ``reference_count``
    references, within a single date and prefix bucket.

    A pair is two references that share a suffix. This is the quantity
    ``n * (n - 1) / (2 * space)`` counts, and it is what the function
    returns.

    collision_probability() answers whether anything collides at all. It
    saturates: once a format is crowded, every volume reports "almost
    certainly", which stops distinguishing a format that collides twice
    a month from one that collides fifty times. This distinguishes them.

    It is *not* the number of rejected inserts, and not the number of
    ``attempt`` retries a caller needs. A suffix drawn ``k`` times is
    ``k * (k - 1) / 2`` pairs but only ``k - 1`` rejected inserts, so the
    two agree only while a bucket is sparse and diverge sharply once it
    fills. Two thousand references over three digits is 1999 pairs and
    about 1135 rejected inserts:

        >>> expected_collisions(2_000, suffix_length=3)
        1999.0

    Read it as a measure of how crowded a format is, not as a count of
    the work a caller will do.
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if reference_count < 0:
        raise ValueError("reference_count must not be negative")
    if reference_count < 2:
        return 0.0

    space: int = 10**suffix_length
    return reference_count * (reference_count - 1) / (2 * space)


def max_references(suffix_length: int, max_probability: float = 0.01) -> int:
    """
    Largest number of references that keeps the collision probability at
    or below ``max_probability`` (default 1%) within one date and prefix
    bucket.
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if not 0.0 < max_probability < 1.0:
        raise ValueError("max_probability must be between 0 and 1")

    space = 10**suffix_length
    # Invert the birthday approximation:
    # n ~= 0.5 + sqrt(0.25 - 2 * space * ln(1 - p))
    n = 0.5 + sqrt(0.25 - 2 * space * log(1 - max_probability))
    return max(1, int(n))


def _normalize_source(source: SourceIdentifier) -> bytes:
    """
    Convert a supported source identifier into a stable bytes value.
    """
    # bool is a subclass of int, so True would otherwise reach the integer
    # branch and quietly produce the reference for 1, and False the one for
    # 0. A boolean is never an identifier; catching it here says so rather
    # than issuing a reference that belongs to some other record.
    if isinstance(source, bool):
        raise TypeError(
            "source must be a string, bytes, non-negative integer, or UUID"
        )

    if isinstance(source, UUID):
        return source.bytes

    if isinstance(source, bytes):
        if not source:
            raise ValueError("source must not be empty")

        return source

    if isinstance(source, str):
        normalized_source = source.strip()

        if not normalized_source:
            raise ValueError("source must not be empty")

        return normalized_source.encode("utf-8")

    if isinstance(source, int):
        if source < 0:
            raise ValueError("integer source must not be negative")

        byte_length = max(1, (source.bit_length() + 7) // 8)
        return source.to_bytes(byte_length, byteorder="big")

    raise TypeError(
        "source must be a string, bytes, non-negative integer, or UUID"
    )


def _source_to_integer(source: bytes, attempt: int = 0) -> int:
    """
    Convert normalized bytes into a deterministic integer.

    BLAKE2b is used so identifiers of different formats are processed
    consistently.

    The attempt goes in the salt rather than into the message. Appending
    it to the source would make generate_reference(b"abc", attempt=1)
    and generate_reference(b"abc#1") agree, inventing a fresh class of
    collision inside the feature meant to resolve them. The salt is a
    separate input to the compression function, so the attempts of one
    source cannot be spelled as the source of another.

    An attempt of 0 salts with sixteen zero bytes, which BLAKE2b treats
    exactly as the unsalted digest it computed before this parameter
    existed. References written by earlier versions therefore still
    recompute to the same value.
    """
    digest = blake2b(
        source,
        digest_size=16,
        person=b"compactref-v1",
        salt=attempt.to_bytes(16, byteorder="big"),
    ).digest()

    return int.from_bytes(digest, byteorder="big")
