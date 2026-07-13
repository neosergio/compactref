# Roadmap

1.0.0 is a lock, not a milestone: it is a promise not to break the API.
So what goes before it is whatever we would regret being stuck with.
See the [changelog](CHANGELOG.md) for what has shipped.

## Shipped

- **0.2.0** — `attempt`, so a reference a unique constraint rejected can
  be regenerated. Retrying without it returns the same string forever.
- **0.2.1** — booleans rejected as sources (`True` was returning the
  reference belonging to `1`). `expected_collisions()` documented as the
  pair count it always was, rather than the retry count it never was.
- **0.3.0** — `tz`. The system timezone is no longer read, so a reference
  no longer depends on the machine that produced it.
  `expected_rejected_inserts()`, `suffix_length_for()`.
- **0.4.0** — `alphabet` (Crockford base32), `check` and
  `verify_reference()`, `namespace` (`prefix` never reached the hash, so
  an order and an invoice from one customer drew the same suffix). `base`
  on every sizing helper.

## 0.5.0 — ergonomics and confidence

Everything here is additive. Nothing changes what a reference looks like,
which is the point: the format is now settled.

### A `CompactRef` class

Every call repeats the same five arguments:

```python
generate_reference(order.id, prefix="ORD", separator="-",
                   alphabet=CROCKFORD_BASE32, namespace="orders", check=True)
```

A configured instance says it once:

```python
orders = CompactRef(prefix="ORD", separator="-",
                    alphabet=CROCKFORD_BASE32, namespace="orders", check=True)

orders.generate(order.id)
orders.verify(reference)
orders.suffix_length_for(200)   # knows its own base
```

The functions stay. The class is a convenience over them, not a
replacement, and it is what makes `verify()` pleasant — today a caller has
to pass the alphabet, separator and prefix back in by hand, and getting
any of them wrong silently returns False.

### Property-based tests

Hypothesis, over the invariants the hand-written tests only sample:

- every reference decodes to `suffix_length` characters of the alphabet;
- `verify()` accepts what `generate(check=True)` produced, for any source,
  alphabet, prefix and separator;
- a single-character edit never verifies;
- `attempt` never repeats a reference within a bucket.

### Integration documentation

The retry loop in the README is pseudocode. Real, runnable examples for
SQLAlchemy and Django — a unique constraint, an `IntegrityError`, and the
`attempt` retry — are what a caller actually copies.

## 1.0.0 — the lock

Ship it when the API is one we are content never to break. At that point:

- Remove `expected_collisions()`, deprecated since 0.3.0.
- Settle the exception contract in writing: `TypeError` when the type is
  unusable, `ValueError` when the type is right but the value is not.

## Considered, not planned

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
