from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from leo.analysis.research.cross_family_qin_predictive_scoring import (
    load_cross_family_qin_scoring_config,
    score_cross_family_qin_evidence,
)
from tools import run_cross_family_qin_predictive_scoring as runner

PROJECT_ROOT = Path(__file__).parents[2]
TOOL = PROJECT_ROOT / "tools/run_cross_family_qin_predictive_scoring.py"
CONFIG = PROJECT_ROOT / runner.DEFAULT_CONFIG


def test_verify_only_reports_descriptive_result_without_writes() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(TOOL), "--verify-only"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    assert value["result_digest"] == (
        "sha256:e76b85d63b0a3567ebaf1f6a2f9fab98bc4db032d381e25cca6820a4cfdcf12a"
    )
    assert value["truth_arm_equal_accuracy"] == 0.5
    assert value["formal_95_percent_rank_pair_count_sufficient"] is False
    assert value["new_iq_read"] is False


def test_outputs_are_exclusive(tmp_path: Path) -> None:
    config = load_cross_family_qin_scoring_config(CONFIG)
    result = score_cross_family_qin_evidence(
        (PROJECT_ROOT / config.evidence_path).read_bytes(),
        (PROJECT_ROOT / config.protocol_path).read_bytes(),
        config,
    )
    result_path = tmp_path / "result.json"
    result_path.write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="must be absent"):
        runner._write_outputs(  # noqa: SLF001
            result_path=result_path,
            report_path=tmp_path / "report.md",
            result=result,
            repository_root=PROJECT_ROOT,
        )


def test_tool_has_no_database_http_storage_or_iq_imports() -> None:
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(
        value.startswith(
            (
                "sqlalchemy",
                "psycopg",
                "requests",
                "leo.storage",
                "leo.analysis.qam",
                "leo.analysis.starlink.templates",
            )
        )
        for value in imported
    )
