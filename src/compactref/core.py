from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from hashlib import blake2b
from math import ceil, exp, expm1, log, log1p, sqrt
from typing import TypeAlias
from uuid import UUID
from warnings import warn


SourceIdentifier: TypeAlias = str | bytes | int | UUID

DIGITS = "0123456789"

# Crockford's base32: the digits, then the letters with I, L, O and U
# removed. I and L are dropped because they are read as 1, O because it is
# read as 0, and U so that the encoding does not spell obscenities by
# accident. What is left is 32 characters a human can transcribe.
CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Decimal stays the default. Anything else would move every reference our
# callers have already stored.
DEFAULT_ALPHABET = DIGITS

DEFAULT_SUFFIX_LENGTH = 6
DEFAULT_DATE_FORMAT = "%Y%m%d"

# The date part is a bucket label, and every caller has to agree on which
# bucket an instant falls in. UTC is the only default that does not depend
# on which machine happened to run the code.
DEFAULT_TIMEZONE: tzinfo = timezone.utc

# blake2b takes at most 16 bytes of salt, which is where the attempt goes.
MAX_ATTEMPT = 2**128 - 1

# blake2b takes at most 64 bytes of key, which is where the namespace goes.
MAX_NAMESPACE_BYTES = 64


def generate_reference(
    source: SourceIdentifier,
    *,
    generated_at: datetime | None = None,
    tz: tzinfo = DEFAULT_TIMEZONE,
    suffix_length: int = DEFAULT_SUFFIX_LENGTH,
    alphabet: str = DEFAULT_ALPHABET,
    check: bool = False,
    namespace: str = "",
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
            Number of characters used after the date. The check character,
            if any, is added on top of this.

        alphabet:
            Characters the suffix is drawn from. Defaults to the decimal
            digits, which is what every reference produced before 0.4.0
            used.

            CROCKFORD_BASE32 buys a great deal of room at no extra length:
            six decimal characters carry a million values, six Crockford
            characters carry 1.07 billion, which is 32 times the volume a
            bucket holds at the same risk. It is not free, though. Digits
            can be typed on a numeric keypad and read down a phone line
            without spelling anything; letters cannot. Choose deliberately.

        check:
            Append a check character, so a mistyped reference is *invalid*
            rather than merely absent. Without one, a support agent who
            fat-fingers a digit gets "no such record", which is
            indistinguishable from a record that does not exist. Read it
            back with verify_reference().

            The character is derived from the date and the suffix — Luhn
            mod N over ``alphabet``, the scheme on the back of a credit
            card, generalised past base ten. It catches:

            - every single-character error, which is the common typo;
            - every adjacent transposition *except* the swap of the first
              and last characters of the alphabet. For the digits that is
              09 <-> 90, and for CROCKFORD_BASE32 it is 0Z <-> Z0. Luhn
              cannot see those, which costs about 2.7% of transpositions
              in decimal and 0.3% in base32. Measured, not assumed.

            It adds a character but no capacity: it is computed from the
            reference, not drawn from the hash, so the collision maths
            still depend on ``suffix_length`` alone. A six-character suffix
            with a check character is seven characters holding a million
            values, not ten million.

        namespace:
            Separates references that share a source. The suffix is
            derived from the source alone, and ``prefix`` is only a label
            — it never reaches the hash. So an order and an invoice both
            derived from one customer's ULID draw the *same* suffix, every
            time:

                ORD-20260713-133083
                INV-20260713-133083

            That is a certainty, not a one-in-a-million coincidence, and
            the collision helpers in this module do not account for it.
            Give each kind of reference its own namespace and they stop
            agreeing.

            Carried in the hash itself (BLAKE2b's key), so it cannot be
            spelled as part of some other source. An empty namespace, the
            default, reproduces every reference made before 0.4.0.

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

            Attempts are independent draws, not a walk through unused
            values: two of them can land on the same suffix, exactly as two
            sources can. A retry loop is therefore not guaranteed to find a
            free reference in a fixed number of tries — it must keep
            checking, and it should give up rather than spin. In a bucket
            sized for its volume this is rare; in one that is already
            crowded, no retry policy will save the format, and the answer
            is a longer suffix.

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
            If source is empty, suffix_length is less than one, attempt is
            negative or larger than MAX_ATTEMPT, the alphabet has fewer
            than two characters or repeats one, or the namespace is longer
            than MAX_NAMESPACE_BYTES once encoded.

    Warning:
        Shortening an identifier reduces its uniqueness space. This
        function does not mathematically guarantee that two different
        source identifiers cannot produce the same compact reference.
        See collision_probability() and expected_rejected_inserts(),
        passing ``base=len(alphabet)``.
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if attempt < 0:
        raise ValueError("attempt must not be negative")
    if attempt > MAX_ATTEMPT:
        raise ValueError(f"attempt must not be greater than {MAX_ATTEMPT}")

    _validate_alphabet(alphabet)
    namespace_key = _normalize_namespace(namespace)

    source_bytes = _normalize_source(source)

    date_part = _resolve_moment(generated_at, tz).strftime(date_format)

    numeric_value = _source_to_integer(source_bytes, attempt, namespace_key)
    suffix = _encode(numeric_value, alphabet, suffix_length)

    if check:
        # Over the date as well as the suffix: a mistyped day is a
        # transcription error too, and it lands in the wrong bucket.
        suffix += _check_character(date_part + suffix, alphabet)

    parts = [part for part in (prefix, date_part, suffix) if part]

    return separator.join(parts)


def verify_reference(
    reference: str,
    *,
    alphabet: str = DEFAULT_ALPHABET,
    separator: str = "",
    prefix: str = "",
) -> bool:
    """
    Check a reference that was generated with ``check=True``.

    Returns True when the check character agrees with the rest of the
    reference. A mistyped reference is then *invalid*, rather than merely
    absent, and a caller can say so — "that is not a valid reference"
    instead of "no such record", which is a different answer and an
    actionable one.

    The generating call's ``alphabet``, ``separator`` and ``prefix`` have
    to be passed back in, because they decide where the reference ends and
    its label begins.

        >>> reference = generate_reference(
        ...     "01J2H8NQPG6B5X8KGN97SX3R5C",
        ...     generated_at=datetime(2026, 7, 13),
        ...     prefix="RDR",
        ...     separator="-",
        ...     check=True,
        ... )
        >>> verify_reference(reference, prefix="RDR", separator="-")
        True

    This says nothing about whether the reference exists. It says the
    string was not garbled on its way here.
    """
    _validate_alphabet(alphabet)

    body = reference
    if prefix and separator and body.startswith(prefix + separator):
        body = body[len(prefix) + len(separator) :]
    elif prefix and not separator and body.startswith(prefix):
        body = body[len(prefix) :]

    if separator:
        body = body.replace(separator, "")

    if len(body) < 2:
        return False

    payload, check = body[:-1], body[-1]

    return _check_character(payload, alphabet) == check


def collision_probability(
    reference_count: int,
    suffix_length: int,
    base: int = 10,
) -> float:
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
    if base < 2:
        raise ValueError("base must be at least two")
    if reference_count < 2:
        return 0.0

    space = base**suffix_length
    exponent = -reference_count * (reference_count - 1) / (2 * space)
    return 1.0 - exp(exponent)


def expected_colliding_pairs(
    reference_count: int,
    suffix_length: int,
    base: int = 10,
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
    if base < 2:
        raise ValueError("base must be at least two")
    if reference_count < 2:
        return 0.0

    space: int = base**suffix_length
    return reference_count * (reference_count - 1) / (2 * space)


def expected_rejected_inserts(
    reference_count: int,
    suffix_length: int,
    base: int = 10,
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
    if base < 2:
        raise ValueError("base must be at least two")
    if reference_count < 2:
        return 0.0

    space: int = base**suffix_length

    # Written through log1p and expm1 rather than as the formula above.
    # Spelled directly, a roomy bucket subtracts two nearly equal numbers:
    # for two references over ten digits the true answer is 1e-10, and the
    # double precision left over after the cancellation gives -1.7e-07 --
    # a negative count of rejected inserts. log1p and expm1 keep their
    # precision exactly where that cancellation happens.
    taken = -space * expm1(reference_count * log1p(-1.0 / space))
    return reference_count - taken


def expected_collisions(
    reference_count: int,
    suffix_length: int,
    base: int = 10,
) -> float:
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
    return expected_colliding_pairs(reference_count, suffix_length, base)


def max_references(
    suffix_length: int,
    max_probability: float = 0.01,
    base: int = 10,
) -> int:
    """
    Largest number of references that keeps the collision probability at
    or below ``max_probability`` (default 1%) within one date and prefix
    bucket.
    """
    if suffix_length < 1:
        raise ValueError("suffix_length must be greater than zero")
    if not 0.0 < max_probability < 1.0:
        raise ValueError("max_probability must be between 0 and 1")
    if base < 2:
        raise ValueError("base must be at least two")

    space = base**suffix_length
    # Invert the birthday approximation:
    # n ~= 0.5 + sqrt(0.25 - 2 * space * ln(1 - p))
    n = 0.5 + sqrt(0.25 - 2 * space * log(1 - max_probability))
    return max(1, int(n))


def suffix_length_for(
    reference_count: int,
    max_probability: float = 0.01,
    base: int = 10,
) -> int:
    """
    Smallest suffix length that keeps ``reference_count`` references in
    one bucket at or below ``max_probability`` (default 1%).

    max_references() answers this backwards — it takes a length and
    returns a volume — so a caller who knows their volume and wants a
    length had to sweep. This is the direction people actually ask in.

        >>> suffix_length_for(200)
        7

    Pass ``base=len(alphabet)`` when the suffix is not decimal. A
    Crockford base32 suffix holds far more per character, and asking this
    for a decimal length would size it as if it did not:

        >>> suffix_length_for(200, base=32)
        5

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
    if base < 2:
        raise ValueError("base must be at least two")
    if reference_count < 2:
        return 1

    # Invert the birthday approximation for the space:
    #   p = 1 - exp(-n(n-1) / 2s)  =>  s >= n(n-1) / (-2 ln(1 - p))
    space = (
        reference_count
        * (reference_count - 1)
        / (-2 * log(1 - max_probability))
    )
    return max(1, ceil(log(space) / log(base)))


def _validate_alphabet(alphabet: str) -> None:
    """
    An alphabet must be usable as a positional numeral system.
    """
    if len(alphabet) < 2:
        raise ValueError("alphabet must have at least two characters")
    if len(set(alphabet)) != len(alphabet):
        raise ValueError("alphabet must not repeat a character")


def _normalize_namespace(namespace: str) -> bytes:
    """
    Turn the namespace into the BLAKE2b key.

    An empty namespace gives an empty key, and BLAKE2b treats an empty key
    exactly as no key at all — which is what earlier versions hashed with.
    References made before namespaces existed therefore still recompute to
    the same value.
    """
    key = namespace.encode("utf-8")

    if len(key) > MAX_NAMESPACE_BYTES:
        raise ValueError(
            f"namespace must not exceed {MAX_NAMESPACE_BYTES} bytes "
            f"when encoded as UTF-8"
        )

    return key


def _encode(value: int, alphabet: str, length: int) -> str:
    """
    Render ``value`` in base ``len(alphabet)``, padded to ``length``.

    For the decimal alphabet this is exactly the zero-padded decimal string
    earlier versions produced, so the default output has not moved.
    """
    base = len(alphabet)
    remainder = value % (base**length)

    characters = []
    for _ in range(length):
        remainder, index = divmod(remainder, base)
        characters.append(alphabet[index])

    return "".join(reversed(characters))


def _check_character(payload: str, alphabet: str) -> str:
    """
    Luhn mod N over ``alphabet``.

    Catches every single-character error. Catches every adjacent
    transposition except the swap of the alphabet's first and last
    characters — 09 <-> 90 in decimal, 0Z <-> Z0 in Crockford base32 —
    which is the well-known blind spot of the scheme, and the one credit
    card numbers live with. Damm would close it, but a Damm check needs a
    totally anti-symmetric quasigroup of the alphabet's order, and there
    is no way to construct one for an arbitrary alphabet at call time.

    Characters outside the alphabet are skipped rather than rejected, so a
    date_format carrying a separator ("%Y%m%d-%H") does not break the sum.
    """
    base = len(alphabet)
    positions = {character: index for index, character in enumerate(alphabet)}

    total = 0
    factor = 2
    for character in reversed(payload):
        index = positions.get(character)
        if index is None:
            continue

        addend = factor * index
        total += (addend // base) + (addend % base)
        factor = 1 if factor == 2 else 2

    return alphabet[(base - (total % base)) % base]


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


def _source_to_integer(
    source: bytes,
    attempt: int = 0,
    namespace: bytes = b"",
) -> int:
    """
    Convert normalized bytes into a deterministic integer.

    BLAKE2b is used so identifiers of different formats are processed
    consistently.

    Neither the attempt nor the namespace touches the message. The attempt
    goes in the salt and the namespace in the key, both of which are
    separate inputs to the compression function. Appending either to the
    source would let one be spelled as part of another —
    generate_reference(b"abc", attempt=1) would agree with
    generate_reference(b"abc#1") — inventing a fresh class of collision
    inside the features meant to resolve them.

    Both defaults reproduce what earlier versions hashed. An attempt of 0
    salts with sixteen zero bytes, which BLAKE2b treats as unsalted; an
    empty namespace is an empty key, which BLAKE2b treats as unkeyed.
    References written before either parameter existed still recompute to
    the same value.
    """
    digest = blake2b(
        source,
        digest_size=16,
        person=b"compactref-v1",
        salt=attempt.to_bytes(16, byteorder="big"),
        key=namespace,
    ).digest()

    return int.from_bytes(digest, byteorder="big")
