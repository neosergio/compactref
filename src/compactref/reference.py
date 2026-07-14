"""A configured reference scheme.

Verifying a reference means recomputing its check character, which means
knowing the alphabet, prefix, separator, suffix length and date format it
was made with. A free function has to be *told* all of that, and it cannot
tell when it has been told wrong. compactref shipped one, briefly, and it
failed two ways that no amount of care inside it could have fixed:

- Given a different alphabet, prefix or separator than the reference was
  made with, it returned False. False means "this reference is a typo", so
  a caller told a customer their perfectly good reference was invalid when
  it was the caller's own configuration that was wrong.

- Given a reference with no check character in it — the default — it read
  the last character of the suffix as one, and passed about one time in
  ``len(alphabet)``. It was noise, and it did not say so.

The defect is not in the arithmetic; it is that the configuration was
loose. Verification and generation must agree, and only holding them in
one place makes that so. A CompactRef is that place: generate() and
verify() read the same object, so there is nothing left to get out of
step, and verify() on a scheme with no check character raises rather than
guessing.

That function (verify_reference) was removed in 1.0.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo

from .core import (
    _PROBE_DATES,
    DEFAULT_ALPHABET,
    DEFAULT_DATE_FORMAT,
    DEFAULT_SUFFIX_LENGTH,
    DEFAULT_TIMEZONE,
    SourceIdentifier,
    _check_character,
    _render_date,
    _validate_checkable,
    _validate_configuration,
    collision_probability,
    expected_colliding_pairs,
    expected_rejected_inserts,
    generate_reference,
    max_references,
    suffix_length_for,
)


class InvalidReferenceError(ValueError):
    """A string is not shaped like a reference from this scheme.

    A ValueError, so a caller who does not care about the distinction can
    still write ``except ValueError``.

    Raised by parse(), not by verify(): verify() answers a yes/no question
    and returns False. parse() is for callers who need to know *why*, and
    the difference is one a support desk cares about — "that is one of our
    order numbers and you have a digit wrong" is a different sentence from
    "that is not an order number".
    """


@dataclass(frozen=True)
class ParsedReference:
    """The pieces of a reference, once it has been read apart.

    ``check_character`` is None when the scheme carries no check character.
    Parsing still works — the structure is checkable without one — but
    there is nothing to weigh.
    """

    prefix: str
    date_part: str
    suffix: str
    check_character: str | None


@dataclass(frozen=True)
class CompactRef:
    """A reference scheme: one configuration, used to generate and to verify.

    Configure it once, and the two operations cannot disagree:

        >>> orders = CompactRef(
        ...     prefix="ORD",
        ...     separator="-",
        ...     namespace="orders",
        ...     check=True,
        ... )
        >>> reference = orders.generate("01J2H8NQPG6B5X8KGN97SX3R5C")
        >>> orders.verify(reference)
        True

    The configuration is checked when the object is built, so a bad
    alphabet raises on the line that made it rather than on the
    ten-thousandth call.

    Frozen, so it can be built once at import and shared. The sizing
    helpers are bound to it too, and already know their own base:

        >>> orders.suffix_length_for(200)
        7
    """

    suffix_length: int = DEFAULT_SUFFIX_LENGTH
    alphabet: str = DEFAULT_ALPHABET
    check: bool = False
    namespace: str = ""
    date_format: str = DEFAULT_DATE_FORMAT
    prefix: str = ""
    separator: str = ""
    tz: tzinfo = DEFAULT_TIMEZONE

    def __post_init__(self) -> None:
        # A frozen dataclass annotates its fields; it does not enforce them.
        # CompactRef(suffix_length=True) would build happily and hand back a
        # one-character reference, because bool subclasses int — the trap
        # 0.2.1 closed for the source. The class promises its configuration
        # is checked where it is written, so check it.
        _validate_configuration(
            suffix_length=self.suffix_length,
            alphabet=self.alphabet,
            check=self.check,
            namespace=self.namespace,
            date_format=self.date_format,
            prefix=self.prefix,
            separator=self.separator,
            tz=self.tz,
            attempt=0,
        )

        # A date_format that does not render on this platform is broken
        # here, check character or not. Fail on the line that chose it.
        _render_date(_PROBE_DATES[0], self.date_format)

        if self.check:
            # The rules a reference must obey to be worth checking: a date of
            # a fixed width, a date the alphabet can spell, and a separator
            # the suffix cannot contain. Shared with generate_reference(), so
            # the function cannot mint a checked reference that this class
            # would refuse to verify.
            _validate_checkable(
                alphabet=self.alphabet,
                date_format=self.date_format,
                separator=self.separator,
            )
        else:
            # Without a check character there is nothing to void, so the
            # date is the caller's business. The separator is not: a
            # separator drawn from the alphabet would make
            #
            #     ORD02026071400471283
            #
            # which no person can read and no regex can split, whatever this
            # class can privately parse. That is a readability rule, and it
            # holds with or without a check character.
            self._reject_a_separator_the_suffix_can_contain()

    def _reject_a_separator_the_suffix_can_contain(self) -> None:
        """
        A separator the suffix can also contain is not a separator.

        A readability rule, not a correctness one, and worth being honest
        about which. verify() reads a reference by position, so it would in
        fact cope: a decimal scheme separated by "0" round trips, and stays
        strict about malformed input. The parser does not need this guard.

        A human does. The point of the library is a reference a person can
        read down a phone line, and

            ORD02026071400471283

        is not one — the separators are indistinguishable from the data.
        Nor can anything downstream take the reference apart: a support
        tool, a log grep or a regex that splits on the separator has no way
        to tell a separator from a digit, even though this class does.
        """
        if not self.separator:
            return

        shared = sorted(set(self.separator) & set(self.alphabet))
        if shared:
            raise ValueError(
                f"separator must not contain characters from the alphabet, "
                f"but shares {''.join(shared)!r}. The reference would still "
                f"verify — it is read by position — but nothing else could "
                f"take it apart: a separator that looks exactly like the "
                f"data is no use to a person reading it aloud, or to a regex "
                f"splitting on it."
            )

    @property
    def base(self) -> int:
        """How many values one character of the suffix carries."""
        return len(self.alphabet)

    @property
    def date_length(self) -> int | None:
        """
        Characters the date part occupies, or None if it varies.

        None means the ``date_format`` renders to different widths on
        different dates — ``%B`` is seven characters in January and eight in
        December. A checked scheme cannot be built that way, so this is only
        ever None when ``check`` is False.
        """
        widths = {
            len(_render_date(moment, self.date_format))
            for moment in _PROBE_DATES
        }

        return widths.pop() if len(widths) == 1 else None

    @property
    def reference_length(self) -> int | None:
        """
        Characters a reference from this scheme occupies, or None if it varies.

        Written for the column that stores it:

            reference: Mapped[str] = mapped_column(
                String(ORDERS.reference_length),
                unique=True,
            )

        None means the date renders to different widths on different dates,
        so the reference has no fixed length either. That is not a
        compromise: ``String(None)`` is an unbounded VARCHAR, which is
        exactly what a reference of no fixed length wants. A checked scheme
        is never None, because it cannot be built with a date that moves.
        """
        date_length = self.date_length
        if date_length is None:
            return None

        parts = [len(self.prefix)] if self.prefix else []
        if date_length:
            parts.append(date_length)
        parts.append(self.suffix_length + (1 if self.check else 0))

        # generate() drops the empty parts before joining, so only the
        # separators between the parts that survive are counted.
        return sum(parts) + len(self.separator) * (len(parts) - 1)

    def generate(
        self,
        source: SourceIdentifier,
        *,
        generated_at: datetime | None = None,
        attempt: int = 0,
    ) -> str:
        """Generate a reference under this scheme."""
        return generate_reference(
            source,
            generated_at=generated_at,
            tz=self.tz,
            suffix_length=self.suffix_length,
            alphabet=self.alphabet,
            check=self.check,
            namespace=self.namespace,
            date_format=self.date_format,
            prefix=self.prefix,
            separator=self.separator,
            attempt=attempt,
        )

    def parse(self, reference: str) -> ParsedReference:
        """
        Read a reference apart, or say why it is not one.

        Structural only. It tells you the string is shaped exactly as this
        scheme shapes one — the right prefix, the separators where they
        belong, each field at its width, nothing trailing, every character
        of the suffix in the alphabet — and hands back the pieces. It does
        *not* decide whether the check character is right; verify() does
        that, on top of this.

        The distinction is the one a support desk needs. A reference that
        parses but fails verify() is *shaped* like yours and mistyped. A
        reference that does not parse is not yours at all. "That is one of
        our order numbers, and you have a digit wrong" is a different
        sentence from "that is not an order number", and a caller who can
        only say False cannot choose between them.

            >>> orders = CompactRef(prefix="ORD", separator="-", check=True)
            >>> parsed = orders.parse("ORD-20260714-0471283")
            >>> parsed.date_part
            '20260714'
            >>> parsed.suffix
            '047128'
            >>> parsed.check_character
            '3'

        Raises:
            InvalidReferenceError:
                If the string is not shaped like a reference from this
                scheme. A ValueError, so ``except ValueError`` still catches
                it.

            ValueError:
                If this scheme's date_format renders to different widths on
                different dates. There is then no way to say where the date
                ends, so no reference can be read by position. Only possible
                without a check character; a checked scheme cannot be built
                that way.
        """
        date_width = self.date_length
        if date_width is None:
            raise ValueError(
                f"a reference from this scheme cannot be read by position: "
                f"{self.date_format!r} renders to different widths on "
                f"different dates, so there is no telling where the date "
                f"ends. Use a fixed-width format."
            )

        cursor = 0
        joined = False  # whether a separator is due before the next field

        def take(cursor: int, width: int, what: str) -> tuple[str, int]:
            taken = reference[cursor : cursor + width]
            if len(taken) != width:
                raise InvalidReferenceError(
                    f"{reference!r} is too short: expected {width} "
                    f"characters of {what}."
                )
            return taken, cursor + width

        def take_separator(cursor: int) -> int:
            if not self.separator:
                return cursor
            end = cursor + len(self.separator)
            if reference[cursor:end] != self.separator:
                raise InvalidReferenceError(
                    f"{reference!r} is missing the separator "
                    f"{self.separator!r} at position {cursor}."
                )
            return end

        if self.prefix:
            if not reference.startswith(self.prefix):
                raise InvalidReferenceError(
                    f"{reference!r} does not begin with the prefix "
                    f"{self.prefix!r}."
                )
            cursor = len(self.prefix)
            joined = True

        if date_width:
            if joined:
                cursor = take_separator(cursor)
            date_part, cursor = take(cursor, date_width, "date")
            joined = True
        else:
            date_part = ""

        if joined:
            cursor = take_separator(cursor)

        suffix, cursor = take(cursor, self.suffix_length, "suffix")

        check_character: str | None = None
        if self.check:
            check_character, cursor = take(cursor, 1, "check character")

        # Nothing may follow. A trailing separator is a garbled reference,
        # not a decoration.
        if cursor != len(reference):
            raise InvalidReferenceError(
                f"{reference!r} has {len(reference) - cursor} character(s) "
                f"trailing after the reference ends."
            )

        # A character the alphabet does not contain is not a check failure,
        # it is not a reference. Luhn *skips* what it cannot index, and
        # skipping is indistinguishable from contributing zero — so a
        # garbled character could leave the check unmoved and verify.
        #
        # For a checked scheme the date is covered too. Such a scheme cannot
        # be built on a date the alphabet cannot spell, so every character of
        # a genuine date is in the alphabet; one that is not means the
        # reference was garbled on its way here. A scheme with a date_format
        # of "0" and a decimal alphabet makes this concrete: "X0471284" would
        # otherwise verify against a scheme that produced "00471284", because
        # X is skipped and "0" contributes zero.
        #
        # An unchecked scheme is left alone: its date may legitimately carry
        # literals the alphabet has no index for, and there is no checksum
        # for them to fool.
        body = suffix + (check_character or "")
        if self.check:
            body += date_part

        stray = sorted(set(body) - set(self.alphabet))
        if stray:
            raise InvalidReferenceError(
                f"{reference!r} contains {''.join(stray)!r}, which the "
                f"alphabet does not."
            )

        return ParsedReference(
            prefix=self.prefix,
            date_part=date_part,
            suffix=suffix,
            check_character=check_character,
        )

    def verify(self, reference: str) -> bool:
        """
        Check a reference made under this scheme.

        True means the string is exactly what this scheme would have
        produced, and its check character agrees. It says nothing about
        whether the reference exists.

        Built on parse(), so the two cannot drift: the structure is read by
        position — the right prefix, the separators where they belong, each
        field at its width, nothing trailing — and only then is the check
        character weighed. A stray separator is a transcription error like
        any other, and a verifier that quietly deleted the extra one would
        call ``ORD--20260714-…`` valid, which is the confusion the check
        character exists to prevent.

        Use parse() when you need to tell *why* a reference failed: one that
        parses but does not verify is shaped like yours and mistyped; one
        that does not parse is not yours at all.

        Raises:
            ValueError:
                If this scheme has no check character. There would be
                nothing to verify: reading the last character of the suffix
                as a check passes about one time in ``base``, which is
                noise dressed up as an answer. A scheme that wants to
                verify must be built with ``check=True``.
        """
        if not self.check:
            raise ValueError(
                "this scheme generates no check character, so there is "
                "nothing to verify. Build it with check=True. Verifying "
                "an unchecked reference would read the last character of "
                "the suffix as a check and pass roughly one time in "
                f"{self.base}."
            )

        try:
            parsed = self.parse(reference)
        except InvalidReferenceError:
            return False

        expected = _check_character(
            parsed.date_part + parsed.suffix,
            self.alphabet,
        )

        return parsed.check_character == expected

    def collision_probability(self, reference_count: int) -> float:
        """Chance that any two of ``reference_count`` share a suffix."""
        return collision_probability(
            reference_count,
            self.suffix_length,
            base=self.base,
        )

    def expected_colliding_pairs(self, reference_count: int) -> float:
        """How many pairs are expected to share a suffix."""
        return expected_colliding_pairs(
            reference_count,
            self.suffix_length,
            base=self.base,
        )

    def expected_rejected_inserts(self, reference_count: int) -> float:
        """How many inserts a unique constraint is expected to reject."""
        return expected_rejected_inserts(
            reference_count,
            self.suffix_length,
            base=self.base,
        )

    def max_references(self, max_probability: float = 0.01) -> int:
        """Largest volume this scheme carries at or below the risk."""
        return max_references(
            self.suffix_length,
            max_probability,
            base=self.base,
        )

    def suffix_length_for(
        self,
        reference_count: int,
        max_probability: float = 0.01,
    ) -> int:
        """
        Suffix length this scheme *should* have for a given volume.

        Advisory: it does not change ``suffix_length``. Compare it with
        the one you configured.
        """
        return suffix_length_for(
            reference_count,
            max_probability,
            base=self.base,
        )
