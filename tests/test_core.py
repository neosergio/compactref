import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from compactref import (
    CROCKFORD_BASE32,
    DEFAULT_ALPHABET,
    DEFAULT_TIMEZONE,
    DIGITS,
    MAX_ATTEMPT,
    MAX_NAMESPACE_BYTES,
    SourceIdentifier,
    collision_probability,
    expected_colliding_pairs,
    expected_collisions,
    expected_rejected_inserts,
    generate_reference,
    max_references,
    suffix_length_for,
    verify_reference,
)


FIXED_DATETIME = datetime(2026, 7, 10, 12, 30)
FIXED_ULID = "01J2H8NQPG6B5X8KGN97SX3R5C"
FIXED_UUID = UUID("b37fd04a-10b7-47b8-a5fe-76e3e615f441")


def test_generates_numeric_reference_from_ulid() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
    )

    assert reference.startswith("20260710")
    assert len(reference) == 14
    assert reference.isdigit()


def test_same_input_produces_same_reference() -> None:
    first_reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
    )

    second_reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
    )

    assert first_reference == second_reference


def test_different_sources_usually_produce_different_references() -> None:
    first_reference = generate_reference(
        "01J2H8NQPG6B5X8KGN97SX3R5C",
        generated_at=FIXED_DATETIME,
    )

    second_reference = generate_reference(
        "01J2H8NQPG6B5X8KGN97SX3R5D",
        generated_at=FIXED_DATETIME,
    )

    assert first_reference != second_reference


def test_accepts_uuid() -> None:
    reference = generate_reference(
        FIXED_UUID,
        generated_at=FIXED_DATETIME,
    )

    assert reference.startswith("20260710")
    assert reference.isdigit()


def test_accepts_bytes() -> None:
    reference = generate_reference(
        b"internal-record-123",
        generated_at=FIXED_DATETIME,
    )

    assert reference.startswith("20260710")


def test_accepts_integer() -> None:
    reference = generate_reference(
        123456789,
        generated_at=FIXED_DATETIME,
    )

    assert reference.startswith("20260710")


def test_supports_prefix_and_separator() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        prefix="INC",
        separator="-",
    )

    assert reference.startswith("INC-20260710-")
    assert len(reference.split("-")[-1]) == 6


def test_supports_custom_suffix_length() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        suffix_length=8,
    )

    assert reference.startswith("20260710")
    assert len(reference) == 16


def test_supports_custom_date_format() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        date_format="%y%m%d",
    )

    assert reference.startswith("260710")
    assert len(reference) == 12


@pytest.mark.parametrize("suffix_length", [0, -1, -10])
def test_rejects_invalid_suffix_length(
    suffix_length: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="suffix_length must be greater than zero",
    ):
        generate_reference(
            FIXED_ULID,
            suffix_length=suffix_length,
        )


@pytest.mark.parametrize("source", ["", " ", b""])
def test_rejects_empty_source(
    source: str | bytes,
) -> None:
    with pytest.raises(
        ValueError,
        match="source must not be empty",
    ):
        generate_reference(source)


def test_rejects_negative_integer() -> None:
    with pytest.raises(
        ValueError,
        match="integer source must not be negative",
    ):
        generate_reference(-1)


def test_rejects_unsupported_source_type() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "source must be a string, bytes, non-negative integer, or UUID"
        ),
    ):
        generate_reference(["unsupported"])  # type: ignore[arg-type]


# No type: ignore on the boolean calls below, and none is possible: bool
# subclasses int in the type system exactly as it does at runtime, so
# SourceIdentifier admits True and mypy is content. Python cannot spell
# "int but not bool", which is why the guard has to be a runtime one --
# and why these tests are the only thing standing between a caller and a
# reference belonging to some other record.
@pytest.mark.parametrize("source", [True, False])
def test_rejects_boolean_source(source: bool) -> None:
    with pytest.raises(
        TypeError,
        match=(
            "source must be a string, bytes, non-negative integer, or UUID"
        ),
    ):
        generate_reference(source)


def test_booleans_do_not_impersonate_their_integers() -> None:
    # The regression that mattered: True was a spelling of 1, and False of 0.
    generate_reference(1, generated_at=FIXED_DATETIME)
    generate_reference(0, generated_at=FIXED_DATETIME)

    with pytest.raises(TypeError):
        generate_reference(True, generated_at=FIXED_DATETIME)

    with pytest.raises(TypeError):
        generate_reference(False, generated_at=FIXED_DATETIME)


# TypeError when the type is unusable, ValueError when the type is right
# but the value is not. Pinned so the distinction cannot drift.
@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda: generate_reference(object()), TypeError),  # type: ignore[arg-type]
        (lambda: generate_reference(["a"]), TypeError),  # type: ignore[arg-type]
        (lambda: generate_reference(True), TypeError),
        (lambda: generate_reference(False), TypeError),
        (lambda: generate_reference(-1), ValueError),
        (lambda: generate_reference(""), ValueError),
        (lambda: generate_reference(b""), ValueError),
        (lambda: generate_reference("x", suffix_length=0), ValueError),
        (lambda: generate_reference("x", attempt=-1), ValueError),
        (
            lambda: generate_reference("x", attempt=MAX_ATTEMPT + 1),
            ValueError,
        ),
    ],
)
def test_error_type_contract(
    call: Callable[[], str],
    expected: type[Exception],
) -> None:
    with pytest.raises(expected):
        call()


# References generated by 0.1.0, before the attempt argument existed.
# Anything stored by a caller on that version has to keep recomputing to
# the same string, so these are pinned rather than derived.
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("01J2H8NQPG6B5X8KGN97SX3R5C", "20260710385177"),
        (UUID("b37fd04a-10b7-47b8-a5fe-76e3e615f441"), "20260710893023"),
        (b"internal-record-123", "20260710016594"),
        (123456789, "20260710284854"),
    ],
)
def test_default_attempt_reproduces_pre_attempt_references(
    source: SourceIdentifier,
    expected: str,
) -> None:
    assert generate_reference(source, generated_at=FIXED_DATETIME) == expected


def test_attempt_zero_is_the_default() -> None:
    default = generate_reference(FIXED_ULID, generated_at=FIXED_DATETIME)
    explicit = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        attempt=0,
    )

    assert default == explicit


def test_attempt_changes_the_reference() -> None:
    first = generate_reference(FIXED_ULID, generated_at=FIXED_DATETIME)
    second = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        attempt=1,
    )

    assert first != second


def test_attempt_is_deterministic() -> None:
    first = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        attempt=7,
    )
    second = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        attempt=7,
    )

    assert first == second


def test_attempt_keeps_the_prefix_and_date() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        prefix="INC",
        separator="-",
        attempt=3,
    )

    assert reference.startswith("INC-20260710-")
    assert len(reference.split("-")[-1]) == 6


def test_successive_attempts_are_distinct() -> None:
    references = {
        generate_reference(
            FIXED_ULID,
            generated_at=FIXED_DATETIME,
            attempt=attempt,
        )
        for attempt in range(50)
    }

    assert len(references) == 50


def test_attempt_is_not_the_same_as_a_suffixed_source() -> None:
    # The attempt is salted, not appended. If it were appended, these two
    # would agree, and the collision fix would introduce a collision.
    salted = generate_reference(
        "abc",
        generated_at=FIXED_DATETIME,
        attempt=1,
    )
    appended = generate_reference(
        "abc1",
        generated_at=FIXED_DATETIME,
    )

    assert salted != appended


def test_accepts_the_largest_attempt() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        attempt=MAX_ATTEMPT,
    )

    assert reference.startswith("20260710")


@pytest.mark.parametrize("attempt", [-1, -10])
def test_rejects_negative_attempt(attempt: int) -> None:
    with pytest.raises(
        ValueError,
        match="attempt must not be negative",
    ):
        generate_reference(FIXED_ULID, attempt=attempt)


def test_rejects_attempt_above_the_maximum() -> None:
    with pytest.raises(
        ValueError,
        match="attempt must not be greater than",
    ):
        generate_reference(FIXED_ULID, attempt=MAX_ATTEMPT + 1)


@pytest.mark.parametrize("reference_count", [0, 1])
def test_collision_probability_is_zero_below_two_references(
    reference_count: int,
) -> None:
    assert collision_probability(reference_count, suffix_length=6) == 0.0


def test_collision_probability_increases_with_reference_count() -> None:
    fewer = collision_probability(50, suffix_length=4)
    more = collision_probability(120, suffix_length=4)

    assert 0.0 < fewer < more < 1.0


def test_collision_probability_decreases_with_longer_suffix() -> None:
    short_suffix = collision_probability(120, suffix_length=4)
    long_suffix = collision_probability(120, suffix_length=6)

    assert long_suffix < short_suffix


def test_collision_probability_matches_birthday_approximation() -> None:
    # 1 - exp(-n*(n-1) / (2 * 10**length)) for n=100, length=4
    probability = collision_probability(100, suffix_length=4)

    assert probability == pytest.approx(0.3904, abs=1e-4)


@pytest.mark.parametrize("suffix_length", [0, -1])
def test_collision_probability_rejects_invalid_suffix_length(
    suffix_length: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="suffix_length must be greater than zero",
    ):
        collision_probability(10, suffix_length=suffix_length)


def test_collision_probability_rejects_negative_reference_count() -> None:
    with pytest.raises(
        ValueError,
        match="reference_count must not be negative",
    ):
        collision_probability(-1, suffix_length=6)


@pytest.mark.parametrize("reference_count", [0, 1])
def test_expected_colliding_pairs_is_zero_below_two_references(
    reference_count: int,
) -> None:
    assert expected_colliding_pairs(reference_count, suffix_length=6) == 0.0


def test_expected_colliding_pairs_matches_the_pair_count() -> None:
    # 300 * 299 / (2 * 10**4)
    assert expected_colliding_pairs(300, suffix_length=4) == pytest.approx(
        4.485
    )


@pytest.mark.parametrize(
    ("reference_count", "suffix_length", "expected"),
    [
        (0, 6, 0.0),
        (1, 6, 0.0),
        (2, 1, 0.1),  # 2 * 1 / (2 * 10)
        (2_000, 3, 1999.0),  # 2000 * 1999 / (2 * 1000)
        (20_000, 3, 199_990.0),
    ],
)
def test_expected_colliding_pairs_counts_pairs(
    reference_count: int,
    suffix_length: int,
    expected: float,
) -> None:
    assert expected_colliding_pairs(
        reference_count,
        suffix_length=suffix_length,
    ) == pytest.approx(expected)


def test_expected_colliding_pairs_is_not_the_number_of_rejected_inserts() -> (
    None
):
    """Pairs and rejected inserts are different quantities.

    A suffix drawn k times is k * (k - 1) / 2 pairs but only k - 1
    rejected inserts, so the pair count runs ahead of the retries once a
    bucket fills. The docs said otherwise until 0.2.1; this pins the
    difference so the claim cannot quietly come back.
    """
    space = 10**3
    count = 2_000

    pairs = expected_colliding_pairs(count, suffix_length=3)

    # Inserting count references into `space` slots, the expected number
    # rejected by a unique constraint is
    #     n - space * (1 - (1 - 1/space) ** n)
    rejected = count - space * (1 - (1 - 1 / space) ** count)

    assert pairs == pytest.approx(1999.0)
    assert rejected == pytest.approx(1135.2, abs=0.5)
    assert pairs > rejected * 1.5


def test_expected_colliding_pairs_grows_with_reference_count() -> None:
    fewer = expected_colliding_pairs(50, suffix_length=4)
    more = expected_colliding_pairs(120, suffix_length=4)

    assert 0.0 < fewer < more


def test_expected_colliding_pairs_decreases_with_longer_suffix() -> None:
    short_suffix = expected_colliding_pairs(300, suffix_length=4)
    long_suffix = expected_colliding_pairs(300, suffix_length=6)

    assert long_suffix < short_suffix


def test_expected_colliding_pairs_keeps_counting_past_certainty() -> None:
    # The point of the function: collision_probability saturates at
    # "certain" and stops separating a crowded format from a hopeless
    # one. The expected count still does.
    crowded = collision_probability(2_000, suffix_length=3)
    hopeless = collision_probability(20_000, suffix_length=3)

    assert crowded == pytest.approx(1.0)
    assert hopeless == pytest.approx(1.0)

    assert expected_colliding_pairs(20_000, suffix_length=3) > (
        expected_colliding_pairs(2_000, suffix_length=3)
    )


@pytest.mark.parametrize("suffix_length", [0, -1])
def test_expected_colliding_pairs_rejects_invalid_suffix_length(
    suffix_length: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="suffix_length must be greater than zero",
    ):
        expected_colliding_pairs(10, suffix_length=suffix_length)


def test_expected_colliding_pairs_rejects_negative_reference_count() -> None:
    with pytest.raises(
        ValueError,
        match="reference_count must not be negative",
    ):
        expected_colliding_pairs(-1, suffix_length=6)


def test_max_references_grows_with_suffix_length() -> None:
    assert max_references(4) < max_references(6) < max_references(8)


def test_max_references_grows_with_allowed_probability() -> None:
    strict = max_references(6, max_probability=0.01)
    lenient = max_references(6, max_probability=0.50)

    assert strict < lenient


def test_max_references_stays_within_target_probability() -> None:
    limit = max_references(6, max_probability=0.01)

    assert collision_probability(limit, suffix_length=6) <= 0.01
    assert collision_probability(limit + 1, suffix_length=6) > 0.01


@pytest.mark.parametrize("suffix_length", [0, -1])
def test_max_references_rejects_invalid_suffix_length(
    suffix_length: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="suffix_length must be greater than zero",
    ):
        max_references(suffix_length)


@pytest.mark.parametrize("max_probability", [0.0, 1.0, -0.1, 1.5])
def test_max_references_rejects_invalid_probability(
    max_probability: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_probability must be between 0 and 1",
    ):
        max_references(6, max_probability=max_probability)


# ---------------------------------------------------------------------------
# 0.3.0: the date bucket no longer depends on the machine
# ---------------------------------------------------------------------------


def test_the_system_timezone_does_not_reach_the_reference() -> None:
    """The bug 0.3.0 exists to kill.

    Before 0.3.0 the default clock was datetime.now(), naive local time,
    so the same identifier at the same instant produced 20260713... in
    Lima and 20260714... in Tokyo. A reference that depends on which
    machine produced it is not deterministic, which is the one thing this
    library sells.
    """
    instant = datetime(2026, 7, 13, 23, 30, tzinfo=timezone.utc)

    references = set()
    for zone in ("UTC", "America/Lima", "Asia/Tokyo", "Pacific/Auckland"):
        previous = os.environ.get("TZ")
        os.environ["TZ"] = zone
        time.tzset()
        try:
            references.add(
                generate_reference(FIXED_ULID, generated_at=instant)
            )
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            time.tzset()

    assert len(references) == 1


def test_aware_datetimes_are_converted_into_the_reference_timezone() -> None:
    # One instant, expressed two ways. Both must land in the same bucket.
    utc = datetime(2026, 7, 13, 23, 30, tzinfo=timezone.utc)
    tokyo = utc.astimezone(ZoneInfo("Asia/Tokyo"))  # 2026-07-14 08:30 +09

    assert tokyo.strftime("%Y%m%d") == "20260714"  # a different wall date
    assert generate_reference(FIXED_ULID, generated_at=utc) == (
        generate_reference(FIXED_ULID, generated_at=tokyo)
    )


def test_tz_moves_the_bucket_boundary() -> None:
    # 23:30 UTC is already the 14th in Tokyo. A caller who wants the
    # business day rather than UTC asks for it, and gets it.
    instant = datetime(2026, 7, 13, 23, 30, tzinfo=timezone.utc)

    in_utc = generate_reference(FIXED_ULID, generated_at=instant)
    in_tokyo = generate_reference(
        FIXED_ULID,
        generated_at=instant,
        tz=ZoneInfo("Asia/Tokyo"),
    )

    assert in_utc.startswith("20260713")
    assert in_tokyo.startswith("20260714")


def test_naive_datetimes_are_taken_at_face_value() -> None:
    # A wall clock the caller chose. It is used as given, whatever the
    # machine's timezone says.
    naive = datetime(2026, 7, 13, 23, 30)

    for zone in ("UTC", "Pacific/Auckland"):
        previous = os.environ.get("TZ")
        os.environ["TZ"] = zone
        time.tzset()
        try:
            reference = generate_reference(FIXED_ULID, generated_at=naive)
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            time.tzset()

        assert reference.startswith("20260713")


def test_the_default_clock_is_aware() -> None:
    # Nothing asserts the wall time, only that the default path does not
    # go through naive local time.
    reference = generate_reference(FIXED_ULID)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    assert reference.startswith(today)


def test_default_timezone_is_utc() -> None:
    assert DEFAULT_TIMEZONE is timezone.utc


# ---------------------------------------------------------------------------
# 0.3.0: expected_rejected_inserts, and the honest name for the pair count
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reference_count", [0, 1])
def test_expected_rejected_inserts_is_zero_below_two_references(
    reference_count: int,
) -> None:
    assert expected_rejected_inserts(reference_count, suffix_length=6) == 0.0


def test_expected_rejected_inserts_matches_the_closed_form() -> None:
    # n - space * (1 - (1 - 1/space) ** n), verified against simulation.
    assert expected_rejected_inserts(2_000, suffix_length=3) == pytest.approx(
        1135.2, abs=0.1
    )


def test_expected_rejected_inserts_cannot_exceed_the_reference_count() -> None:
    # An insert can only be rejected once. Pairs have no such ceiling, and
    # that is exactly why they were the wrong number to hand a caller.
    for count in (100, 2_000, 5_000, 50_000):
        assert 0.0 <= expected_rejected_inserts(count, 3) <= count

    assert expected_colliding_pairs(50_000, 3) > 50_000


def test_rejected_inserts_are_fewer_than_colliding_pairs_once_crowded() -> (
    None
):
    pairs = expected_colliding_pairs(2_000, suffix_length=3)
    rejected = expected_rejected_inserts(2_000, suffix_length=3)

    assert pairs == pytest.approx(1999.0)
    assert rejected == pytest.approx(1135.2, abs=0.1)
    assert pairs > rejected * 1.5


def test_expected_collisions_still_works_but_warns() -> None:
    with pytest.warns(DeprecationWarning, match="expected_colliding_pairs"):
        legacy = expected_collisions(2_000, 3)

    assert legacy == expected_colliding_pairs(2_000, 3)


@pytest.mark.parametrize("suffix_length", [0, -1])
def test_expected_rejected_inserts_rejects_invalid_suffix_length(
    suffix_length: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="suffix_length must be greater than zero",
    ):
        expected_rejected_inserts(10, suffix_length=suffix_length)


def test_expected_rejected_inserts_rejects_negative_reference_count() -> None:
    with pytest.raises(
        ValueError,
        match="reference_count must not be negative",
    ):
        expected_rejected_inserts(-1, suffix_length=6)


# ---------------------------------------------------------------------------
# 0.3.0: suffix_length_for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reference_count", [0, 1])
def test_suffix_length_for_is_one_below_two_references(
    reference_count: int,
) -> None:
    assert suffix_length_for(reference_count) == 1


@pytest.mark.parametrize("reference_count", [10, 50, 200, 500, 5_000])
def test_suffix_length_for_returns_the_smallest_length_that_fits(
    reference_count: int,
) -> None:
    length = suffix_length_for(reference_count)

    assert collision_probability(reference_count, length) <= 0.01
    assert collision_probability(reference_count, length - 1) > 0.01


def test_suffix_length_for_agrees_with_max_references() -> None:
    # The two invert each other: the largest volume a length can carry
    # must not ask for a longer one.
    for length in range(3, 9):
        assert suffix_length_for(max_references(length)) <= length


def test_suffix_length_for_honours_the_probability() -> None:
    strict = suffix_length_for(200, max_probability=0.001)
    lenient = suffix_length_for(200, max_probability=0.10)

    assert lenient < strict


def test_suffix_length_for_rejects_negative_reference_count() -> None:
    with pytest.raises(
        ValueError,
        match="reference_count must not be negative",
    ):
        suffix_length_for(-1)


@pytest.mark.parametrize("max_probability", [0.0, 1.0, -0.1, 1.5])
def test_suffix_length_for_rejects_invalid_probability(
    max_probability: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_probability must be between 0 and 1",
    ):
        suffix_length_for(200, max_probability=max_probability)


# ---------------------------------------------------------------------------
# 0.4.0: alphabet
# ---------------------------------------------------------------------------


def test_digits_remain_the_default() -> None:
    assert DEFAULT_ALPHABET == DIGITS
    assert generate_reference(
        FIXED_ULID, generated_at=FIXED_DATETIME
    ).isdigit()


def test_crockford_omits_the_letters_a_human_misreads() -> None:
    # I and L read as 1, O reads as 0, and U is dropped so the encoding
    # does not spell obscenities.
    for character in "ILOU":
        assert character not in CROCKFORD_BASE32

    assert len(CROCKFORD_BASE32) == 32
    assert len(set(CROCKFORD_BASE32)) == 32


def test_alphabet_changes_the_suffix_but_not_its_length() -> None:
    digits = generate_reference(FIXED_ULID, generated_at=FIXED_DATETIME)
    base32 = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        alphabet=CROCKFORD_BASE32,
    )

    assert digits[8:] != base32[8:]
    assert len(digits) == len(base32)
    assert all(character in CROCKFORD_BASE32 for character in base32[8:])


def test_alphabet_is_deterministic() -> None:
    first = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        alphabet=CROCKFORD_BASE32,
    )
    second = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        alphabet=CROCKFORD_BASE32,
    )

    assert first == second


@pytest.mark.parametrize("alphabet", ["", "0"])
def test_rejects_an_alphabet_too_short_to_count_in(alphabet: str) -> None:
    with pytest.raises(
        ValueError,
        match="alphabet must have at least two characters",
    ):
        generate_reference(FIXED_ULID, alphabet=alphabet)


def test_rejects_an_alphabet_with_a_repeated_character() -> None:
    with pytest.raises(
        ValueError,
        match="alphabet must not repeat a character",
    ):
        generate_reference(FIXED_ULID, alphabet="0123456780")


def test_base32_holds_far_more_per_character() -> None:
    # The reason the alphabet exists: the same length, far more room.
    assert max_references(6, base=32) > max_references(6, base=10) * 30
    assert suffix_length_for(200, base=32) < suffix_length_for(200, base=10)


# ---------------------------------------------------------------------------
# 0.4.0: check character
# ---------------------------------------------------------------------------


def test_check_appends_exactly_one_character() -> None:
    plain = generate_reference(FIXED_ULID, generated_at=FIXED_DATETIME)
    checked = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        check=True,
    )

    assert len(checked) == len(plain) + 1
    assert checked.startswith(plain)


def test_a_checked_reference_verifies() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        prefix="RDR",
        separator="-",
        check=True,
    )

    assert verify_reference(reference, prefix="RDR", separator="-")


@pytest.mark.parametrize("alphabet", [DIGITS, CROCKFORD_BASE32])
def test_check_catches_every_single_character_error(alphabet: str) -> None:
    """The common typo. Luhn mod N catches all of them, in any base."""
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        alphabet=alphabet,
        check=True,
    )

    for position in range(len(reference)):
        for character in alphabet:
            if character == reference[position]:
                continue

            mistyped = (
                reference[:position] + character + reference[position + 1 :]
            )

            assert not verify_reference(mistyped, alphabet=alphabet), mistyped


def test_check_covers_the_date_as_well_as_the_suffix() -> None:
    # A mistyped day is a transcription error too, and it sends the lookup
    # into the wrong bucket.
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        check=True,
    )

    assert reference.startswith("20260710")

    wrong_day = "20260711" + reference[8:]

    assert not verify_reference(wrong_day)


def test_check_misses_only_the_luhn_blind_spot() -> None:
    """Luhn cannot see a 09 <-> 90 swap. Say so, rather than imply otherwise.

    Every other adjacent transposition is caught. Damm would close this
    gap, but a Damm check needs a totally anti-symmetric quasigroup of the
    alphabet's order, which cannot be built for an arbitrary alphabet at
    call time. Credit cards live with the same hole.
    """
    undetected = set()

    for index in range(200):
        reference = generate_reference(
            f"source-{index}",
            generated_at=FIXED_DATETIME,
            check=True,
        )

        for position in range(8, len(reference) - 1):
            left, right = reference[position], reference[position + 1]
            if left == right:
                continue

            swapped = (
                reference[:position] + right + left + reference[position + 2 :]
            )

            if verify_reference(swapped):
                undetected.add(frozenset((left, right)))

    assert undetected == {frozenset(("0", "9"))}


def test_the_check_character_adds_no_capacity() -> None:
    # It is computed from the reference, not drawn from the hash. Seven
    # characters of which one is a check still hold a million values.
    plain = {
        generate_reference(
            f"source-{index}",
            generated_at=FIXED_DATETIME,
            suffix_length=3,
        )
        for index in range(500)
    }
    checked = {
        generate_reference(
            f"source-{index}",
            generated_at=FIXED_DATETIME,
            suffix_length=3,
            check=True,
        )
        for index in range(500)
    }

    assert len(plain) == len(checked)


def test_verify_rejects_a_string_too_short_to_carry_a_check() -> None:
    assert not verify_reference("")
    assert not verify_reference("7")


# ---------------------------------------------------------------------------
# 0.4.0: namespace
# ---------------------------------------------------------------------------


def test_namespace_separates_references_that_share_a_source() -> None:
    """The bug 0.4.0 fixes.

    prefix never reached the hash, so an order and an invoice derived from
    one customer's ULID drew the same suffix every time. That is a
    certainty, not a one-in-a-million coincidence, and none of the
    collision helpers accounted for it.
    """
    order = generate_reference(
        "customer-42",
        generated_at=FIXED_DATETIME,
        prefix="ORD",
        separator="-",
    )
    invoice = generate_reference(
        "customer-42",
        generated_at=FIXED_DATETIME,
        prefix="INV",
        separator="-",
    )

    # Still true, and still surprising: the prefix is only a label.
    assert order.split("-")[-1] == invoice.split("-")[-1]

    # Namespaces are what actually separate them.
    namespaced_order = generate_reference(
        "customer-42",
        generated_at=FIXED_DATETIME,
        prefix="ORD",
        separator="-",
        namespace="orders",
    )
    namespaced_invoice = generate_reference(
        "customer-42",
        generated_at=FIXED_DATETIME,
        prefix="INV",
        separator="-",
        namespace="invoices",
    )

    assert (
        namespaced_order.split("-")[-1] != (namespaced_invoice.split("-")[-1])
    )


def test_the_empty_namespace_reproduces_pre_namespace_references() -> None:
    # blake2b treats an empty key as no key, which is what earlier versions
    # hashed with. Stored references must survive the upgrade.
    assert generate_reference("customer-42", generated_at=FIXED_DATETIME) == (
        generate_reference(
            "customer-42",
            generated_at=FIXED_DATETIME,
            namespace="",
        )
    )


def test_namespace_is_deterministic() -> None:
    first = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        namespace="orders",
    )
    second = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        namespace="orders",
    )

    assert first == second


def test_a_namespace_cannot_be_spelled_as_part_of_another_source() -> None:
    # The namespace is the hash key, not a prefix on the message. Were it
    # appended, these two would agree.
    keyed = generate_reference(
        "b",
        generated_at=FIXED_DATETIME,
        namespace="a",
    )
    concatenated = generate_reference("ab", generated_at=FIXED_DATETIME)

    assert keyed != concatenated


def test_rejects_a_namespace_longer_than_the_hash_key() -> None:
    with pytest.raises(
        ValueError,
        match="namespace must not exceed",
    ):
        generate_reference(
            FIXED_ULID,
            namespace="n" * (MAX_NAMESPACE_BYTES + 1),
        )


def test_a_namespace_at_the_limit_is_accepted() -> None:
    reference = generate_reference(
        FIXED_ULID,
        generated_at=FIXED_DATETIME,
        namespace="n" * MAX_NAMESPACE_BYTES,
    )

    assert reference.startswith("20260710")


# ---------------------------------------------------------------------------
# 0.4.0: the sizing helpers learned about the base
# ---------------------------------------------------------------------------


def test_the_helpers_default_to_base_ten() -> None:
    assert collision_probability(50, 4) == collision_probability(
        50, 4, base=10
    )
    assert max_references(6) == max_references(6, base=10)
    assert suffix_length_for(200) == suffix_length_for(200, base=10)


def test_a_larger_base_holds_more_at_the_same_length() -> None:
    assert collision_probability(200, 6, base=32) < (
        collision_probability(200, 6, base=10)
    )
    assert expected_rejected_inserts(200, 6, base=32) < (
        expected_rejected_inserts(200, 6, base=10)
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: collision_probability(10, 4, base=1),
        lambda: expected_colliding_pairs(10, 4, base=1),
        lambda: expected_rejected_inserts(10, 4, base=1),
        lambda: max_references(4, base=1),
        lambda: suffix_length_for(10, base=1),
    ],
)
def test_helpers_reject_a_base_below_two(call: Callable[[], float]) -> None:
    with pytest.raises(ValueError, match="base must be at least two"):
        call()
