# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.0]: https://github.com/neosergio/compactref/releases/tag/v0.2.0
[0.1.0]: https://github.com/neosergio/compactref/releases/tag/v0.1.0
