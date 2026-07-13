# Roadmap

1.0.0 is a lock, not a milestone: it is a promise not to break the API.
So what goes before it is whatever we would regret being stuck with.
See the [changelog](CHANGELOG.md) for what has shipped.

## Shipped

- **0.2.0** — the `attempt` argument, so a reference a unique constraint
  rejected can be regenerated. `expected_collisions()`.
- **0.2.1** — booleans rejected as sources; `expected_collisions()`
  documented as the pair count it always was.
- **0.3.0** — the `tz` argument. The system timezone is no longer read,
  so a reference no longer depends on the machine that produced it.
  `expected_rejected_inserts()`, `suffix_length_for()`.

## 0.4.0 — make it worth being human-facing

### An `alphabet` argument

The suffix is decimal, so six characters carry a million values. Six
Crockford base32 characters carry 1.07 *billion* — the same length, the
same shape, 32× the safe volume:

| Length | digits | Crockford base32 |
| --- | --- | --- |
| 4 | 14 refs/bucket | 145 |
| 6 | 142 | 4,646 |
| 7 | 448 | 26,280 |

This is the single biggest lever on the collision problem the README
spends so many words apologising for.

It is a real trade, though, not a free win, and digits must stay the
default so nobody's stored references move:

- Digits are unambiguous, universally typeable, and work on a numeric
  keypad — which matters if a reference is ever read into a phone menu or
  a numbers-only field.
- Letters are denser but harder to convey aloud, and can spell things.
  Crockford drops I, L, O and U precisely to kill 1/I and 0/O confusion
  and most accidental obscenity, which is why it is the right base32 to
  reach for.

### A check character

CompactRef exists for references humans read aloud, type into support
forms, and write on paper — and there is no way to tell a mistyped one
from a missing one. A support agent who fat-fingers `RDR-20260713-177`
gets "not found", which is indistinguishable from "no such product".

A check character (Damm, or mod-97) turns that into "that is not a valid
reference" — a different answer, and an actionable one. IBAN, ISBN and
card numbers all carry one, for exactly this reason. Its absence is the
most conspicuous gap in a library with this name.

## 1.0.0 — the lock

Ship it when the API is one we are content never to break: compact
(base32), human-proof (check character), correct (no environment read),
and honest about collisions rather than merely apologetic.

At that point:

- Remove `expected_collisions()`, deprecated since 0.3.0.

## Considered, not planned

### Bucket-aware sizing

Every sizing helper takes a count *per bucket*, and `date_format` decides
the bucket — a caller on `%Y%m` has one bucket a month, a caller on
`%Y%m%d-%H` has one an hour. Converting by hand is the commonest way to
size a reference badly: a monthly bucket holds roughly thirty times the
daily volume, so it collides far sooner than the extra digit it usually
buys back.

A helper that took `date_format` and a rate could do the conversion.
Worth *not* doing if it guesses more than it explains; the docs may be
the better fix.
