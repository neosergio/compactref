"""The retry loop, against a real database.

The README used to print this as pseudocode, which is a way of saying "we
have not run it". Here it runs: a real unique constraint, a real
IntegrityError, and a real retry on a higher attempt. The README example
is copied from this file rather than imagined.

SQLite is enough. The constraint and the exception are what matter, and
they behave the same on Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)

from compactref import CROCKFORD_BASE32, CompactRef


ORDERS = CompactRef(
    prefix="ORD",
    separator="-",
    alphabet=CROCKFORD_BASE32,
    namespace="orders",
    check=True,
)

MAX_ATTEMPTS = 10


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    # The real identifier. The reference never replaces it.
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # The human-facing one. Unique, so a collision is a rejected write
    # rather than two orders quietly sharing a reference. The scheme knows
    # how long it is, so the column does not have to guess.
    reference: Mapped[str] = mapped_column(
        String(ORDERS.reference_length),
        unique=True,
    )

    # Which attempt won. Stored so the reference can be recomputed later
    # from the id alone.
    attempt: Mapped[int] = mapped_column(default=0)


class ReferenceExhausted(RuntimeError):
    """Every attempt collided. The suffix is too short for the volume."""


def create_order(
    session: Session,
    order_id: str,
    *,
    scheme: CompactRef = ORDERS,
    generated_at: datetime | None = None,
) -> Order:
    """Insert an order, retrying on a higher attempt when the reference is
    already taken.

    Attempts are independent draws, so a retry is not guaranteed to find a
    free reference — hence the ceiling. Hitting it does not mean try
    harder; it means the suffix is too short for the volume, and
    expected_rejected_inserts() will have said so beforehand.
    """
    for attempt in range(MAX_ATTEMPTS):
        reference = scheme.generate(
            order_id,
            generated_at=generated_at,
            attempt=attempt,
        )
        order = Order(id=order_id, reference=reference, attempt=attempt)

        try:
            with session.begin_nested():
                session.add(order)
            return order
        except IntegrityError:
            # The unique constraint fired. The same attempt would produce
            # the same string forever, so the next one has to differ.
            continue

    raise ReferenceExhausted(
        f"{MAX_ATTEMPTS} attempts collided for {order_id}. "
        f"The suffix is too short for this volume."
    )


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as active:
        yield active

    # Otherwise the connection is collected rather than closed, and pytest
    # is configured to treat that ResourceWarning as the leak it is.
    engine.dispose()


def test_an_order_gets_a_reference(session: Session) -> None:
    order = create_order(session, "01J2H8NQPG6B5X8KGN97SX3R5C")
    session.commit()

    assert order.reference.startswith("ORD-")
    assert order.attempt == 0
    assert ORDERS.verify(order.reference)


def test_the_reference_column_is_actually_unique(session: Session) -> None:
    # If this fails, the retry loop below is guarding nothing.
    session.add(Order(id="a", reference="ORD-20260713-AAAAAAA"))
    session.commit()

    session.add(Order(id="b", reference="ORD-20260713-AAAAAAA"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_taken_reference_is_retried_on_a_higher_attempt(
    session: Session,
) -> None:
    """The whole point of `attempt`.

    Squat on the reference attempt 0 would produce, then insert the order
    that wants it. The loop must land on attempt 1 rather than fail — and
    must not simply reissue the same string, which is what retrying without
    `attempt` would do.
    """
    at = datetime(2026, 7, 13, tzinfo=timezone.utc)
    order_id = "01J2H8NQPG6B5X8KGN97SX3R5C"

    taken = ORDERS.generate(order_id, generated_at=at, attempt=0)
    session.add(Order(id="squatter", reference=taken))
    session.commit()

    order = create_order(session, order_id, generated_at=at)
    session.commit()

    assert order.attempt == 1
    assert order.reference != taken
    assert order.reference == ORDERS.generate(
        order_id,
        generated_at=at,
        attempt=1,
    )
    assert ORDERS.verify(order.reference)


def test_the_reference_recomputes_from_the_id_and_the_stored_attempt(
    session: Session,
) -> None:
    # Why `attempt` is a column. Without it a retried reference cannot be
    # derived again from the identifier.
    at = datetime(2026, 7, 13, tzinfo=timezone.utc)
    order_id = "01J2H8NQPG6B5X8KGN97SX3R5C"

    session.add(
        Order(
            id="squatter", reference=ORDERS.generate(order_id, generated_at=at)
        )
    )
    session.commit()

    create_order(session, order_id, generated_at=at)
    session.commit()

    stored = session.scalar(select(Order).where(Order.id == order_id))
    assert stored is not None

    recomputed = ORDERS.generate(
        stored.id,
        generated_at=at,
        attempt=stored.attempt,
    )

    assert recomputed == stored.reference


def test_a_hopeless_format_gives_up_rather_than_spinning(
    session: Session,
) -> None:
    """A one-character decimal suffix has ten values. Fill all ten.

    The loop must raise rather than loop forever. Exhaustion is a sizing
    problem, and no retry policy fixes it.

    Decimal rather than binary, because a checked scheme has to be able to
    spell its own date: under an alphabet of "01" the checksum would step
    over the 2 of a 2026 date, and CompactRef refuses to build that.
    """
    tiny = CompactRef(suffix_length=1, check=True)
    at = datetime(2026, 7, 13, tzinfo=timezone.utc)

    # Take every reference the scheme is capable of issuing, by asking it
    # for them rather than hand-building strings.
    every_reference = {
        tiny.generate(f"filler-{index}", generated_at=at)
        for index in range(400)
    }
    assert len(every_reference) == 10, every_reference

    for index, reference in enumerate(sorted(every_reference)):
        session.add(Order(id=f"squatter-{index}", reference=reference))
    session.commit()

    with pytest.raises(ReferenceExhausted):
        create_order(
            session, "wants-a-reference", scheme=tiny, generated_at=at
        )


def test_many_orders_in_a_well_sized_bucket_never_collide(
    session: Session,
) -> None:
    # 500 orders into a base32 bucket of 32**6. The retry path should never
    # be taken, which is what "sized correctly" means.
    at = datetime(2026, 7, 13, tzinfo=timezone.utc)

    for index in range(500):
        create_order(session, f"order-{index}", generated_at=at)
    session.commit()

    orders = session.scalars(select(Order)).all()

    assert len(orders) == 500
    assert all(order.attempt == 0 for order in orders)
    assert len({order.reference for order in orders}) == 500
    assert all(ORDERS.verify(order.reference) for order in orders)
