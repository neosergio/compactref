"""A scheme shared between threads.

The README says to build a CompactRef once at import and share it. On a
free-threaded build (3.14t and later) sharing means threads really do run
it at the same time, with no GIL taking turns for them. These hold that
advice to account: a shared scheme must give every thread exactly what it
gives one thread alone.

On a build with a GIL they still pass, and prove less. CI runs them on a
free-threaded build too, which is where they can fail.
"""

from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from compactref import CROCKFORD_BASE32, CompactRef


THREADS = 8
SOURCES = [f"record-{index}" for index in range(400)]
START = datetime(2026, 7, 10, tzinfo=timezone.utc)

FREE_THREADED = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


def test_importing_compactref_leaves_the_gil_off() -> None:
    """A free-threaded interpreter turns the GIL back on for any extension
    module that has not declared itself safe without it — silently, unless
    you go looking. compactref is pure Python and has no dependencies, so
    importing it must never be what does that.

    Asked in a fresh interpreter, so the answer is about compactref and not
    about whatever the test run imported first. PYTHON_GIL is dropped from
    its environment: forcing the GIL off would make the question moot.
    """
    if not FREE_THREADED:
        pytest.skip("only meaningful on a free-threaded build")

    environment = {
        name: value
        for name, value in os.environ.items()
        if name != "PYTHON_GIL"
    }
    answer = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            "import compactref, sys; print(sys._is_gil_enabled())",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )

    assert answer.stdout.strip() == "False"


@pytest.mark.parametrize(
    "scheme",
    [
        CompactRef(),
        CompactRef(prefix="ORD", separator="-", check=True),
        CompactRef(
            prefix="ORD",
            separator="-",
            alphabet=CROCKFORD_BASE32,
            namespace="orders",
            check=True,
            tolerant=True,
        ),
    ],
    ids=["default", "checked", "crockford-tolerant"],
)
def test_a_shared_scheme_gives_every_thread_what_it_gives_one(
    scheme: CompactRef,
) -> None:
    def work(index: int, source: str) -> tuple[str, bool, str]:
        reference = scheme.generate(
            source,
            generated_at=START + timedelta(days=index % 40),
            attempt=index % 3,
        )
        verified = scheme.verify(reference) if scheme.check else True
        # A tolerant scheme is handed what a person would type. The prefix
        # is matched exactly, tolerant or not, so it keeps its case.
        typed = reference
        if scheme.tolerant:
            coded = reference.removeprefix(scheme.prefix)
            typed = scheme.prefix + coded.lower()
        return reference, verified, scheme.normalize(typed)

    def all_of_them() -> list[tuple[str, bool, str]]:
        return [work(index, source) for index, source in enumerate(SOURCES)]

    if FREE_THREADED:
        # Otherwise this passes and proves only what a GIL build proves.
        assert not sys._is_gil_enabled(), (  # type: ignore[attr-defined]
            "the GIL is on, so these threads take turns. Something this "
            "run imported re-enabled it; set PYTHON_GIL=0 to test anyway."
        )

    # One thread alone, for the answer every thread must agree with.
    expected = all_of_them()

    # Then all of them at once. The barrier holds every worker until the
    # last has started, so they hit the scheme together rather than one
    # finishing before the next is scheduled.
    barrier = threading.Barrier(THREADS)

    def run(_: int) -> list[tuple[str, bool, str]]:
        barrier.wait()
        return all_of_them()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        outcomes = list(pool.map(run, range(THREADS)))

    assert all(outcome == expected for outcome in outcomes)
    # And the answers are the right ones, not merely consistent.
    assert all(verified for _, verified, _ in expected)
    assert all(reference == normal for reference, _, normal in expected)
