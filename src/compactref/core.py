from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from hashlib import blake2b
from math import ceil, exp, log, log10, sqrt
from typing import TypeAlias
from uuid import UUID
from warnings import warn


SourceIdentifier: TypeAlias = str | bytes | int | UUID

DEFAULT_SUFFIX_LENGTH = 6
DEFAULT_DATE_FORMAT = "%Y%m%d"

# The date part is a bucket label, and every caller has to agree on which
# bucket an instant falls in. UTC is the only default that does not depend
# on which machine happened to run the code.
DEFAULT_TIMEZONE: tzinfo = timezone.utc

# blake2b takes at most 16 bytes of salt, which is where the attempt goes.
MAX_ATTEMPT = 2**128 - 1


def generate_reference(
    source: SourceIdentifier,
    *,
    generated_at: datetime | None = None,
    tz: tzinfo = DEFAULT_TIMEZONE,
    suffix_length: int = DEFAULT_SUFFIX_LENGTH,
    date_format: str = DEFAULT_DATE_FORMAT,
    prefix: str = "",
    separator: str = "",
    attempt: int = 0,
) -> str:
    """
    Generate a compact human-facing reference from a stable identifier.

    The same source, date, attempt and configuration always produce the
    same reference — on every machine. The system timezone is never
    consulted.

    Args:
        source:
            Stable internal identifier. It can be a ULID string, UUID,
            integer or bytes.

        generated_at:
            The instant the date portion describes. Defaults to now, read
            in ``tz``.

            An aware datetime is converted into ``tz`` first, so callers
            in different places agree on which bucket an instant falls in.
            A naive datetime is taken at face value, as already being in
            ``tz``: it is a wall clock the caller chose, and this function
            will not guess at what it meant.

        tz:
            The timezone the date portion is expressed in. Defaults to
            UTC.

            This exists because the date is a *bucket label*, and every
            caller has to agree on which bucket an instant belongs to.
            Before 0.3.0 the default clock was ``datetime.now()``, whose
            naive local time made the reference depend on the machine that
            produced it: the same identifier at the same instant became
            20260713… in Lima and 20260714… in Tokyo. Determinism is the
            point of this library, so nothing here reads the environment
            any more.

            Pass a zone if the bucket should follow a business day rather
            than UTC — a shop that closes at midnight in Madrid wants
            ``ZoneInfo("Europe/Madrid")``, so an order taken at 23:50 is
            filed on the day the shop counts it.

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
        See collision_probability() and expected_rejected_inserts().
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if attempt < 0:
        raise ValueError("attempt must not be negative")
    if attempt > MAX_ATTEMPT:
        raise ValueError(f"attempt must not be greater than {MAX_ATTEMPT}")

    source_bytes = _normalize_source(source)

    date_part = _resolve_moment(generated_at, tz).strftime(date_format)

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


def expected_colliding_pairs(
    reference_count: int,
    suffix_length: int,
) -> float:
    """
    Approximate the number of *colliding pairs* among ``reference_count``
    references, within a single date and prefix bucket.

    A pair is two references that share a suffix.

    collision_probability() answers whether anything collides at all. It
    saturates: once a format is crowded, every volume reports "almost
    certainly", which stops distinguishing a format that collides twice
    a month from one that collides fifty times. This distinguishes them,
    which is what sizes a suffix.

    It is *not* the number of rejected inserts, and not the number of
    ``attempt`` retries a caller needs — for that, see
    expected_rejected_inserts(). A suffix drawn ``k`` times is
    ``k * (k - 1) / 2`` pairs but only ``k - 1`` rejected inserts, so the
    two agree while a bucket is sparse and part company once it fills:

        >>> expected_colliding_pairs(2_000, suffix_length=3)
        1999.0
        >>> expected_rejected_inserts(2_000, suffix_length=3)
        1135.2...

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


def expected_rejected_inserts(
    reference_count: int,
    suffix_length: int,
) -> float:
    """
    Approximate how many of ``reference_count`` inserts a unique
    constraint rejects, within a single date and prefix bucket.

    This is the number a caller acts on: each rejection is one reference
    that has to be regenerated with a higher ``attempt``, so it is the
    size of the retry budget.

    Every reference lands in one of ``space = 10 ** suffix_length``
    suffixes. After ``n`` of them, the expected number of *distinct*
    suffixes taken is ``space * (1 - (1 - 1 / space) ** n)``, and every
    reference that did not take a fresh suffix was a rejected insert:

        rejected = n - space * (1 - (1 - 1 / space) ** n)

    Unlike expected_colliding_pairs(), this does not run away as a bucket
    fills — it cannot exceed ``n``, because an insert can only be rejected
    once.

        >>> expected_rejected_inserts(30, suffix_length=3)
        0.4...
        >>> expected_rejected_inserts(2_000, suffix_length=3)
        1135.2...
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if reference_count < 0:
        raise ValueError("reference_count must not be negative")
    if reference_count < 2:
        return 0.0

    space: int = 10**suffix_length
    taken = space * (1.0 - (1.0 - 1.0 / space) ** reference_count)
    return reference_count - taken


def expected_collisions(reference_count: int, suffix_length: int) -> float:
    """
    Deprecated alias for expected_colliding_pairs().

    The old name suggested a count of collisions a caller would have to
    handle, and the documentation said as much. It is not: it counts
    pairs, which runs far ahead of the rejected inserts once a bucket
    fills. Use expected_colliding_pairs() to size a format, or
    expected_rejected_inserts() to size a retry budget.
    """
    warn(
        "expected_collisions() is deprecated and will be removed in 1.0.0. "
        "It returns colliding pairs, not rejected inserts: use "
        "expected_colliding_pairs() to measure how crowded a format is, or "
        "expected_rejected_inserts() for the number of retries a unique "
        "constraint will actually cause.",
        DeprecationWarning,
        stacklevel=2,
    )
    return expected_colliding_pairs(reference_count, suffix_length)


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


def suffix_length_for(
    reference_count: int,
    max_probability: float = 0.01,
) -> int:
    """
    Smallest suffix length that keeps ``reference_count`` references in
    one bucket at or below ``max_probability`` (default 1%).

    max_references() answers this backwards — it takes a length and
    returns a volume — so a caller who knows their volume and wants a
    length had to sweep. This is the direction people actually ask in.

        >>> suffix_length_for(200)
        7

    The count is *per bucket*, and ``date_format`` decides the bucket. A
    daily format wants references per day; a monthly one wants references
    per month, which is roughly thirty times as many and needs a longer
    suffix, not a shorter one. Getting that backwards is the most common
    way to size a reference badly.
    """
    if reference_count < 0:
        raise ValueError("reference_count must not be negative")
    if not 0.0 < max_probability < 1.0:
        raise ValueError("max_probability must be between 0 and 1")
    if reference_count < 2:
        return 1

    # Invert the birthday approximation for the space:
    #   p = 1 - exp(-n(n-1) / 2s)  =>  s >= n(n-1) / (-2 ln(1 - p))
    space = (
        reference_count
        * (reference_count - 1)
        / (-2 * log(1 - max_probability))
    )
    return max(1, ceil(log10(space)))


def _resolve_moment(generated_at: datetime | None, tz: tzinfo) -> datetime:
    """
    Decide which instant the date portion describes.

    The system timezone is deliberately not reachable from here. Reading it
    is what made a reference depend on the machine that produced it, and a
    reference that depends on the machine is not deterministic.
    """
    if generated_at is None:
        # datetime.now(tz), never datetime.now(). The bare call returns
        # naive local time, which is the whole bug.
        return datetime.now(tz)

    if generated_at.tzinfo is None:
        # A wall clock the caller chose. Take it as already being in tz
        # rather than guessing; guessing is what we are here to stop.
        return generated_at

    return generated_at.astimezone(tz)


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
