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