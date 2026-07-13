# Roadmap

## Planned

### `expected_collisions(reference_count, suffix_length)`

Return the *expected number* of colliding pairs in one bucket, rather
than the probability that at least one collision occurs.

`collision_probability()` answers "will anything collide?" — a yes/no
risk that saturates near 100% and stops being informative. Once a
format is known to collide, the question becomes "how often?", and that
is a different quantity:

```
expected pairs = n * (n - 1) / (2 * 10 ** suffix_length)
```

For a reference column with a unique constraint, a collision is a
failed insert, so this number is really an error rate. It is the figure
most people want when sizing a suffix:

| Format | 10 refs/day | Expected collisions/month |
| --- | --- | --- |
| `RDR-20260713-123` | 300/month over 30 daily buckets | 1.35 |
| `RDR-202607-1234` | 300 in one monthly bucket | 4.49 |
| `RDR-20260713-1234` | 300/month over 30 daily buckets | 0.13 |
| `RDR-20260713-482731` | 300/month over 30 daily buckets | 0.00 |

Notes for implementation:

- Mirror the validation of `collision_probability()`: reject
  `suffix_length < 1` and negative `reference_count`; return `0.0` for
  fewer than two references.
- The caller supplies the per-bucket count. Callers with a daily bucket
  who want a monthly total multiply by the number of days themselves —
  the function should not guess the bucket size from `date_format`.
