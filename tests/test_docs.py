"""The documentation must name things that exist.

The README carried six references to expected_collisions() after 1.0.0
removed it, including a runnable `from compactref import expected_collisions`
that would have raised ImportError for anyone who copied it. Prose drifts
away from code silently; this makes it fail loudly.

An earlier version of this file could not have caught that. It skipped any
name it did not already recognise -- which is precisely every name that
would be stale -- and then asserted that what remained existed, which was
true by construction. A test that cannot fail is worse than no test: it
reads as coverage.

So these check three things that can genuinely fail:

1. Every name the README imports from compactref exists. This is the bug
   above: a copied snippet must not raise ImportError.
2. Every method the README calls on a scheme exists.
3. No removed name is recommended, outside the sentence saying it is gone.

They do not try to prove that every call in the README is one of ours. The
examples call SQLAlchemy, zoneinfo and the caller's own code, and an
allowlist of everything foreign would need updating whenever an example
grew a line -- brittle in the direction of noise, which teaches people to
ignore the test.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import compactref
from compactref import CompactRef


README = pathlib.Path(__file__).parent.parent / "README.md"

# Named in the README only to say they are gone. They must NOT exist.
REMOVED = {"expected_collisions", "verify_reference"}


def readme() -> str:
    return README.read_text()


def imported_from_compactref() -> set[str]:
    """Every name the README imports from the package.

    Two spellings, and the second must not be allowed to run past its
    closing bracket into the next statement:

        from compactref import CompactRef
        from compactref import (
            CompactRef,
            generate_reference,
        )
    """
    text = readme()
    names: set[str] = set()

    # from compactref import a, b, c
    for match in re.finditer(r"from compactref import ([^(\n]+)$", text, re.M):
        names |= {n.strip() for n in match.group(1).split(",") if n.strip()}

    # from compactref import (\n a,\n b,\n )
    for match in re.finditer(r"from compactref import \(([^)]*)\)", text):
        names |= {n.strip() for n in match.group(1).split(",") if n.strip()}

    return names


def methods_called_on_a_scheme() -> set[str]:
    """Every method the README calls on something built from CompactRef.

    Finds the variables assigned a CompactRef, then what is called on them.
    """
    text = readme()

    schemes = set(re.findall(r"^(\w+)\s*=\s*CompactRef\(", text, re.MULTILINE))
    schemes |= set(
        re.findall(r"^(\w+)\s*=\s*CompactRef\($", text, re.MULTILINE)
    )

    called: set[str] = set()
    for scheme in schemes:
        called |= set(re.findall(rf"\b{scheme}\.(\w+)", text))

    return called


def test_the_readme_imports_only_names_that_exist() -> None:
    """A copied snippet must not raise ImportError.

    This is the check that would have caught expected_collisions(): the
    README imported it in a runnable block after 1.0.0 removed it.
    """
    public = set(compactref.__all__)
    imported = imported_from_compactref()

    assert imported, "the README imports nothing from compactref?"

    for name in sorted(imported):
        assert name in public, (
            f"README has `from compactref import {name}`, which is not "
            f"exported. Anyone copying that block gets an ImportError."
        )
        assert hasattr(compactref, name), (
            f"{name} is in __all__ but not importable"
        )


def test_the_readme_calls_only_methods_a_scheme_has() -> None:
    """`orders.verifyy(...)` should fail the build, not the reader."""
    attributes = {name for name in dir(CompactRef) if not name.startswith("_")}
    called = methods_called_on_a_scheme()

    assert called, "the README calls nothing on a scheme?"

    for name in sorted(called):
        assert name in attributes, (
            f"README calls scheme.{name}(), which CompactRef does not have"
        )


def test_the_readme_recommends_no_function_that_was_removed() -> None:
    """Except where it is telling you they were removed."""
    lines = readme().splitlines()

    for name in REMOVED:
        assert not hasattr(compactref, name), f"{name} is back?"

        for index, line in enumerate(lines):
            if name not in line:
                continue

            # Allowed only where the surrounding lines say it is gone — the
            # sentence announcing the removal, or the `# before` half of a
            # migration snippet, whose marker sits on the line above.
            context = " ".join(lines[max(0, index - 2) : index + 2]).lower()
            explains_removal = any(
                word in context
                for word in ("removed", "gone", "before", "deprecated")
            )

            assert explains_removal, (
                f"README line still uses the removed {name}(): {line.strip()}"
            )


@pytest.mark.parametrize(
    "name",
    [
        "collision_probability",
        "expected_colliding_pairs",
        "expected_rejected_inserts",
        "max_references",
        "suffix_length_for",
    ],
)
def test_the_sizing_table_names_the_real_functions(name: str) -> None:
    # The table in "Choosing a suffix length" is the answer to "which of
    # these do I want". If it names something that does not exist, it is
    # worse than no table.
    assert hasattr(compactref, name)
    assert f"`{name}()`" in readme()
