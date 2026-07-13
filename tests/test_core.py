from datetime import datetime
from uuid import UUID

import pytest

from compactref import (
    collision_probability,
    generate_reference,
    max_references,
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
