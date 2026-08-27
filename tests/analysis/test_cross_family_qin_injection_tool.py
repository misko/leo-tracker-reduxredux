from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from tools import run_cross_family_qin_injection as runner

PROJECT_ROOT = Path(__file__).parents[2]
TOOL = PROJECT_ROOT / "tools/run_cross_family_qin_injection.py"


def test_tool_help_is_available_without_external_data() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(TOOL), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--verify-only" in result.stdout


def test_missing_execution_amendment_fails_before_protocol_or_iq(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="hash-bound amendment"):
        runner._validate_execution_authority(  # noqa: SLF001
            PROJECT_ROOT,
            tmp_path / "missing.json",
            protocol_path=Path(
                "config/analysis/satellite-pnt-cross-family-injection-protocol-v1.json"
            ),
            output_root=Path("reports/figures/never"),
            report_path=Path("reports/never.md"),
        )


def test_tool_has_no_database_http_or_storage_imports() -> None:
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(
        value.startswith(("sqlalchemy", "psycopg", "requests", "leo.storage")) for value in imported
    )


def test_canonical_outputs_are_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(ValueError, match="absent"):
        runner._write_outputs(  # noqa: SLF001
            output_root=output,
            report_path=tmp_path / "report.md",
            evidence={"pair_summaries": []},
            execution={},
        )
