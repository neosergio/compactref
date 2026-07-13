# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-07-13

Nothing here moves a reference you have already stored. Every new
argument defaults to what earlier versions did, and a test pins the
strings 0.1.0 produced.

### Added

- **`namespace`** — and the bug it fixes. `prefix` is only a label: it
  never reached the hash. So an order and an invoice derived from one
  customer's ULID drew the *same* suffix, every time:

      ORD-20260713-133083
      INV-20260713-133083

  That is a certainty, not a one-in-a-million coincidence, and none of the
  collision helpers accounted for it. A namespace separates them. It is
  carried in BLAKE2b's key, so one namespace cannot be spelled as part of
  another source, and an empty namespace — the default — is an empty key,
  which BLAKE2b treats as no key at all.

- **`alphabet`**, with `CROCKFORD_BASE32` and `DIGITS`. Six decimal
  characters hold a million values; six Crockford characters hold 1.07
  billion, which is 32× the volume a bucket carries at the same risk and
  the same length. Crockford drops `I`, `L`, `O` and `U` — the first three
  because they are misread as `1` and `0`, the last so the encoding does
  not spell obscenities.

  It is a trade, not a free win: digits can be typed on a numeric keypad
  and read down a phone line without spelling anything. Digits stay the
  default.

- **`check`** and **`verify_reference()`**. Without a check character a
  mistyped reference is merely *absent*, which a caller cannot tell from a
  record that never existed. With one it is *invalid*, which is a
  different answer and an actionable one.

  Luhn mod N over the alphabet, covering the date as well as the suffix,
  so a mistyped day is caught too. Measured, not assumed: it catches
  **every** single-character error, and every adjacent transposition
  except the swap of the alphabet's first and last characters (`09 ↔ 90`
  in decimal, `0Z ↔ Z0` in base32) — the known blind spot of the scheme on
  the back of a credit card, costing ~2.7% of transpositions in decimal
  and 0.3% in base32.

  It adds a character but **no capacity**: it is computed from the
  reference, not drawn from the hash, so the collision maths still depend
  on `suffix_length` alone.

- `base` on every sizing helper — `collision_probability()`,
  `expected_colliding_pairs()`, `expected_rejected_inserts()`,
  `max_references()` and `suffix_length_for()`. They assumed ten, and a
  base32 suffix sized as if it were decimal is sized wrong by orders of
  magnitude. Defaults to 10.

- `MAX_NAMESPACE_BYTES`, `DEFAULT_ALPHABET`.

### Documented

- A reference without a date, via `date_format=""`. This always worked;
  nothing said so. Mind that it puts every reference you ever issue in one
  bucket, so size for the all-time total, not a day's worth.

## [0.3.0] - 2026-07-13

### Changed — breaking

- **The date part is now UTC by default, and the system timezone is never
  read.**

  Before 0.3.0 the default clock was `datetime.now()` — naive *local*
  time — so a reference depended on the machine that produced it. The
  same identifier, at the same instant, became `20260713…` on a Lima
  server and `20260714…` on a Tokyo one. Determinism is what this library
  is for, and it did not hold across a fleet.

  `generate_reference()` takes a `tz` argument, defaulting to UTC.
  `generated_at=None` now reads `datetime.now(tz)`; an aware `generated_at`
  is converted into `tz`; a naive one is taken at face value, as a wall
  clock the caller chose. Nothing consults the environment.

  **Who this moves.** If your servers do not run in UTC, new references
  land in a different bucket than they used to — about 21% of them for a
  UTC−5 server and 38% for UTC+9, that being how often the local date
  differs from the UTC date. Stored references are untouched; only what
  new calls return changes. Callers who *recompute* a reference instead of
  storing it should pin the old behaviour with the zone their servers ran
  in, for example `tz=ZoneInfo("America/Lima")`. Callers who store it, as
  the README has always advised, need do nothing.

### Added

- `expected_rejected_inserts(reference_count, suffix_length)` — how many
  inserts a unique constraint rejects, which is the number of `attempt`
  retries a caller will actually make, and so the number to plan with.
  Unlike the pair count it can never exceed the reference count, because
  an insert can only be rejected once. Verified against simulation.

- `suffix_length_for(reference_count, max_probability=0.01)` — the
  smallest suffix length that holds a given volume. `max_references()`
  answers this backwards, taking a length and returning a volume, so the
  README used to tell callers to write a loop. It no longer does.

- `DEFAULT_TIMEZONE`.

### Deprecated

- `expected_collisions()` is renamed to `expected_colliding_pairs()`. The
  old name suggested a count of collisions a caller would have to handle,
  and until 0.2.1 the documentation said exactly that. It counts pairs,
  which runs far ahead of the rejected inserts once a bucket fills. The
  old name still works, warns, and goes away in 1.0.0.

## [0.2.1] - 2026-07-13

### Fixed

- `generate_reference()` rejects booleans. `bool` subclasses `int`, so
  `True` reached the integer branch and returned the reference belonging
  to `1`, and `False` the one belonging to `0` — silently issuing a
  reference for a different record. Both now raise `TypeError`.

- `expected_collisions()` documented itself as an error rate: "the number
  of writes per bucket a caller should expect to retry". It is not. It
  returns the expected number of *colliding pairs*, and a suffix drawn
  `k` times is `k * (k - 1) / 2` pairs but only `k - 1` rejected inserts.
  The two agree while a bucket is sparse and diverge sharply once it
  fills: two thousand references over three digits is 1999 pairs but
  about 1135 rejected inserts, so the old wording overstated the retries
  by more than half. The behaviour is unchanged and correct; the
  docstring and README now say what it computes, and warn against sizing
  a retry budget with it.

### Added

- Tests pinning the pair semantics at 0, 1, 2 and crowded volumes, the
  gap between pairs and rejected inserts, boolean rejection, and the
  error-type contract: `TypeError` when the type is unusable, `ValueError`
  when the type is right but the value is not.

## [0.2.0] - 2026-07-13

### Added

- `generate_reference()` takes an `attempt` argument. A reference is
  derived from its source, so the same source always produces the same
  reference and retrying a rejected one returns the identical string.
  Raising the attempt derives a different reference from the same
  source, which is what makes a unique constraint recoverable: when
  attempt 0 is taken, offer attempt 1. Each attempt is deterministic in
  its own right, so a reference stays recomputable from the source and
  the attempt that won.

- `expected_collisions(reference_count, suffix_length)` returns how many
  pairs are expected to share a suffix in one bucket.
  `collision_probability()` saturates — past a certain volume every
  format reports "almost certainly", which stops separating a format
  that collides twice a month from one that collides fifty times. With
  a unique constraint in place, the expected count is an error rate: the
  number of inserts per bucket that will need a retry.

- `MAX_ATTEMPT`, the largest accepted `attempt`.

### Changed

- The README states plainly that compactref generates compact
  references, not globally unique identifiers, and shows the retry loop
  that `attempt` now makes possible.

### Compatibility

- `attempt` defaults to 0, which reproduces the references 0.1.0
  produced, byte for byte. The attempt is passed as BLAKE2b salt, and an
  attempt of 0 salts with zero bytes, which BLAKE2b treats exactly as the
  unsalted digest of earlier versions. References already stored by
  callers on 0.1.0 remain valid and still recompute to the same value; a
  test pins this.

  The attempt is deliberately *not* appended to the source. Appending
  would make `generate_reference(b"abc", attempt=1)` and
  `generate_reference(b"abc1")` agree, introducing a new class of
  collision inside the feature meant to resolve them.

## [0.1.0] - 2026-07-12

### Added

- `generate_reference()` derives a compact reference from a ULID, UUID,
  string, bytes or non-negative integer, with a configurable prefix,
  date format, separator and suffix length.
- `collision_probability()` and `max_references()` size the suffix using
  the birthday model.

[0.4.0]: https://github.com/neosergio/compactref/releases/tag/v0.4.0
[0.3.0]: https://github.com/neosergio/compactref/releases/tag/v0.3.0
[0.2.1]: https://github.com/neosergio/compactref/releases/tag/v0.2.1
[0.2.0]: https://github.com/neosergio/compactref/releases/tag/v0.2.0
[0.1.0]: https://github.com/neosergio/compactref/releases/tag/v0.1.0
