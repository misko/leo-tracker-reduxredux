from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest
from tools import run_cross_family_qin_injection as runner

PROJECT_ROOT = Path(__file__).parents[2]
TOOL = PROJECT_ROOT / "tools/run_cross_family_qin_injection.py"
AMENDMENT = PROJECT_ROOT / "config/analysis/satellite-pnt-cross-family-injection-execution-v1.json"
AMENDMENT_ATTEMPT2 = (
    PROJECT_ROOT / "config/analysis/satellite-pnt-cross-family-injection-execution-v2.json"
)
PROTOCOL = Path("config/analysis/satellite-pnt-cross-family-injection-protocol-v1.json")
OUTPUT_ROOT = Path("reports/figures/2026_08_27_satellite_pnt_cross_family_injection_v1")
REPORT = Path("reports/2026_08_27_satellite_pnt_cross_family_injection_results.md")
OUTPUT_ROOT_ATTEMPT2 = Path(
    "reports/figures/2026_08_27_satellite_pnt_cross_family_injection_attempt2"
)
REPORT_ATTEMPT2 = Path(
    "reports/2026_08_27_satellite_pnt_cross_family_injection_attempt2_results.md"
)


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


def test_attempt1_authority_rejects_corrected_implementation_bytes() -> None:
    with pytest.raises(ValueError, match="hash differs: tools/run_cross_family_qin_injection.py"):
        runner._validate_execution_authority(  # noqa: SLF001
            PROJECT_ROOT,
            AMENDMENT,
            protocol_path=PROTOCOL,
            output_root=OUTPUT_ROOT,
            report_path=REPORT,
        )


def test_attempt2_authority_binds_corrected_implementation() -> None:
    authority = runner._validate_execution_authority(  # noqa: SLF001
        PROJECT_ROOT,
        AMENDMENT_ATTEMPT2,
        protocol_path=PROTOCOL,
        output_root=OUTPUT_ROOT_ATTEMPT2,
        report_path=REPORT_ATTEMPT2,
    )
    assert authority["implementation_commit"] == ("57036c53d95587b63f0b7c891bb61c3e50a10e84")


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


def test_persisted_json_preserves_semantic_digest_inputs() -> None:
    payload = {
        "diagnostics": {"background_power": 3.513155020770348e-08},
        "rows": [
            {
                "measured_cfo_hz": 69_866.16012345678,
                "standard_uncertainty_hz": 12.345678901234567,
            }
        ],
    }

    persisted = json.loads(runner._json_bytes(payload))  # noqa: SLF001

    assert canonical_digest(persisted) == canonical_digest(payload)
