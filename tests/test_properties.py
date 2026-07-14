"""Property-based tests.

The tests in test_core.py sample: a fixed ULID, a fixed date, one or two
alphabets. These state the invariants that must hold for *every*
configuration, and let Hypothesis go looking for the one that does not.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from compactref import (
    CROCKFORD_BASE32,
    DIGITS,
    MAX_NAMESPACE_BYTES,
    CompactRef,
    generate_reference,
)


# A source the library accepts. Booleans are deliberately absent: they are
# rejected, and test_core.py pins that.
sources = st.one_of(
    st.text(min_size=1).filter(lambda value: value.strip()),
    st.binary(min_size=1),
    st.integers(min_value=0, max_value=2**128),
    st.uuids(),
)

alphabets = st.sampled_from([DIGITS, CROCKFORD_BASE32, "01", "abcdef"])

# A checked scheme must be able to spell its own date, or the checksum skips
# the characters it cannot index and a mistyped date verifies. Hypothesis
# found that: under "01", the 2 of a 2026 date is skipped, and editing it to
# a 0 left the check unmoved. So a checked scheme draws from the alphabets
# that contain the digits.
checkable_alphabets = st.sampled_from([DIGITS, CROCKFORD_BASE32])

namespaces = st.text(max_size=16).filter(
    lambda value: len(value.encode("utf-8")) <= MAX_NAMESPACE_BYTES
)

moments = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
).map(lambda value: value.replace(tzinfo=timezone.utc))


@st.composite
def schemes(draw: st.DrawFn, *, check: bool | None = None) -> CompactRef:
    checked = draw(st.booleans()) if check is None else check

    return CompactRef(
        suffix_length=draw(st.integers(min_value=1, max_value=12)),
        alphabet=draw(checkable_alphabets if checked else alphabets),
        check=checked,
        namespace=draw(namespaces),
        prefix=draw(st.sampled_from(["", "RDR", "ORD"])),
        separator=draw(st.sampled_from(["", "-", "/"])),
    )


@given(source=sources, scheme=schemes(), at=moments)
@settings(max_examples=300)
def test_the_suffix_is_always_the_length_and_alphabet_asked_for(
    source: object,
    scheme: CompactRef,
    at: datetime,
) -> None:
    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]

    body = reference
    if scheme.prefix:
        body = body[len(scheme.prefix) :]
    if scheme.separator:
        body = body.replace(scheme.separator, "")

    expected = scheme.suffix_length + (1 if scheme.check else 0)
    suffix = body[-expected:]

    assert len(suffix) == expected
    assert all(character in scheme.alphabet for character in suffix)


@given(source=sources, scheme=schemes(), at=moments)
@settings(max_examples=300)
def test_generation_is_deterministic(
    source: object,
    scheme: CompactRef,
    at: datetime,
) -> None:
    first = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]
    second = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]

    assert first == second


@given(source=sources, scheme=schemes(check=True), at=moments)
@settings(max_examples=300)
def test_verify_accepts_whatever_generate_produced(
    source: object,
    scheme: CompactRef,
    at: datetime,
) -> None:
    """The invariant the class exists for: the two cannot disagree."""
    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]

    assert scheme.verify(reference)


@given(
    source=sources,
    scheme=schemes(check=True),
    at=moments,
    position=st.integers(min_value=0),
    replacement=st.integers(min_value=0),
)
@settings(max_examples=500)
def test_a_single_character_edit_never_verifies(
    source: object,
    scheme: CompactRef,
    at: datetime,
    position: int,
    replacement: int,
) -> None:
    """Change any one character of a reference and it stops verifying.

    Anywhere: in the prefix, in a separator, in the date, in the suffix.
    Each is caught by something different — the prefix by the literal
    match, a separator by the positional read, the date and suffix by Luhn
    — and the caller does not care which. They care that a garbled
    reference is refused.
    """
    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]
    assume(reference)

    index = position % len(reference)
    character = scheme.alphabet[replacement % scheme.base]
    assume(character != reference[index])

    edited = reference[:index] + character + reference[index + 1 :]

    assert not scheme.verify(edited)


@given(
    source=sources,
    scheme=schemes(check=True),
    at=moments,
    position=st.integers(min_value=0),
)
@settings(max_examples=400)
def test_a_stray_separator_never_verifies(
    source: object,
    scheme: CompactRef,
    at: datetime,
    position: int,
) -> None:
    """An extra separator is a transcription error like any other.

    verify() used to pull the reference apart on the separator and delete
    every occurrence, so ORD--20260714-… and ORD-20260714-…- both came back
    True. That is the confusion the check character exists to prevent: a
    caller could not tell a typo from a reference that does not exist.
    It reads by position now.
    """
    assume(scheme.separator)

    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]
    index = position % (len(reference) + 1)

    inserted = reference[:index] + scheme.separator + reference[index:]

    assert not scheme.verify(inserted)


@given(source=sources, scheme=schemes(), at=moments, count=st.integers(2, 25))
@settings(max_examples=200)
def test_each_attempt_is_deterministic(
    source: object,
    scheme: CompactRef,
    at: datetime,
    count: int,
) -> None:
    """The invariant that actually holds for every attempt.

    Not "attempts never repeat". Hypothesis killed that one: with a binary
    alphabet over six characters there are 64 suffixes, and nine attempts
    collide by the birthday problem, exactly as nine sources would.
    Attempts are independent draws, not a walk through unused values.
    """
    for attempt in range(count):
        first = scheme.generate(source, generated_at=at, attempt=attempt)  # type: ignore[arg-type]
        second = scheme.generate(source, generated_at=at, attempt=attempt)  # type: ignore[arg-type]

        assert first == second


@given(source=sources, scheme=schemes(), at=moments, count=st.integers(2, 25))
@settings(max_examples=200)
def test_attempts_are_distinct_when_the_bucket_has_room(
    source: object,
    scheme: CompactRef,
    at: datetime,
    count: int,
) -> None:
    """A retry loop makes progress — but only because the bucket is roomy.

    Sized so a birthday collision among the attempts is vanishingly
    unlikely. The point of the bound is that it has to be *stated*: a
    crowded bucket cannot promise this, and no retry policy fixes that.
    """
    assume(scheme.base**scheme.suffix_length >= count**2 * 100_000)

    references = {
        scheme.generate(source, generated_at=at, attempt=attempt)  # type: ignore[arg-type]
        for attempt in range(count)
    }

    assert len(references) == count


@given(source=sources, at=moments)
@settings(max_examples=200)
def test_the_defaults_reproduce_the_pre_feature_reference(
    source: object,
    at: datetime,
) -> None:
    """Every feature added since 0.1.0 defaults to doing nothing.

    attempt=0 salts with zeros, which BLAKE2b treats as unsalted. The empty
    namespace is an empty key, which it treats as unkeyed. Together they
    must reproduce what the library produced before either existed.
    """
    plain = generate_reference(source, generated_at=at)  # type: ignore[arg-type]
    explicit = generate_reference(
        source,  # type: ignore[arg-type]
        generated_at=at,
        attempt=0,
        namespace="",
        alphabet=DIGITS,
        check=False,
    )

    assert plain == explicit


@given(scheme=schemes(), count=st.integers(min_value=0, max_value=10_000))
@settings(max_examples=300)
def test_rejected_inserts_never_exceed_the_reference_count(
    scheme: CompactRef,
    count: int,
) -> None:
    """An insert can only be rejected once. Pairs have no such ceiling."""
    rejected = scheme.expected_rejected_inserts(count)

    assert 0.0 <= rejected <= count


@given(
    scheme=schemes(),
    count=st.integers(min_value=2, max_value=10_000),
    probability=st.floats(min_value=0.001, max_value=0.5),
)
@settings(max_examples=300)
def test_the_recommended_length_actually_meets_the_target(
    scheme: CompactRef,
    count: int,
    probability: float,
) -> None:
    length = scheme.suffix_length_for(count, probability)
    sized = CompactRef(suffix_length=length, alphabet=scheme.alphabet)

    assert sized.collision_probability(count) <= probability


# ---------------------------------------------------------------------------
# 1.0.0: the configurations that make a scheme fail to verify itself
#
# CodeRabbit found these, and the strategy above could not have. It only ever
# drew separators from "-" and "/", which appear in none of the alphabets it
# draws, so the overlap was never generated. A property test explores the
# space you hand it and no further.
# ---------------------------------------------------------------------------


@given(
    alphabet=alphabets,
    index=st.integers(min_value=0),
)
@settings(max_examples=200)
def test_a_separator_from_the_alphabet_is_always_refused(
    alphabet: str,
    index: int,
) -> None:
    """Whatever the alphabet, a separator drawn from it is refused.

    Were it allowed, stripping the separator in verify() would take
    characters out of the suffix, and the scheme would reject a reference it
    had just produced.
    """
    separator = alphabet[index % len(alphabet)]

    with pytest.raises(ValueError, match="separator must not contain"):
        CompactRef(alphabet=alphabet, separator=separator)


@given(
    alphabet=checkable_alphabets,
    separator=st.sampled_from(["-", "/", ".", " ", "::"]),
)
@settings(max_examples=100)
def test_a_separator_outside_the_alphabet_is_always_accepted(
    alphabet: str,
    separator: str,
) -> None:
    assume(not set(separator) & set(alphabet))

    scheme = CompactRef(alphabet=alphabet, separator=separator, check=True)
    reference = scheme.generate("01J2H8NQPG6B5X8KGN97SX3R5C")

    assert scheme.verify(reference)


# Depend on the machine's language: "%B" is July, julio or juillet. Refused
# always -- a reference must not read differently in Madrid than in London.
LOCALE_DEPENDENT_FORMATS = ["%B", "%A", "%b", "%a", "%c", "%x", "%X", "%p"]

# Do not render at all on Windows: "%-d" is a glibc extension. On Linux and
# macOS they render and vary. Either way a scheme cannot be built with them,
# but the reason differs by platform, so they are tested apart.
NON_PORTABLE_FORMATS = ["%-d", "%-m", "%-H", "%-M"]
FIXED_WIDTH_FORMATS = ["%Y%m%d", "%y%m%d", "%Y%m", "%Y%m%d%H", "%j", ""]


@given(
    date_format=st.sampled_from(LOCALE_DEPENDENT_FORMATS),
    check=st.booleans(),
)
@settings(max_examples=100)
def test_a_locale_dependent_date_format_is_always_refused(
    date_format: str,
    check: bool,
) -> None:
    """With or without a check character. Determinism is not optional."""
    with pytest.raises(ValueError, match="depends on the machine's"):
        CompactRef(date_format=date_format, check=check)


@given(date_format=st.sampled_from(NON_PORTABLE_FORMATS))
@settings(max_examples=50)
def test_a_date_format_that_is_not_portable_is_always_refused(
    date_format: str,
) -> None:
    """Refused everywhere, for a reason that depends on where you are.

    "%-d" is a glibc extension. On Windows it does not render at all, and
    the library says so. On Linux and macOS it renders — and produces a
    width that moves, which is refused for its own reasons. The caller
    cannot build the scheme either way, which is the point: a reference is
    supposed to be the same on every machine.
    """
    with pytest.raises(ValueError) as caught:
        CompactRef(date_format=date_format, check=True)

    message = str(caught.value)

    assert repr(date_format) in message
    assert (
        "does not render on this platform" in message
        or "needs a date of a fixed width" in message
    ), message


@given(
    date_format=st.sampled_from(FIXED_WIDTH_FORMATS),
    at=moments,
    source=sources,
)
@settings(max_examples=300)
def test_a_fixed_width_date_verifies_on_every_date_of_the_year(
    date_format: str,
    at: datetime,
    source: object,
) -> None:
    """The invariant the width guard buys.

    A reference must verify whatever day of the year it was made on. With a
    variable-width format it would verify in January and be rejected in
    December, which is the bug the guard exists to make impossible.
    """
    scheme = CompactRef(date_format=date_format, check=True, separator="-")
    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]

    assert scheme.verify(reference)


@given(source=sources, scheme=schemes(check=True), at=moments)
@settings(max_examples=300)
def test_the_function_cannot_mint_what_the_class_cannot_verify(
    source: object,
    scheme: CompactRef,
    at: datetime,
) -> None:
    """The invariant that broke when the guards lived in only one place.

    generate_reference() carried no check-coverage rules, so it happily
    produced references — 2026-07-140471283, say — that no CompactRef could
    be built to verify, because the class refused that configuration. A
    library should not be able to mint a thing it cannot read.

    Both now share _validate_checkable(), so whatever the function produces
    with check=True, the matching scheme verifies.
    """
    reference = generate_reference(
        source,  # type: ignore[arg-type]
        generated_at=at,
        tz=scheme.tz,
        suffix_length=scheme.suffix_length,
        alphabet=scheme.alphabet,
        check=True,
        namespace=scheme.namespace,
        date_format=scheme.date_format,
        prefix=scheme.prefix,
        separator=scheme.separator,
    )

    assert scheme.verify(reference)
    assert reference == scheme.generate(source, generated_at=at)  # type: ignore[arg-type]


@given(source=sources, scheme=schemes(), at=moments)
@settings(max_examples=400)
def test_reference_length_is_the_length_of_the_reference(
    source: object,
    scheme: CompactRef,
    at: datetime,
) -> None:
    """Written for a column definition, so it had better be right.

    String(scheme.reference_length) is only as good as this property.
    """
    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]

    assert scheme.reference_length == len(reference)


@given(scheme=schemes(check=True))
@settings(max_examples=100)
def test_a_checked_scheme_always_has_a_length(scheme: CompactRef) -> None:
    """None is only ever possible without a check character.

    A checked scheme cannot be built on a date that changes width, so its
    reference cannot change width either.
    """
    assert scheme.reference_length is not None
    assert scheme.date_length is not None


@given(source=sources, scheme=schemes(), at=moments)
@settings(max_examples=400)
def test_parse_reassembles_whatever_generate_produced(
    source: object,
    scheme: CompactRef,
    at: datetime,
) -> None:
    """parse() and generate() are inverses, for every configuration."""
    assume(scheme.date_length is not None)

    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]
    parsed = scheme.parse(reference)

    rebuilt = scheme.separator.join(
        part
        for part in (
            parsed.prefix,
            parsed.date_part,
            parsed.suffix + (parsed.check_character or ""),
        )
        if part
    )

    assert rebuilt == reference
