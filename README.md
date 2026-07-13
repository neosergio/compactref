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
reference:

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
*pairs* are expected to share a suffix in one bucket. With a unique
constraint in place, a collision is a rejected insert, so this is really
an error rate — the number of writes per bucket that will need an
`attempt` retry:

```python
from compactref import collision_probability, expected_collisions

collision_probability(2_000, suffix_length=3)   # 1.0   -> "certain"
collision_probability(20_000, suffix_length=3)  # 1.0   -> "certain", equally

expected_collisions(2_000, suffix_length=3)     # 1999  pairs
expected_collisions(20_000, suffix_length=3)    # 199990 pairs
```

Both formats are certain to collide. Only the second number tells you
how badly.

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

```python
from compactref import collision_probability

expected_per_day = 200

for length in range(4, 9):
    risk = collision_probability(expected_per_day, suffix_length=length)
    print(f"{length} digits -> {risk:.3%}")

# 4 digits -> 86.330%
# 5 digits -> 18.045%
# 6 digits -> 1.970%
# 7 digits -> 0.199%
# 8 digits -> 0.020%
```

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