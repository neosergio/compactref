# CompactRef

Generate compact, human-facing references from ULIDs, UUIDs and other
stable internal identifiers.

CompactRef is useful when an application keeps a full internal
identifier but needs a shorter reference for users, support teams,
documents or searches.

> **CompactRef generates compact references, not globally unique
> identifiers.**
>
> A short reference has fewer possible values than the identifier it is
> derived from, so two identifiers can produce the same reference. Keep
> the ULID or UUID as the primary key, put a unique constraint on the
> reference column, and use [`attempt`](#recovering-from-a-collision) to
> derive another one when that constraint rejects a write. [Choosing a
> suffix length](#choosing-a-suffix-length) sizes the reference so this
> stays rare.

![PyPI Version](https://img.shields.io/pypi/v/compactref)
![PyPI License](https://img.shields.io/pypi/l/compactref)
![PyPI Python Version](https://img.shields.io/pypi/pyversions/compactref)
![PyPI Status](https://img.shields.io/pypi/status/compactref)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/compactref?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=total-downloads)](https://pepy.tech/projects/compactref)

## Installation

```bash
pip install compactref
```

## Generate a reference from a ULID

```python
from compactref import generate_reference

reference = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
)

print(reference)
```

Possible output:

```text
20260710482731
```

## Add a prefix and separators

```python
from compactref import generate_reference

reference = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    prefix="INC",
    separator="-",
)

print(reference)
```

Possible output:

```text
INC-20260710-482731
```

## Use a UUID

```python
from uuid import uuid4

from compactref import generate_reference

internal_id = uuid4()
reference = generate_reference(internal_id)
```

## Configure the suffix length

```python
reference = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    suffix_length=8,
)
```

Possible output:

```text
2026071048273164
```

## Change the date format

The `date_format` argument accepts any `datetime.strftime` pattern. A
finer-grained format also produces smaller collision buckets (see
[Choosing a suffix length](#choosing-a-suffix-length)).

```python
reference = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    date_format="%Y%m%d-%H",
    separator="-",
    prefix="INC",
)
```

Possible output:

```text
INC-20260710-14-482731
```

## Use an integer or bytes identifier

```python
from compactref import generate_reference

from_integer = generate_reference(123456789)
from_bytes = generate_reference(b"internal-record-123")
```

## Deterministic generation

The same identifier, date and configuration produce the same
reference — on every machine:

```python
from datetime import datetime

from compactref import generate_reference

generated_at = datetime(2026, 7, 10)

first = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    generated_at=generated_at,
)

second = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    generated_at=generated_at,
)

assert first == second
```

## Timezones

The date part is a *bucket label*, so every caller has to agree on which
bucket an instant falls in. CompactRef therefore never reads the system
timezone. `tz` decides how the date is expressed, and defaults to UTC:

```python
from datetime import datetime, timezone

from compactref import generate_reference

instant = datetime(2026, 7, 13, 23, 30, tzinfo=timezone.utc)

# The same instant, from a server anywhere in the world.
generate_reference("01J2H8NQPG6B5X8KGN97SX3R5C", generated_at=instant)
# 'RDR-20260713-385177'  in Lima, in Tokyo, in Auckland
```

An aware `generated_at` is converted into `tz` first, so two servers
holding the same instant agree. A naive one is taken at face value, as a
wall clock you chose — CompactRef will not guess what it meant.

### Following a business day instead of UTC

Pass a zone when the bucket should follow the day your business counts,
not the day UTC counts. An order taken at 23:50 in Madrid belongs to the
Madrid day:

```python
from zoneinfo import ZoneInfo

generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    generated_at=instant,
    tz=ZoneInfo("Europe/Madrid"),
)
```

> **Upgrading from 0.2.x**
>
> Before 0.3.0 the default clock was `datetime.now()` — naive **local**
> time — so a reference depended on the machine that produced it. The
> same identifier at the same instant became `20260713…` in Lima and
> `20260714…` in Tokyo.
>
> If your servers do not run in UTC, references generated from now on
> will land in a different bucket than they used to: roughly **21% of
> them for a UTC−5 server, 38% for UTC+9**, since that is how often the
> local date differs from the UTC date.
>
> Already-stored references are unaffected — they are strings in a
> column, and nothing rewrites them. What changes is what *new* calls
> return. Two things to check:
>
> 1. If you **recompute** a reference to look a record up, rather than
>    storing it, pin the old behaviour by passing the zone your servers
>    used: `tz=ZoneInfo("America/Lima")`.
> 2. If you **store** the reference, as this README has always advised,
>    there is nothing to do.

## Recovering from a collision

Because a reference is derived from its source, the same source always
produces the same reference. Retrying a rejected reference therefore
returns the identical string, however many times you ask.

`attempt` is what makes a unique constraint recoverable. Raising it
derives a *different* reference from the same source, so when attempt 0
is already taken you can offer attempt 1:

```python
from compactref import generate_reference

def assign_reference(session, product):
    for attempt in range(10):
        reference = generate_reference(
            product.id,
            prefix="RDR",
            separator="-",
            attempt=attempt,
        )
        if not session.query(exists_reference(reference)).scalar():
            return reference

    raise RuntimeError("ten attempts collided; the suffix is too short")
```

Each attempt is deterministic in its own right, so a reference remains
recomputable later from the source and the attempt that won — store the
attempt alongside the reference if you need to rederive it.

```python
first = generate_reference("01J2H8NQPG6B5X8KGN97SX3R5C")
second = generate_reference("01J2H8NQPG6B5X8KGN97SX3R5C", attempt=1)

assert first != second
assert second == generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    attempt=1,
)
```

`attempt` defaults to 0, which reproduces the references CompactRef
produced before the argument existed. References already stored by
callers on 0.1.0 remain valid.

Reaching for `attempt` on most writes is a sign the suffix is too short,
not that the retry loop is working. Size it with `expected_collisions()`
below.

## More room per character

The suffix is decimal by default, so six characters hold a million
values. `CROCKFORD_BASE32` holds 1.07 *billion* in the same six — thirty-
two times the volume, at the same length:

```python
from compactref import CROCKFORD_BASE32, generate_reference

generate_reference("01J2H8NQPG6B5X8KGN97SX3R5C", prefix="RDR", separator="-")
# 'RDR-20260713-385177'   6 chars, 1,000,000 slots

generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    prefix="RDR",
    separator="-",
    alphabet=CROCKFORD_BASE32,
)
# 'RDR-20260713-HCP3CS'   6 chars, 1,073,741,824 slots
```

| Suffix length | Digits | Crockford base32 |
| --- | --- | --- |
| 4 | 14 refs/bucket | 145 |
| 6 | 142 | 4,646 |
| 7 | 448 | 26,280 |

Crockford's alphabet drops `I`, `L`, `O` and `U` — `I` and `L` because
they read as `1`, `O` because it reads as `0`, and `U` so the encoding
does not spell obscenities by accident.

It is not a free win, so choose deliberately. Digits can be typed on a
numeric keypad and read down a phone line without spelling anything;
letters cannot. Digits remain the default, so nothing you have already
stored moves.

**Tell the sizing helpers about it.** They assume base 10 unless told
otherwise:

```python
from compactref import max_references, suffix_length_for

suffix_length_for(200)             # 7  -> decimal
suffix_length_for(200, base=32)    # 5  -> the same volume, two chars shorter
max_references(6, base=32)         # 4646
```

## Catching a mistyped reference

Without a check character, a support agent who fat-fingers a digit gets
"no such record" — which is indistinguishable from a record that does not
exist. `check=True` makes a mistyped reference *invalid* rather than
merely absent, which is a different answer and an actionable one:

```python
from compactref import generate_reference, verify_reference

reference = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    prefix="RDR",
    separator="-",
    check=True,
)
# 'RDR-20260713-3851772'   <- the last character is the check

verify_reference(reference, prefix="RDR", separator="-")          # True
verify_reference("RDR-20260713-3851779", prefix="RDR", separator="-")  # False
```

The check covers the **date as well as the suffix**, so a mistyped day —
which would send the lookup into the wrong bucket — is caught too.

What it catches, measured rather than assumed:

- **Every** single-character error, in any alphabet. This is the common
  typo.
- Every adjacent transposition **except** the swap of the alphabet's first
  and last characters: `09 ↔ 90` in decimal, `0Z ↔ Z0` in base32. That is
  the well-known blind spot of Luhn — the scheme on the back of a credit
  card — and costs about 2.7% of transpositions in decimal, 0.3% in
  base32.

> **It adds a character but no capacity.** The check character is computed
> from the reference, not drawn from the hash. A six-character suffix plus
> a check is seven characters holding a million values, not ten million.
> Size with `suffix_length`, which is unchanged.

## Separating references that share a source

`prefix` is only a label — **it never reaches the hash**. So an order and
an invoice derived from the same customer's ULID draw the *same* suffix,
every single time:

```python
generate_reference("customer-42", prefix="ORD", separator="-")
# 'ORD-20260713-133083'
generate_reference("customer-42", prefix="INV", separator="-")
# 'INV-20260713-133083'   <- the same digits, by construction
```

That is a certainty, not a one-in-a-million coincidence, and none of the
collision helpers account for it. `namespace` is what actually separates
them:

```python
generate_reference(
    "customer-42", prefix="ORD", separator="-", namespace="orders",
)
# 'ORD-20260713-513524'

generate_reference(
    "customer-42", prefix="INV", separator="-", namespace="invoices",
)
# 'INV-20260713-205954'
```

The namespace is carried in the hash itself (BLAKE2b's key), so one
namespace cannot be spelled as part of another source. An empty
namespace — the default — reproduces every reference made before 0.4.0.

## A reference without a date

Pass an empty `date_format`. The date part drops out of the join:

```python
generate_reference("01J2H8NQPG6B5X8KGN97SX3R5C", prefix="RDR", separator="-",
                   date_format="")
# 'RDR-385177'
```

Be careful: the date is what keeps buckets small. Without it every
reference you ever issue shares one bucket, so size `suffix_length` for
your **all-time** total rather than a day's worth.

## Supported source types

CompactRef accepts:

- ULIDs represented as strings
- UUID objects
- strings
- bytes
- non-negative integers

## Choosing a suffix length

A reference is unique only within a single *bucket* — references that
share the same prefix and date part. Because the date resets each day,
what matters is how many references you expect **per bucket** (for the
default format, per day), not the all-time total.

Two helpers size the suffix using the
[birthday model](https://en.wikipedia.org/wiki/Birthday_problem).

### Estimate the collision risk

`collision_probability(reference_count, suffix_length)` returns the
probability that at least two references in one bucket share the same
suffix:

```python
from compactref import collision_probability

collision_probability(50, suffix_length=4)   # 0.1153  -> ~11.5%
collision_probability(50, suffix_length=6)   # 0.0012  -> ~0.1%
collision_probability(120, suffix_length=4)  # 0.5103  -> coin flip
```

### Count the collisions, not just the risk

`collision_probability()` saturates. Past a certain volume every format
reports "almost certainly", which stops separating a format that
collides twice a month from one that collides fifty times.

`expected_collisions(reference_count, suffix_length)` returns how many
**colliding pairs** are expected in one bucket — two references sharing a
suffix is one pair:

```python
from compactref import collision_probability, expected_collisions

collision_probability(2_000, suffix_length=3)   # 1.0   -> "certain"
collision_probability(20_000, suffix_length=3)  # 1.0   -> "certain", equally

expected_collisions(2_000, suffix_length=3)     # 1999   pairs
expected_collisions(20_000, suffix_length=3)    # 199990 pairs
```

Both formats are certain to collide. Only the second number says how
badly, which is what sizes a suffix.

> **It is a measure of crowding, not a count of retries.**
>
> A colliding pair is not a rejected insert. A suffix drawn `k` times is
> `k * (k - 1) / 2` pairs but only `k - 1` rejected inserts, so the two
> agree while a bucket is sparse and part company once it fills. Two
> thousand references over three digits is **1999 pairs but roughly 1135
> rejected inserts** — the pair count overstates the retries by more than
> half.
>
> Use it to compare formats. Do not size a retry budget with it.

### Find a safe volume

`max_references(suffix_length, max_probability=0.01)` returns the
largest number of references that keeps the risk at or below the
threshold (1% by default):

```python
from compactref import max_references

max_references(4)         # 14   -> under 1% risk with 4 digits
max_references(6)         # 142  -> under 1% risk with 6 digits
max_references(6, 0.05)   # 320  -> if you accept up to 5% risk
```

### Pick a length for your volume

`suffix_length_for(reference_count, max_probability=0.01)` answers the
question in the direction people actually ask it — you know your volume
and want a length:

```python
from compactref import suffix_length_for

suffix_length_for(200)              # 7  -> 200 a day needs 7 digits
suffix_length_for(200, 0.10)        # 6  -> if you accept up to 10% risk
suffix_length_for(5_000)            # 10
```

The count is **per bucket**, and `date_format` decides the bucket. A
daily format wants references per *day*; a monthly one wants references
per *month* — around thirty times as many, needing a **longer** suffix,
not a shorter one. Getting that backwards is the commonest way to size a
reference badly.

### Size a retry budget

`expected_rejected_inserts(reference_count, suffix_length)` returns how
many inserts a unique constraint will reject — which is how many
references need regenerating with a higher [`attempt`](#recovering-from-a-collision).
This is the number to plan with:

```python
from compactref import expected_colliding_pairs, expected_rejected_inserts

expected_rejected_inserts(200, suffix_length=7)   # 0.002 -> effectively never
expected_rejected_inserts(2_000, suffix_length=3) # 1135  -> a bad format

expected_colliding_pairs(2_000, suffix_length=3)  # 1999  -> pairs, not retries
```

An insert can only be rejected once, so this can never exceed the
reference count. Colliding pairs can, and do — which is why they are the
wrong number to size a retry budget with.

For roughly 200 references per day, a 7-digit suffix keeps the risk
well under 1%.

## Uniqueness warning

CompactRef does not replace the original internal identifier.

Shortening an identifier reduces the number of possible values.
Different internal identifiers can produce the same compact reference.
No suffix length makes this impossible; a longer one only makes it
rarer.

Applications requiring unique references should:

1. Keep the original ULID or UUID as the internal identifier. The
   reference is for humans; the identifier is for the database.
2. Add a unique constraint to the reference column, so a collision
   surfaces as a rejected write rather than two products quietly sharing
   a reference.
3. Handle that rejection by retrying with a higher `attempt`, as in
   [Recovering from a collision](#recovering-from-a-collision).
4. Size `suffix_length` for the expected volume *per bucket*, using
   `expected_collisions()`, so step 3 stays a rare path rather than the
   normal one.

## Requirements

Python 3.10 or newer. No runtime dependencies.

## Changelog

See
[CHANGELOG.md](https://github.com/neosergio/compactref/blob/main/CHANGELOG.md).

Version 0.2.0 added the `attempt` argument and `expected_collisions()`.
References produced by 0.1.0 are unchanged: `attempt` defaults to 0, which
reproduces them byte for byte, so anything already stored stays valid.

## Contributing

Issues and pull requests are welcome at
[github.com/neosergio/compactref](https://github.com/neosergio/compactref).

Maintainers: see
[RELEASING.md](https://github.com/neosergio/compactref/blob/main/RELEASING.md)
for how a version reaches PyPI.

## License

MIT