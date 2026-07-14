"""A configured reference scheme.

generate_reference() and verify_reference() take their configuration as
loose arguments, and the two calls have no way to agree with each other.
That is not a theoretical worry:

- verify_reference() handed a different alphabet, prefix or separator than
  the reference was made with returns False. False means "this reference
  is a typo", so a caller tells a customer their perfectly good reference
  is invalid, when it was the caller's own configuration that was wrong.

- verify_reference() handed a reference with no check character in it — the
  default — reads the last character of the suffix as one, and passes
  about one time in ``len(alphabet)``. It is noise, and it does not say so.

Neither can be fixed inside the functions, because neither function can
see what the other was told. A CompactRef holds the configuration once,
and generate() and verify() read it from the same place, so there is
nothing left to get out of step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo

from .core import (
    DEFAULT_ALPHABET,
    DEFAULT_DATE_FORMAT,
    DEFAULT_SUFFIX_LENGTH,
    DEFAULT_TIMEZONE,
    SourceIdentifier,
    _check_character,
    _normalize_namespace,
    _validate_alphabet,
    collision_probability,
    expected_colliding_pairs,
    expected_rejected_inserts,
    generate_reference,
    max_references,
    suffix_length_for,
)


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
        if self.suffix_length < 1:
            raise ValueError("suffix_length must be greater than zero")

        _validate_alphabet(self.alphabet)
        _normalize_namespace(self.namespace)

    @property
    def base(self) -> int:
        """How many values one character of the suffix carries."""
        return len(self.alphabet)

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

    def verify(self, reference: str) -> bool:
        """
        Check a reference made under this scheme.

        True means the string was not garbled on its way here. It says
        nothing about whether the reference exists.

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

        body = self._strip_label(reference)

        if len(body) != self._body_length:
            return False

        payload, check = body[:-1], body[-1]

        return _check_character(payload, self.alphabet) == check

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

    @property
    def _body_length(self) -> int:
        """Characters in the date and suffix, once the label is stripped."""
        # The date is whatever strftime makes of the format; measure it
        # rather than guess, since a format can carry literals.
        date_length = len(
            datetime(2026, 1, 1)
            .strftime(self.date_format)
            .replace(self.separator, "")
            if self.separator
            else datetime(2026, 1, 1).strftime(self.date_format)
        )

        return date_length + self.suffix_length + (1 if self.check else 0)

    def _strip_label(self, reference: str) -> str:
        """Remove the prefix and the separators, leaving date and suffix."""
        body = reference

        if self.prefix:
            label = self.prefix + self.separator
            if body.startswith(label):
                body = body[len(label) :]

        if self.separator:
            body = body.replace(self.separator, "")

        return body
