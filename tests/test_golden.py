"""Golden references. These strings are the 1.0.0 promise.

Every value here is in somebody's database. If a test in this file fails,
the library has changed what it produces, and the change is a 2.0 whether
or not any Python signature moved — the callers whose references stopped
resolving will not care that the type hints held.

That makes this file different in kind from the rest of the suite. The
others check that the code is right. These check that it has not *moved*,
which is a separate promise and the one people actually depend on.

What is frozen, and what would break it:

- The hash: BLAKE2b, digest_size=16, person=b"compactref-v1". Changing the
  algorithm, the digest size, or the personalisation moves every reference.
- The attempt: BLAKE2b's salt, sixteen big-endian bytes. Moving it into the
  message, or changing the width, moves every retried reference.
- The namespace: BLAKE2b's key. Same.
- Integer sources: big-endian, minimum width. Strings: UTF-8 of the stripped
  value. UUIDs: their sixteen bytes. Any of these is a wire format.
- The suffix: the digest read big-endian, taken modulo base ** length, and
  rendered in the alphabet from the most significant character.
- The check character: Luhn mod N over the alphabet, computed on
  date_part + suffix, appended to the suffix.

Everything below was produced by the library, not by hand.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from compactref import (
    CROCKFORD_BASE32,
    DIGITS,
    CompactRef,
    SourceIdentifier,
    generate_reference,
)


# Fixed, and aware. A naive value would let a machine's timezone leak into
# the expected strings, which is the bug 0.3.0 exists to prevent.
AT = datetime(2026, 7, 10, 12, 30, tzinfo=timezone.utc)

ULID = "01J2H8NQPG6B5X8KGN97SX3R5C"


# --------------------------------------------------------------------------
# Every kind of source. How an identifier becomes bytes is a wire format.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (ULID, "20260710385177"),
        (UUID("b37fd04a-10b7-47b8-a5fe-76e3e615f441"), "20260710893023"),
        (b"internal-record-123", "20260710016594"),
        (123456789, "20260710284854"),
        (0, "20260710523465"),
        # UTF-8, not latin-1 and not the platform's default encoding.
        ("órden-ñ-42", "20260710800921"),
    ],
)
def test_a_source_still_hashes_to_the_reference_it_always_did(
    source: SourceIdentifier,
    expected: str,
) -> None:
    assert generate_reference(source, generated_at=AT) == expected


# --------------------------------------------------------------------------
# attempt — BLAKE2b's salt, sixteen big-endian bytes.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [
        (0, "20260710385177"),  # must equal the unsalted digest, forever
        (1, "20260710210736"),
        (2, "20260710342336"),
        (7, "20260710277898"),
        (99, "20260710445670"),
    ],
)
def test_an_attempt_still_derives_the_reference_it_always_did(
    attempt: int,
    expected: str,
) -> None:
    assert generate_reference(ULID, generated_at=AT, attempt=attempt) == (
        expected
    )


# --------------------------------------------------------------------------
# namespace — BLAKE2b's key.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("namespace", "expected"),
    [
        ("", "20260710385177"),  # an empty key is no key: the 0.1.0 value
        ("orders", "20260710379700"),
        ("invoices", "20260710916090"),
        ("órdenes", "20260710513265"),  # UTF-8 again
    ],
)
def test_a_namespace_still_derives_the_reference_it_always_did(
    namespace: str,
    expected: str,
) -> None:
    assert generate_reference(ULID, generated_at=AT, namespace=namespace) == (
        expected
    )


# --------------------------------------------------------------------------
# alphabet — the digest read big-endian, modulo base ** length, rendered
# from the most significant character.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alphabet", "expected"),
    [
        (DIGITS, "20260710385177"),
        (CROCKFORD_BASE32, "20260710HCP3CS"),
    ],
)
def test_an_alphabet_still_encodes_the_way_it_always_did(
    alphabet: str,
    expected: str,
) -> None:
    assert generate_reference(ULID, generated_at=AT, alphabet=alphabet) == (
        expected
    )


# --------------------------------------------------------------------------
# check — Luhn mod N over the alphabet, on date_part + suffix.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scheme", "expected"),
    [
        (CompactRef(check=True), "202607103851778"),
        (
            CompactRef(alphabet=CROCKFORD_BASE32, check=True),
            "20260710HCP3CSX",
        ),
        (
            CompactRef(prefix="ORD", separator="-", check=True),
            "ORD-20260710-3851778",
        ),
    ],
)
def test_a_check_character_is_still_the_one_it_always_was(
    scheme: CompactRef,
    expected: str,
) -> None:
    reference = scheme.generate(ULID, generated_at=AT)

    assert reference == expected
    assert scheme.verify(reference)


# --------------------------------------------------------------------------
# tz — the bucket an instant falls in.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tz", "expected"),
    [
        # 23:30 UTC is already tomorrow in Tokyo, and still today in Lima.
        (timezone.utc, "20260713385177"),
        (ZoneInfo("America/Lima"), "20260713385177"),
        (ZoneInfo("Asia/Tokyo"), "20260714385177"),
    ],
)
def test_a_timezone_still_buckets_the_way_it_always_did(
    tz: timezone | ZoneInfo,
    expected: str,
) -> None:
    instant = datetime(2026, 7, 13, 23, 30, tzinfo=timezone.utc)

    assert generate_reference(ULID, generated_at=instant, tz=tz) == expected


# --------------------------------------------------------------------------
# The whole thing at once, as a caller would actually configure it.
# --------------------------------------------------------------------------


def test_a_fully_configured_scheme_is_still_itself() -> None:
    orders = CompactRef(
        prefix="ORD",
        separator="-",
        alphabet=CROCKFORD_BASE32,
        namespace="orders",
        suffix_length=6,
        check=True,
    )

    reference = orders.generate(ULID, generated_at=AT, attempt=2)

    assert reference == "ORD-20260710-DTCJHY0"
    assert orders.verify(reference)
    assert orders.reference_length == len(reference)


# --------------------------------------------------------------------------
# The public surface. 1.0.0 promises these names, and only these.
# --------------------------------------------------------------------------


def test_the_public_api_is_exactly_this() -> None:
    """Adding a name is a minor version. Removing one is a major version.

    Pinned so neither happens by accident — an export slipped in during a
    refactor is a name we are then obliged to keep.
    """
    import compactref

    assert set(compactref.__all__) == {
        # Types
        "CompactRef",
        "ParsedReference",
        "SourceIdentifier",
        # Exceptions
        "InvalidReferenceError",
        # Alphabets
        "CROCKFORD_BASE32",
        "DIGITS",
        # Defaults
        "DEFAULT_ALPHABET",
        "DEFAULT_DATE_FORMAT",
        "DEFAULT_SUFFIX_LENGTH",
        "DEFAULT_TIMEZONE",
        # Limits
        "MAX_ATTEMPT",
        "MAX_NAMESPACE_BYTES",
        # The primitive
        "generate_reference",
        # Sizing
        "collision_probability",
        "expected_colliding_pairs",
        "expected_rejected_inserts",
        "max_references",
        "suffix_length_for",
    }

    # Every promised name is importable, not merely listed.
    for name in compactref.__all__:
        assert hasattr(compactref, name), f"{name} is in __all__ but absent"


def test_the_defaults_are_the_ones_that_were_promised() -> None:
    """Changing any of these moves every reference a caller has not pinned."""
    from compactref import (
        DEFAULT_ALPHABET,
        DEFAULT_DATE_FORMAT,
        DEFAULT_SUFFIX_LENGTH,
        DEFAULT_TIMEZONE,
        DIGITS,
    )

    assert DEFAULT_ALPHABET == DIGITS == "0123456789"
    assert DEFAULT_SUFFIX_LENGTH == 6
    assert DEFAULT_DATE_FORMAT == "%Y%m%d"
    assert DEFAULT_TIMEZONE is timezone.utc
