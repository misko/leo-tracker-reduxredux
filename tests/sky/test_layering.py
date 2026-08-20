"""Guard the layering rules AGENTS.md states for analysis code.

``leo.sky`` is pure science.  If it ever grows an import of PostgreSQL, HTTP,
the CLI or a concrete storage module, the boundary has been crossed and these
tests fail rather than the violation being noticed later in review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import leo.sky

FORBIDDEN_ROOTS = (
    "sqlalchemy",
    "alembic",
    "psycopg",
    "fastapi",
    "starlette",
    "uvicorn",
    "typer",
    "httpx",
    "leo.catalog",
    "leo.api",
    "leo.cli",
    "leo.storage",
    "leo.operations",
    "leo.artifacts",
    "leo.processing",
    "leo.presentation",
    "leo.application",
)

SKY_ROOT = Path(leo.sky.__file__).parent


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _sky_modules() -> list[Path]:
    return sorted(SKY_ROOT.glob("*.py"))


def test_the_sky_package_has_modules_to_check() -> None:
    assert len(_sky_modules()) >= 5


@pytest.mark.parametrize("path", _sky_modules(), ids=lambda path: path.name)
def test_sky_science_imports_no_infrastructure(path: Path) -> None:
    offending = {
        module
        for module in _imported_modules(path)
        for root in FORBIDDEN_ROOTS
        if module == root or module.startswith(f"{root}.")
    }
    assert not offending, f"{path.name} imports infrastructure: {sorted(offending)}"


@pytest.mark.parametrize("path", _sky_modules(), ids=lambda path: path.name)
def test_sky_science_depends_only_on_contracts_and_itself(path: Path) -> None:
    leo_imports = {module for module in _imported_modules(path) if module.startswith("leo.")}
    unexpected = {
        module
        for module in leo_imports
        if not (module.startswith("leo.sky") or module.startswith("leo.contracts"))
    }
    assert not unexpected, f"{path.name} reaches outside contracts: {sorted(unexpected)}"


def test_sky_science_never_reads_a_clock() -> None:
    """Every instant is supplied by the caller so predictions are reproducible."""

    for path in _sky_modules():
        source = path.read_text()
        for forbidden in ("time.time", "datetime.now", "datetime.utcnow", "time_ns()"):
            assert forbidden not in source, f"{path.name} reads a clock via {forbidden}"
