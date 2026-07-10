# CompactRef

Generate compact, human-facing references from ULIDs, UUIDs and other
stable internal identifiers.

CompactRef is useful when an application keeps a full internal
identifier but needs a shorter reference for users, support teams,
documents or searches.

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

Applications requiring unique references should:

1. Keep the original ULID or UUID as the internal identifier.
2. Add a unique constraint to the reference column.
3. Detect and handle the unlikely possibility of a collision.
4. Increase `suffix_length` when the expected volume requires it.

## Requirements

Python 3.10 or newer.

## License

MIT