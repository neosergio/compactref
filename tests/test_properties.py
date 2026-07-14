"""Property-based tests.

The tests in test_core.py sample: a fixed ULID, a fixed date, one or two
alphabets. These state the invariants that must hold for *every*
configuration, and let Hypothesis go looking for the one that does not.
"""

from __future__ import annotations

from datetime import datetime, timezone

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

namespaces = st.text(max_size=16).filter(
    lambda value: len(value.encode("utf-8")) <= MAX_NAMESPACE_BYTES
)

moments = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
).map(lambda value: value.replace(tzinfo=timezone.utc))


@st.composite
def schemes(draw: st.DrawFn, *, check: bool | None = None) -> CompactRef:
    return CompactRef(
        suffix_length=draw(st.integers(min_value=1, max_value=12)),
        alphabet=draw(alphabets),
        check=draw(st.booleans()) if check is None else check,
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
    """Luhn catches every single-character error, in every alphabet."""
    reference = scheme.generate(source, generated_at=at)  # type: ignore[arg-type]

    body = scheme._strip_label(reference)
    assume(body)

    index = position % len(body)
    character = scheme.alphabet[replacement % scheme.base]
    assume(character != body[index])
    # Only edit a character the check actually covers.
    assume(body[index] in scheme.alphabet)

    edited = body[:index] + character + body[index + 1 :]
    rebuilt = (
        scheme.prefix + scheme.separator + edited if scheme.prefix else edited
    )

    assert not scheme.verify(rebuilt)


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
