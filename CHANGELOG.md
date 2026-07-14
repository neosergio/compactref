# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-14

The API is settled. From here it does not break without a 2.0.0.

### The promise

Locked, and changed only in a major version:

- **Names.** `CompactRef`, `generate_reference()`, and the sizing helpers.
- **Parameters.** Their names, their order, and their defaults.
- **The default format.** `generate_reference("…")` returns what it
  returned in 0.1.0. Every argument added since — `attempt`, `namespace`,
  `alphabet`, `check`, `tz` — defaults to doing nothing, and a test pins
  the strings 0.1.0 produced. Your stored references keep resolving.
- **The exception contract.** `TypeError` when the type is unusable;
  `ValueError` when the type is right but the value is not. Pinned by test.
- **Determinism.** The same source, date, attempt and configuration give
  the same reference on every machine. Nothing reads the environment.
- **The check character.** Changing how it is computed would invalidate
  references already in somebody's database, so the policy is settled and
  pinned by test:

  - It covers `date_part + suffix` — Luhn mod N over the alphabet.
  - It does **not** cover the prefix. The prefix is a *label*; `namespace`
    is what separates one kind of reference from another, and it does so in
    the hash. A label may be renamed, translated, or shown differently in
    one place than another, and none of that should move the reference
    underneath.
  - It does **not** cover the separators, which carry no information.
  - The prefix and separators are nevertheless *checked* — structurally.
    `verify()` matches the prefix literally, requires each separator exactly
    where it belongs, takes each field at its known width, and permits
    nothing to trail.
  - Every character of the date and the suffix is in the alphabet, because a
    checked scheme cannot be built otherwise. The checksum never skips
    anything, so Luhn's guarantee is total rather than partial.
  - Verification is **exact and case-sensitive**. It accepts what
    `generate()` produced and nothing else — no normalising, trimming or
    repairing.

  **Golden tests hold it there.** Every path that produces a reference is
  pinned to the string it produces: each kind of source, each `attempt`,
  each `namespace`, each alphabet, each check character, each timezone
  bucket. Before 1.0 only the default path was pinned — a refactor of the
  encoder, the checksum, or the BLAKE2b salt could have silently changed
  what was in somebody's database, and every test would still have passed.
  I checked the tests can fail: changing the hash personalisation, the
  digest size or the byte order fails all 24, and breaking the Luhn
  alternation fails the 4 checked ones.

  They run on Linux, macOS and Windows, across Python 3.10 to 3.14 — the
  promise is that a reference is the same on *every* machine, and testing it
  on one platform would leave two thirds of that untested. `strftime` and
  the default text encoding are exactly where a platform would differ.

  The public API surface is pinned too, so a name cannot be exported by
  accident and thereby become a name we are obliged to keep.

  Running on Windows found something at once, which is the point of running
  on Windows: `zoneinfo` reads the operating system's timezone database, and
  Windows has none — so `tz=ZoneInfo("Europe/Madrid")`, which this README
  *recommends* for business-day buckets, raises `ZoneInfoNotFoundError`
  there until `tzdata` is installed. We were recommending a feature that
  did not work on a whole platform, and had never noticed. Documented now,
  with a `compactref[tz]` extra for convenience.

  Windows found a second thing, and this one is a library bug rather than a
  test problem. `%-d` — an unpadded day — is a glibc extension: it renders on
  Linux and macOS and raises `ValueError("Invalid format string")` on
  Windows, from inside the standard library, with nothing in the message
  about what the caller chose. So a scheme that worked in development would
  crash in production, opaquely. Every `strftime` in the library now goes
  through one place that names the format and the fix. A reference is meant
  to be the same on every machine; a format that only renders on some of
  them cannot keep that promise, and the caller is told so.

  The tests that simulate a server in another timezone use `time.tzset()`,
  which does not exist on Windows. They are skipped there — and the
  invariant they prove is now proved portably instead, by walking the
  library's syntax tree and asserting it never calls `datetime.now()` without
  a timezone. That is the bare call that let the machine's timezone into a
  reference before 0.3.0, and the guard fails if it is ever reintroduced.

  The library itself still has **no runtime dependencies**: its default
  bucket is `datetime.timezone.utc`, which is built into Python. Only a
  caller who asks for a *named* zone needs the database, and only on
  Windows.

  Crockford's own spec is *tolerant* of transcription (lowercase accepted,
  `I` and `L` read as `1`, `O` as `0`) and CompactRef is not, yet. That is a
  deliberate omission, recorded in the roadmap, and safe to revisit: teaching
  `verify()` to accept **more** is additive — it changes nothing `generate()`
  produces and invalidates no stored reference — so it can arrive in a 1.x.

Not locked: a reference is still not a unique identifier. That was never a
promise this library could make, and 1.0.0 does not start.

### Fixed

- Two configurations built a scheme that **failed to verify its own
  references**, and said nothing until it did:

  - A `separator` drawn from the `alphabet`. `verify()` stripped the
    separator to find the body, so it took real characters out of the
    suffix with it.

    The positional read below fixes that outright — a decimal scheme
    separated by `0` now round-trips. The configuration stays refused all
    the same, but for the honest reason: `ORD02026071400471283` hides its
    separators inside its data, and nothing downstream — a support tool, a
    regex, a person reading it aloud — can take it apart. It is a
    readability rule now, not a correctness one, and the code says so.
  - A `date_format` whose width moves — `%B` is "January" in one month and
    "December" in another, `%-d` is one character or two. `verify()` knows
    how long a body should be, so references verified for part of the year
    and were rejected for the rest.

  Both are now refused at construction, because by the time `verify()`
  returned `False` the caller would already have told a customer their
  perfectly good reference was a typo.

  Found by CodeRabbit. The width guard samples 54 datetimes rather than
  the two suggested, which miss an unpadded hour (`%-H`): 1 January and 31
  December are both midnight, so it renders `"0"` in each and looks fixed.

- **`verify()` accepted a reference with stray separators.** It pulled the
  reference apart on the separator and deleted every occurrence, so
  `ORD--20260714-…`, `ORD-20260714-…-` and `ORD-20260714-047-1283` all came
  back `True`. That is precisely the confusion the check character exists
  to prevent: a caller could not tell a typo from a reference that does not
  exist.

  It reads a reference by position now — the prefix matched literally, each
  field taken at its known width, each separator required exactly where it
  belongs, and nothing permitted to trail. A character the alphabet does
  not contain is refused outright rather than skipped by the checksum.

  Reading by position is also the only thing that *can* work, and it is why
  the fixed-width guard above matters: a `date_format` may contain the
  separator, so splitting on it would tear the date apart.

- **With `check=True`, a scheme must be able to spell its own date.** The
  check character is computed over the date, and Luhn skips any character
  the alphabet has no index for — so those characters were unprotected, and
  a mistyped one verified.

  Two configurations were affected: an alphabet that cannot express the
  date (letters, against a numeric date), and a literal in the format, such
  as the hyphen in `%Y%m%d-%H`, which could be changed to any other
  unrecognised character undetected. Both are now refused at construction.
  An hourly bucket is still available as `%Y%m%d%H`, which the alphabet can
  spell and the check therefore covers.

  Hypothesis found this one, from the other side: under an alphabet of
  `"01"`, the `2` of a 2026 date is skipped, and editing it to a `0` left
  the check unmoved.

  The rule is enforced on `generate_reference()` as well as `CompactRef`,
  and that matters: it was not, and the function could therefore mint a
  checked reference — `2026-07-140471283` — that **no `CompactRef` could be
  built to verify**, because the class refused the very configuration the
  function had just used. A library should not be able to make a thing it
  cannot read. Both share one guard now, and a property test pins it.

  The alternative — folding unrecognised characters into the checksum
  rather than forbidding them — was considered and rejected. It sounds more
  permissive but is strictly weaker: mapping a character the alphabet
  cannot index to some value (`ord(c) % base`, say) collides, so those
  characters would still not enjoy the single-character guarantee. They
  would merely *look* protected. Refusing the format keeps the guarantee
  total and provable.

- **A boolean was accepted wherever an integer belonged.** `bool`
  subclasses `int`, so `suffix_length=True` built a scheme that handed back
  a **one-character** reference, and `generate_reference(attempt=True)` was
  `attempt=1` — a caller passing a flag where a retry count belonged got a
  valid-looking reference that belonged to somebody else's attempt. Both
  silently.

  This is the trap 0.2.1 closed for `source`. The guard was applied to one
  parameter and never to the others. No type checker catches it, and none
  can: `bool` subclasses `int` in the annotations exactly as it does at
  runtime, and Python has no way to spell "int but not bool".

  `check` had the same shape of hole — it took anything truthy, so
  `check="no"` turned the check character *on*.

  Every argument that shapes a reference is now checked at runtime, on both
  `CompactRef` and `generate_reference()`: `TypeError` when the type is
  unusable, `ValueError` when the type is right but the value is not. A
  frozen dataclass annotates its fields; it does not enforce them, and the
  class promised its configuration was checked where it was written.

### Added

- **`CompactRef.parse()`**, with **`ParsedReference`** and
  **`InvalidReferenceError`**. `verify()` answers yes or no; a support desk
  needs three answers.

      parsed = orders.parse("ORD-20260714-0471283")
      parsed.date_part        # '20260714'
      parsed.suffix           # '047128'
      parsed.check_character  # '3'

  `parse()` is structural: it says the string is shaped exactly as this
  scheme shapes one, and hands back the pieces. It does not weigh the check
  character — `verify()` does that, on top of it. So a reference that
  *parses* but does not *verify* is shaped like yours and mistyped, and one
  that does not parse is not yours at all. "That is one of our order
  numbers and you have a digit wrong" is a different sentence from "that is
  not an order number", and a caller who can only say `False` cannot choose
  between them.

  `InvalidReferenceError` subclasses `ValueError`, so `except ValueError`
  still catches it. `verify()` is now a thin wrapper over `parse()`, so the
  two cannot drift apart.

- **`CompactRef.reference_length`** and **`CompactRef.date_length`**. A
  scheme knows how long its references are, so the column that stores them
  need not guess:

      reference: Mapped[str] = mapped_column(
          String(ORDERS.reference_length),   # VARCHAR(20)
          unique=True,
      )

  Both are `int | None`. `None` means the `date_format` renders to
  different widths on different dates — `%B` is `January` in one month and
  `December` in another — so the reference has no fixed length either. That
  is not a compromise: `String(None)` is an unbounded column, which is
  exactly right for a reference of no fixed length. A checked scheme is
  never `None`, because it cannot be built on a date that moves.

  A property test checks the number against what `generate()` actually
  returns, across every configuration — a length used to size a column had
  better be the real one.

- **A documentation test that could not fail.** The guard added to catch
  stale README references skipped any name it did not already recognise —
  which is precisely every name that would be stale — and then asserted that
  what remained existed, which was true by construction. It would have sailed
  past the `expected_collisions()` bug it was written for. A test that cannot
  fail is worse than none: it reads as coverage.

  It now checks three things that can genuinely fail, and I proved each one
  does: every name the README *imports* from compactref exists (a copied
  snippet must not raise `ImportError`), every method it calls on a scheme
  exists, and no removed name is recommended outside the sentence saying it
  is gone. Found by Copilot.

  It deliberately does *not* try to prove every call in the README is ours —
  the examples call SQLAlchemy, zoneinfo and the reader's own code, and an
  allowlist of everything foreign would need updating whenever an example
  grew a line. Brittle in the direction of noise, which teaches people to
  ignore the test.

- Dead code: `CompactRef._date_width`, replaced by the public `date_length`
  and left behind. Its docstring had gone stale, naming a method that no
  longer existed — which is *why* it went stale: nothing called it, so
  nothing forced it to stay true.

- **A reference could depend on the machine's language.** `%B` renders
  `July` under `LC_TIME=C`, `julio` in Spanish and `juillet` in French — so
  the same source, at the same instant, in the same scheme, produced a
  different reference on a different machine. That is the 0.3.0 bug wearing
  a different hat: a reference is meant to depend on its inputs, not on
  where it was made, and the 1.0 promise says so explicitly.

  `%a`, `%A`, `%b`, `%B`, `%c`, `%h`, `%p`, `%r`, `%x`, `%X` and `%Z` are
  refused, **with or without a check character** — this one is about
  determinism, not verification. Found by CodeRabbit.

- **A garbled date could verify against a checked scheme.** Luhn *skips* a
  character it cannot index, and skipping is indistinguishable from
  contributing zero. A scheme with `date_format="0"` over a decimal alphabet
  makes it concrete: it produces `00471284`, and `X0471284` verified — `X`
  was skipped, and `0` contributes nothing either, so the check character
  was unmoved.

  A checked scheme cannot be built on a date its alphabet cannot spell, so
  every character of a genuine date *is* in the alphabet. One that is not
  means the reference was garbled on its way here, and `parse()` says so now
  rather than handing it to the checksum. Unchecked schemes are untouched:
  their dates may legitimately carry literals, and there is no checksum to
  fool. Found by CodeRabbit.

- **A CI step that proved nothing.** `pip check` was labelled "no runtime
  dependencies, and nothing may quietly acquire one". It does not check
  that. It verifies that whatever is *installed* has its requirements
  satisfied, and would pass just as happily if this package declared six. I
  added `requests` as a runtime dependency to confirm: `pip check` reported
  "No broken requirements found".

  The package job now reads the built wheel's metadata and fails on any
  `Requires-Dist` without an `extra ==` marker. That one does fire.

### Removed

- `expected_collisions()`, deprecated since 0.3.0. It counted colliding
  pairs while its name promised a count of collisions to handle. Use
  `expected_colliding_pairs()` to size a format, or
  `expected_rejected_inserts()` to size a retry budget.

- **`verify_reference()`.** Use `CompactRef(check=True).verify()`.

  It could not be made safe, which is why it is removed rather than fixed.
  It had to be told the alphabet, prefix and separator a reference was made
  with, and could not tell when it had been told wrong — it returned
  `False`, which reads as "this reference is a typo", so a caller would
  tell a customer their good reference was invalid. Nor could it tell that
  a reference carried no check character, and "verified" one about once in
  `len(alphabet)`. Neither is visible from inside the function; only
  binding the configuration to the object fixes it.

  Removed now rather than deprecated into 1.x, because 1.0.0 is the last
  version that may remove anything. It was public for a day, across 0.4.0
  and 0.5.0, and `CompactRef.verify()` shipped in 0.5.0 as its replacement.
  A deprecation warning that most projects never display would have left a
  function documented as unsafe quietly working for the whole of 1.x, which
  is a worse promise than breaking it here.

  Migration is mechanical:

      # before
      verify_reference(ref, alphabet=A, prefix=P, separator=S)

      # after
      scheme = CompactRef(alphabet=A, prefix=P, separator=S, check=True)
      scheme.verify(ref)

## [0.5.0] - 2026-07-13

Additive. Nothing here changes what a reference looks like.

### Added

- **`CompactRef`** — a reference scheme: one configuration, used to
  generate *and* to verify. It exists because `generate_reference()` and
  `verify_reference()` take their configuration separately, and neither
  can see what the other was told. Two things went wrong, both quietly:

  - Verifying with a different alphabet, prefix or separator than the
    reference was made with returns `False`. `False` means "this reference
    is a typo", so a caller told a customer their perfectly good reference
    was invalid, when it was the caller's own configuration that was
    wrong.
  - Verifying a reference with **no check character** — the default — read
    the last character of the suffix as one, and passed about one time in
    `len(alphabet)`. Measured: 105 of 1000 unchecked references "verified"
    against a decimal alphabet. It was noise, and it did not say so.

  `generate()` and `verify()` on a `CompactRef` read the same object, so
  they cannot disagree, and `verify()` on a scheme built without
  `check=True` raises rather than guessing. The configuration is validated
  at construction, so a bad alphabet fails on the line that made it. The
  sizing helpers are bound to it and know their own base.

  The functions remain: the class is a layer over them, not a replacement.

### Fixed

- `expected_rejected_inserts()` returned a **negative** number of rejected
  inserts for a roomy bucket — `-1.65e-07` for two references over ten
  digits, where the true answer is `1e-10`. Written directly, the formula
  subtracts two nearly equal numbers and the answer falls below what a
  double can represent. It now goes through `log1p` and `expm1`, which
  keep their precision exactly where that cancellation happens. Found by
  Hypothesis on its first run.

### Documented

- **Attempts are independent draws, not a walk through unused values.**
  Two attempts can land on the same suffix, exactly as two sources can, so
  a retry loop is *not* guaranteed to find a free reference in a fixed
  number of tries. It must keep checking and it must give up rather than
  spin. Also found by Hypothesis, which produced a nine-attempt collision
  in a 64-suffix bucket.

### Tests

- Property-based tests (Hypothesis) over every configuration, rather than
  the one or two the hand-written tests sampled.
- The README's retry loop is no longer pseudocode. It runs in
  `tests/test_integration.py` against a real table with a real unique
  constraint, a real `IntegrityError`, and a real retry.

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

[1.0.0]: https://github.com/neosergio/compactref/releases/tag/v1.0.0
[0.5.0]: https://github.com/neosergio/compactref/releases/tag/v0.5.0
[0.4.0]: https://github.com/neosergio/compactref/releases/tag/v0.4.0
[0.3.0]: https://github.com/neosergio/compactref/releases/tag/v0.3.0
[0.2.1]: https://github.com/neosergio/compactref/releases/tag/v0.2.1
[0.2.0]: https://github.com/neosergio/compactref/releases/tag/v0.2.0
[0.1.0]: https://github.com/neosergio/compactref/releases/tag/v0.1.0
