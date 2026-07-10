from __future__ import annotations

from datetime import datetime
from hashlib import blake2b
from math import exp, log, sqrt
from typing import TypeAlias
from uuid import UUID


SourceIdentifier: TypeAlias = str | bytes | int | UUID

DEFAULT_SUFFIX_LENGTH = 6
DEFAULT_DATE_FORMAT = "%Y%m%d"


def generate_reference(
    source: SourceIdentifier,
    *,
    generated_at: datetime | None = None,
    suffix_length: int = DEFAULT_SUFFIX_LENGTH,
    date_format: str = DEFAULT_DATE_FORMAT,
    prefix: str = "",
    separator: str = "",
) -> str:
    """
    Generate a compact human-facing reference from a stable identifier.

    The same source, date and configuration always produce the same
    reference.

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

    Returns:
        A compact reference such as ``20260710482731`` or
        ``INC-20260710-482731``.

    Raises:
        TypeError:
            If source has an unsupported type.

        ValueError:
            If source is empty or suffix_length is less than one.

    Warning:
        Shortening an identifier reduces its uniqueness space. This
        function does not mathematically guarantee that two different
        source identifiers cannot produce the same compact reference.
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")

    source_bytes = _normalize_source(source)

    current_datetime = generated_at or datetime.now()
    date_part = current_datetime.strftime(date_format)

    numeric_value = _source_to_integer(source_bytes)
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


def _source_to_integer(source: bytes) -> int:
    """
    Convert normalized bytes into a deterministic integer.

    BLAKE2b is used so identifiers of different formats are processed
    consistently.
    """
    digest = blake2b(
        source,
        digest_size=16,
        person=b"compactref-v1",
    ).digest()

    return int.from_bytes(digest, byteorder="big")
