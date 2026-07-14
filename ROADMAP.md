# Roadmap

CompactRef is 1.0. The API is locked: it does not break without a 2.0.
See the [changelog](CHANGELOG.md) for how it got here.

## What is locked

- **Names** — `CompactRef`, `generate_reference()`, the sizing helpers.
- **Parameters** — their names, their order, their defaults.
- **The default format** — `generate_reference("…")` returns what it
  returned in 0.1.0. Every argument added since defaults to doing nothing.
- **Exceptions** — `TypeError` for an unusable type, `ValueError` for a bad
  value.
- **Determinism** — the same inputs give the same reference on every
  machine.

## Waiting for 2.0

Nothing. `verify_reference()` was removed in 1.0.0 rather than carried
through 1.x: it could not be made safe, and 1.0 was the last version
allowed to remove it.

## Additive, and therefore not urgent

### A `CompactRefError` base class

Proposed, and declined for 1.0 — but the door is open, because adding a
base to an exception is backward compatible:
`class InvalidReferenceError(CompactRefError, ValueError)` keeps every
`except ValueError` working.

Declined because the only exception anyone catches is
`InvalidReferenceError`, the one a *user* can trigger. The rest are
programmer errors — a bad alphabet, a boolean where an integer belongs —
which you fix at startup rather than catch. And a base that did not also
cover the seven `TypeError` raise sites would be a lie: `except
CompactRefError` would miss `suffix_length=True`. Covering them needs a
fourth class inheriting `TypeError`, because 1.0 promises `TypeError` for
an unusable type. That is a larger hierarchy than the problem deserves.

Worth revisiting if a caller ever produces a real use for
`except CompactRefError` that `except ValueError` does not already serve.

### Tolerant verification for Crockford base32

Crockford designed his alphabet so decoding survives a human: lowercase
accepted, `I` and `L` read as `1`, `O` read as `0`. CompactRef takes the
alphabet but not the tolerance — it generates upper case and verifies
exactly, so a support agent who types `hcp3cs` is told the reference is
invalid. That is the confusion the check character exists to prevent.

It did not go into 1.0 because it needs care rather than haste. Case
folding must not be applied to an alphabet that distinguishes case (a
custom one containing both `a` and `A`), and the `I`/`L`/`O` mapping
belongs to Crockford specifically, not to alphabets in general — so it is
a property of the alphabet, not of the verifier.

It is safe to add later: teaching `verify()` to accept *more* changes
nothing that `generate()` produces and invalidates no stored reference.

## Considered, not planned

Nothing below is scheduled. They are written down so the reasoning is not
relitigated.

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

### Anything that changes what a reference looks like

Off the table now. That is what 1.0 means. A new alphabet or a new check
scheme can be *offered* — the arguments exist — but the default output is
fixed, because callers have it in their databases.
