# Roadmap

1.0.0 is a lock, not a milestone: it is a promise not to break the API.
So what goes before it is whatever we would regret being stuck with.
See the [changelog](CHANGELOG.md) for what has shipped.

## Shipped

- **0.2.0** — `attempt`, so a reference a unique constraint rejected can
  be regenerated. Retrying without it returns the same string forever.
- **0.2.1** — booleans rejected as sources (`True` was returning the
  reference belonging to `1`). `expected_collisions()` documented as the
  pair count it always was, rather than the retry count it never was.
- **0.3.0** — `tz`. The system timezone is no longer read, so a reference
  no longer depends on the machine that produced it.
  `expected_rejected_inserts()`, `suffix_length_for()`.
- **0.4.0** — `alphabet` (Crockford base32), `check` and
  `verify_reference()`, `namespace` (`prefix` never reached the hash, so
  an order and an invoice from one customer drew the same suffix). `base`
  on every sizing helper.
- **0.5.0** — `CompactRef`, so generate and verify cannot disagree.
  `expected_rejected_inserts()` no longer returns a negative count for a
  roomy bucket. Property-based tests, and a retry loop that runs against a
  real database rather than sitting in the README as pseudocode.

## 1.0.0 — the lock

The API is one we are content never to break. What remains is to say so.

- Remove `expected_collisions()`, deprecated since 0.3.0.
- Write the exception contract down: `TypeError` when the type is
  unusable, `ValueError` when the type is right but the value is not. It
  is already true, and pinned by test; 1.0.0 is where it becomes a
  promise.
- Decide whether `verify_reference()` and the loose-argument
  `generate_reference()` stay public. They are the primitives `CompactRef`
  is built from, and removing them would be gratuitous — but the two
  footguns 0.5.0 documents live in `verify_reference()`, and cannot be
  fixed there. A deprecation is defensible. Keeping it, with the warning
  the docstring now carries, is also defensible.

## Considered, not planned

### A Damm check character

Luhn cannot see a `09 ↔ 90` transposition — about 2.7% of adjacent swaps
in decimal, 0.3% in base32. Damm sees all of them.

It needs a totally anti-symmetric quasigroup of the alphabet's order,
though, and there is no way to construct one for an arbitrary alphabet at
call time. Shipping Damm would mean shipping a fixed table per supported
alphabet and refusing custom ones. That is a real cost for a real but
small gain, and single-character errors — 100% caught either way — are the
typo that actually happens.

### Bucket-aware sizing

Every sizing helper takes a count *per bucket*, and `date_format` decides
the bucket. Converting by hand is the commonest way to size a reference
badly: a monthly bucket holds roughly thirty times the daily volume, so it
collides far sooner than the extra character it usually buys back.

A helper taking `date_format` and a rate could do the conversion. Worth
*not* doing if it guesses more than it explains; the docs may be the
better fix.

### A CLI

Plausible, but nobody has asked. A library that generates a reference from
an identifier is not obviously something you reach for at a shell prompt.
