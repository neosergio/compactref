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

## A reference scheme

Define the scheme once and use it everywhere. This is the recommended way
in — the functions below it are the primitives it is built from:

```python
from compactref import CROCKFORD_BASE32, CompactRef

orders = CompactRef(
    prefix="ORD",
    separator="-",
    alphabet=CROCKFORD_BASE32,
    namespace="orders",
    check=True,
)

reference = orders.generate("01J2H8NQPG6B5X8KGN97SX3R5C")
# 'ORD-20260713-RWSRDMA'

orders.verify(reference)          # True
orders.verify("ORD-20260713-RWSRD0A")   # False — a typo
```

Sizing is bound to the scheme too, and already knows its own alphabet:

```python
orders.base                          # 32
orders.suffix_length_for(200)        # 5   -- base32 needs fewer characters
orders.max_references()              # 4646
orders.expected_rejected_inserts(500)  # 0.0001
```

And it knows how long its own references are, so the column that stores
them does not have to guess:

```python
orders.reference_length   # 20
orders.date_length        # 8

reference: Mapped[str] = mapped_column(
    String(orders.reference_length),
    unique=True,
)
```

Both are `int | None`. `None` means the `date_format` renders to different
widths on different dates — `%B` is `January` in one month and `December`
in another — so the reference has no fixed length either. That is not a
compromise: `String(None)` is an unbounded column, which is exactly right
for a reference of no fixed length. A **checked** scheme is never `None`,
because it cannot be built on a date that moves.

The configuration is checked when the object is built — types as well as
values — so a mistake raises on the line that made it rather than on the
ten-thousandth call. It is frozen, so build it once at import and share it.

Types are checked at runtime, not merely annotated, because the annotation
is not enough. `bool` subclasses `int`, so `CompactRef(suffix_length=True)`
would otherwise build a scheme that hands back a **one-character**
reference — and no type checker would object, since `bool` subclasses `int`
in the annotations exactly as it does at runtime. Python has no way to
spell "int but not bool".

> **Why a scheme, and not just arguments.** Verifying a reference means
> recomputing its check character, which means knowing the alphabet,
> prefix, separator, suffix length and date format it was generated with.
> A free function has to be *told* all of that, and cannot tell when it has
> been told wrong. compactref shipped one briefly, and it failed two ways
> that no care inside it could have fixed:
>
> - Told a different alphabet, prefix or separator than the reference was
>   made with, it returned `False` — which means *"this reference is a
>   typo"*. You would tell a customer their perfectly good reference was
>   invalid, when it was your own configuration that was wrong.
> - Told a reference with **no check character** — the default — it read
>   the last character of the suffix as one, and passed about **one time in
>   `len(alphabet)`**. Noise, and it never said so.
>
> A `CompactRef` closes both by construction. `generate()` and `verify()`
> read the same object, so they cannot disagree, and `verify()` on a scheme
> without `check=True` raises instead of guessing. The free function was
> removed in 1.0.0.

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
20260710385177
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
INC-20260710-385177
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
2026071024385177
```

## Change the date format

The `date_format` argument accepts any `datetime.strftime` pattern. A
finer-grained format also produces smaller collision buckets (see
[Choosing a suffix length](#choosing-a-suffix-length)).

```python
reference = generate_reference(
    "01J2H8NQPG6B5X8KGN97SX3R5C",
    date_format="%Y%m%d%H",
    separator="-",
    prefix="INC",
)
```

Possible output:

```text
INC-2026071014-385177
```

### What the date format must not do

Some rules hold always, because they protect **determinism** — the promise
that a reference depends on its inputs and not on the machine. Others bind
only when `check=True`, because they protect **verification**. Both are
enforced on `CompactRef` *and* on `generate_reference()`, so the library
cannot mint a reference it is unable to read back.

**The date must render to the same width every time.** `%B` is `January`
in one month and `December` in another; `%-d` is one character or two.
Verifying reads a reference by position, so a width that moves would make
references verify for part of the year and be rejected for the rest. Pad
the field (`%d`, not `%-d`) or use a fixed one (`%m`, not `%B`).

**The date must not depend on the machine's language.** `%B` is `July`
under `LC_TIME=C`, `julio` in Spanish and `juillet` in French — so the same
identifier, at the same instant, in the same scheme, would produce a
different reference on a different machine. That is not a reference, it is a
caption. `%a`, `%A`, `%b`, `%B`, `%c`, `%p`, `%x` and `%X` are all refused,
**with or without a check character**: this one is not about verification,
it is about determinism, which is the thing the library exists to provide.

**The date must render on every platform.** Not every `strftime` directive
exists everywhere: `%-d` (an unpadded day) is a glibc extension that renders
on Linux and macOS and *raises* on Windows, and `%#d` is the Windows
spelling that glibc does not know. A reference is meant to be the same on
every machine, so a format that only works on some of them cannot keep that
promise. CompactRef refuses one, naming the directive rather than leaking a
stdlib traceback. Use the padded numeric directives — `%Y`, `%m`, `%d`,
`%H` — which render everywhere and render the same.

**The date must be spelled in the alphabet.** The check character is
computed over the date, and Luhn steps over any character it cannot index —
so those characters would carry *no protection at all*, and a mistyped one
would verify. That rules out a literal in the format (`%Y-%m-%d` or
`%Y%m%d-%H`, whose hyphens are not digits) and an alphabet that cannot
express the date. Write the hour as `%Y%m%d%H` and it is covered like
everything else; put your separators in `separator`, where the verifier
checks them by position.

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
# '20260713385177'  in Lima, in Tokyo, in Auckland
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

> **On Windows, a named zone needs `tzdata`.**
>
> `ZoneInfo` reads the operating system's timezone database, and Windows
> does not have one, so `ZoneInfo("Europe/Madrid")` raises
> `ZoneInfoNotFoundError` there until you install it:
>
> ```bash
> pip install tzdata          # or: pip install compactref[tz]
> ```
>
> CompactRef itself needs nothing. Its default bucket is
> `datetime.timezone.utc`, which is built into Python — which is why the
> library has no runtime dependencies at all. This only applies if *you*
> ask for a named zone. Linux and macOS ship the database, so it is a
> Windows matter only.

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

### With SQLAlchemy

This is not pseudocode. It is lifted from `tests/test_integration.py`,
which runs it against a real table with a real unique constraint:

```python
from sqlalchemy import String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from compactref import CROCKFORD_BASE32, CompactRef

ORDERS = CompactRef(
    prefix="ORD", separator="-", alphabet=CROCKFORD_BASE32,
    namespace="orders", check=True,
)
MAX_ATTEMPTS = 10


class Order(DeclarativeBase):
    __tablename__ = "orders"

    # The real identifier. The reference never replaces it.
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # The human-facing one. Unique, so a collision is a rejected write
    # rather than two orders quietly sharing a reference. The scheme knows
    # how long it is, so the column does not have to guess.
    reference: Mapped[str] = mapped_column(
        String(ORDERS.reference_length),   # VARCHAR(20)
        unique=True,
    )

    # Which attempt won. Stored so the reference can be recomputed later.
    attempt: Mapped[int] = mapped_column(default=0)


class ReferenceExhausted(RuntimeError):
    """Every attempt collided. The suffix is too short for the volume."""


def create_order(session: Session, order_id: str) -> Order:
    for attempt in range(MAX_ATTEMPTS):
        order = Order(
            id=order_id,
            reference=ORDERS.generate(order_id, attempt=attempt),
            attempt=attempt,
        )
        try:
            with session.begin_nested():
                session.add(order)
            return order
        except IntegrityError:
            # The constraint fired. The same attempt would produce the same
            # string forever, so the next one has to differ.
            continue

    raise ReferenceExhausted(f"{MAX_ATTEMPTS} attempts collided for {order_id}")
```

Three things in there are load-bearing:

**Store the attempt.** Each attempt is deterministic in its own right, so
the reference stays recomputable — but only from the source *and the
attempt that won*. Without that column, a retried reference can never be
derived again.

**Keep the original identifier.** The reference is for humans; the ULID is
for the database. `id` remains the primary key.

**Give up rather than spin.** Attempts are independent draws, not a walk
through unused values — two attempts can land on the same suffix, exactly
as two sources can. So a retry loop is *not* guaranteed to find a free
reference in a fixed number of tries. Hitting the ceiling does not mean
try harder; it means the suffix is too short, and
`expected_rejected_inserts()` would have told you so beforehand.

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
not that the retry loop is working. Pick the length with
[`suffix_length_for()`](#pick-a-length-for-your-volume), and size the retry
budget with [`expected_rejected_inserts()`](#size-a-retry-budget).

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
from compactref import CompactRef

scheme = CompactRef(prefix="RDR", separator="-", check=True)

reference = scheme.generate("01J2H8NQPG6B5X8KGN97SX3R5C")
# 'RDR-20260714-3851770'   <- the last character is the check

scheme.verify(reference)                  # True
scheme.verify("RDR-20260714-3851779")     # False — a typo
```

Verification lives on the scheme, not on a free function, and that is
deliberate. Checking a reference means knowing the alphabet, prefix,
separator, suffix length and date format it was *generated* with — and a
free function has to be told all of that, with no way to tell when it has
been told wrong. It would return `False` for a valid reference whose
configuration you mistyped, which reads as *"that reference is a typo"*.
The scheme holds one configuration, so `generate()` and `verify()` cannot
disagree.

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

## Telling a typo from a stranger

`verify()` answers yes or no. A support desk needs three answers, and
`parse()` is what gives the third:

```python
from compactref import CompactRef, InvalidReferenceError

orders = CompactRef(prefix="ORD", separator="-", check=True)

parsed = orders.parse("ORD-20260714-0471283")
parsed.prefix           # 'ORD'
parsed.date_part        # '20260714'
parsed.suffix           # '047128'
parsed.check_character  # '3'
```

`parse()` is *structural*. It says the string is shaped exactly as this
scheme shapes one — the right prefix, the separators where they belong,
each field at its width, nothing trailing, every character in the alphabet
— and hands back the pieces. It does not decide whether the check
character is right. `verify()` does that, on top of it.

That split is the point:

| | `parse()` | `verify()` | what you can say |
| --- | --- | --- | --- |
| `ORD-20260714-0471283` | ✓ | `True` | valid |
| `ORD-20260714-0471203` | ✓ | `False` | *"that is one of our order numbers, and you have a digit wrong"* |
| `hello` | `InvalidReferenceError` | `False` | *"that is not an order number"* |

A caller who can only say `False` cannot choose between the last two — and
they are different sentences to say to a customer.

`InvalidReferenceError` subclasses `ValueError`, so `except ValueError`
still catches it if you do not care about the distinction. And `parse()`
works without a check character too — the structure is checkable without
one; `check_character` is then `None`.

## What the check character protects

Locked in 1.0.0. Changing any of this would invalidate references already
in somebody's database, so it does not change without a 2.0.

**The checksum covers the date and the suffix.** Luhn mod N over the
alphabet, computed on `date_part + suffix`.

**It does not cover the prefix.** Deliberately: the prefix is a *label*.
`namespace` is what separates one kind of reference from another, and it
does so in the hash, where it cannot be spelled away. A label may be
renamed, translated, or shown differently in one place than another, and
none of that should change the reference underneath. What separates an
order from an invoice is the namespace, not the three letters in front.

**It does not cover the separators.** They carry no information.

**But the prefix and the separators are still checked** — structurally,
not arithmetically. `verify()` reads a reference by position: it matches
the prefix literally, requires each separator exactly where it belongs,
takes each field at its known width, and permits nothing to trail. So a
wrong prefix, a doubled separator, a missing one, or a stray character at
the end is refused, even though none of them touches the checksum.

**Every character of the date and the suffix is in the alphabet.** A
checked scheme cannot be built otherwise, so the checksum never skips
anything and Luhn's guarantee is total rather than partial.

**Verification is exact, and case-sensitive.** `verify()` accepts what
`generate()` produced, and nothing else. It does not normalise, trim,
upper-case, or repair its input.

> **On Crockford and case.** Crockford's base32 was designed to tolerate
> transcription — lowercase accepted, `I` and `L` read as `1`, `O` read as
> `0`. CompactRef does not do that yet: it generates upper case and
> verifies exactly.
>
> That is a deliberate omission rather than an oversight, and it is safe to
> revisit. Teaching `verify()` to accept more is *additive* — it changes
> nothing that `generate()` produces and invalidates no stored reference —
> so it can arrive in a 1.x without breaking the promise above.

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

Five functions, five different questions. Two of them sound alike and are
not, which is the confusion worth heading off:

| Question | Function |
| --- | --- |
| Will *anything* collide? | `collision_probability()` |
| How crowded is this format? | `expected_colliding_pairs()` |
| How many writes will a unique constraint reject — my **retry budget**? | `expected_rejected_inserts()` |
| How much volume does a given length carry? | `max_references()` |
| What length do I need for my volume? | `suffix_length_for()` |

To *choose* a length, use `suffix_length_for()`. To *budget* for retries,
use `expected_rejected_inserts()`. Colliding pairs measure crowding, not
work: a suffix drawn `k` times is `k(k-1)/2` pairs but only `k-1` rejected
inserts, so the pair count runs far ahead of the retries once a bucket
fills.

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

`expected_colliding_pairs(reference_count, suffix_length)` returns how many
**colliding pairs** are expected in one bucket — two references sharing a
suffix is one pair:

```python
from compactref import collision_probability, expected_colliding_pairs

collision_probability(2_000, suffix_length=3)      # 1.0  -> "certain"
collision_probability(20_000, suffix_length=3)     # 1.0  -> "certain", equally

expected_colliding_pairs(2_000, suffix_length=3)   # 1999   pairs
expected_colliding_pairs(20_000, suffix_length=3)  # 199990 pairs
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
   `suffix_length_for()`, so step 3 stays a rare path rather than the
   normal one — and check the cost of that path with
   `expected_rejected_inserts()`.

## Requirements

Python 3.10 or newer. No runtime dependencies.

## Exceptions

Three, and no more. Locked in 1.0.0.

| Raised | When | Where you meet it |
| --- | --- | --- |
| `TypeError` | The type is unusable — `suffix_length=True`, `prefix=123`, `tz="UTC"` | Building a scheme, or calling `generate_reference()` |
| `ValueError` | The type is right but the value is not — an alphabet that repeats a character, a separator the suffix can contain, a date the check cannot cover | Building a scheme |
| `InvalidReferenceError` | A string is not shaped like a reference from this scheme | `parse()` |

`InvalidReferenceError` subclasses `ValueError`, so `except ValueError`
catches everything the library raises with a bad value, and code that does
not care about the distinction need not learn it.

There is no `CompactRefError` base class, deliberately. The only exception
anyone catches is `InvalidReferenceError` — it is the one a *user* can
trigger, by mistyping a reference. The rest are programmer errors: a bad
alphabet, a boolean where an integer belongs. You do not catch those, you
fix them, once, at startup. And the config-versus-reference distinction is
already available from *where* you catch:

```python
try:
    orders = CompactRef(**settings.COMPACTREF)   # config errors surface here
except (TypeError, ValueError) as error:
    raise ImproperlyConfigured(error)

try:
    parsed = orders.parse(user_input)            # reference errors, here
except InvalidReferenceError:
    return "That is not one of our reference numbers."
```

`verify()` does **not** raise on a malformed reference. It returns `False`,
because it answers a yes/no question. It raises only if the scheme has no
check character, which is a configuration mistake rather than a bad
reference.

## Stability

CompactRef is 1.0. The API does not break without a 2.0.

Locked:

- **Names** — `CompactRef`, `generate_reference()`, the sizing helpers.
- **Parameters** — their names, their order, their defaults.
- **The default format** — `generate_reference("…")` returns exactly what
  it returned in 0.1.0. Every argument added since (`attempt`, `namespace`,
  `alphabet`, `check`, `tz`) defaults to doing nothing, and a test pins the
  strings 0.1.0 produced. References you have already stored keep
  resolving.
- **Exceptions** — `TypeError` when the type is unusable, `ValueError` when
  the type is right but the value is not.
- **Determinism** — the same source, date, attempt and configuration give
  the same reference on every machine. Nothing reads the environment.

Not locked, because it never could be: **a reference is not a unique
identifier**. See [Uniqueness warning](#uniqueness-warning).

Removed in 1.0.0: `verify_reference()`. Use
`CompactRef(check=True).verify()`, which cannot be handed a configuration
that disagrees with the one that made the reference. It existed for a day,
in 0.4.0 and 0.5.0; 1.0 is the last version that may remove it, and keeping
a function documented as unsafe for the whole of 1.x would have been a
worse promise than breaking it now.

## Upgrading to 1.0

**One thing breaks.** `verify_reference()` is removed. Use
`CompactRef(check=True).verify()`:

```python
# before (0.4.0, 0.5.0)
verify_reference(reference, alphabet=A, prefix=P, separator=S)

# after
scheme = CompactRef(alphabet=A, prefix=P, separator=S, check=True)
scheme.verify(reference)
```

It could not be made safe. It had to be told the alphabet, prefix and
separator a reference was generated with, and could not tell when it had
been told wrong — it returned `False`, which reads as *"that reference is a
typo"*, so you would tell a customer their perfectly good reference was
invalid. Nor could it tell that a reference carried no check character at
all, and "verified" one about once in `len(alphabet)`. A `CompactRef` holds
one configuration, so `generate()` and `verify()` cannot disagree.

`expected_collisions()` is also gone, deprecated since 0.3.0. Use
`expected_colliding_pairs()` to size a format, or
`expected_rejected_inserts()` to size a retry budget.

**Nothing else moves.** Every reference this library has ever produced still
resolves — `generate_reference("…")` returns exactly what it returned in
0.1.0, and a test pins the strings to prove it. Every argument added across
six releases (`attempt`, `namespace`, `alphabet`, `check`, `tz`) defaults to
doing nothing.

## Changelog

The full history — including the timezone fix in 0.3.0, which *did* move
references for servers not running in UTC — is in
[CHANGELOG.md](https://github.com/neosergio/compactref/blob/main/CHANGELOG.md).

## Contributing

Issues and pull requests are welcome at
[github.com/neosergio/compactref](https://github.com/neosergio/compactref).

Maintainers: see
[RELEASING.md](https://github.com/neosergio/compactref/blob/main/RELEASING.md)
for how a version reaches PyPI.

## License

MIT