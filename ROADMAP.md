# Roadmap

## Shipped

- `expected_collisions()` and the `attempt` argument of
  `generate_reference()`, in 0.2.0. See the [changelog](CHANGELOG.md).

## Planned

### `suffix_length_for(reference_count, max_probability=0.01)`

Return the smallest suffix length that keeps `reference_count`
references in one bucket at or below `max_probability`.

`max_references()` answers the question backwards: it takes a length and
returns a volume, so a caller who knows their volume and wants a length
has to sweep. The README currently tells them to write that loop:

```python
for length in range(4, 9):
    risk = collision_probability(expected_per_day, suffix_length=length)
    print(f"{length} digits -> {risk:.3%}")
```

Sizing a reference is the first decision every caller makes, and it
should not require a loop over a helper to arrive at one integer.

Notes for implementation:

- Invert the birthday approximation directly rather than sweeping.
- Decide what to do when no length is small enough to be useful. A
  volume that needs 30 digits is a caller who should hear about it, not
  receive a 30.

### Bucket-aware sizing

Every helper takes a *per-bucket* count, and the bucket is decided by
`date_format` — a caller on `%Y%m` has one bucket a month, a caller on
`%Y%m%d-%H` has one an hour. Callers currently convert by hand, and
getting it wrong is the single most likely way to size a reference
badly: a monthly bucket holds roughly thirty times the daily volume, so
it collides far sooner than the extra digit it usually buys back.

Worth considering a helper that takes `date_format` and a rate, and does
the conversion. Worth *not* doing if it guesses more than it explains.
