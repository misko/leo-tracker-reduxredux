from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_ten_dwell_raw_doppler.py"
    spec = importlib.util.spec_from_file_location("report_ten_dwell_raw_doppler_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_inputs(path: Path) -> list[dict[str, str]]:
    dwells = [
        {"label": f"T{index:02d}", "session_id": f"session-{index}", "run_id": f"run-{index}"}
        for index in range(1, 11)
    ]
    path.write_text(
        json.dumps(
            {
                "schema": "org.leo.research.ten-dwell-raw-doppler-inputs/v1",
                "dwells": dwells,
            }
        )
    )
    return dwells


def _write_result(root: Path, row: dict[str, str], index: int) -> None:
    diagnostics = {
        "frame_count": 100,
        "qualified_frame_count": 80,
        "coherent_frame_count": 50,
        "ramp_count": 5,
        "glrt_window_count": 20,
        "overall_glrt_rate_hz_s": -6_000.0 + index,
        "overall_glrt_rate_sigma_hz_s": 10.0,
        "local_corrected_rate_hz_s": -4_000.0 + index,
        "local_p025_hz_s": -4_100.0 + index,
        "local_p975_hz_s": -3_900.0 + index,
        "local_practical_sigma_hz_s": 50.0,
        "rate_correction_hz_s": 2_000.0,
        "odd_validation_reduction_percent": 50.0,
        "strict_gate_rate_spread_hz_s": 20.0,
        "glrt_rate_errors": {"frame_count": 50, "validation_rms_hz": 60.0},
        "local_rate_errors": {"frame_count": 50, "validation_rms_hz": 30.0},
    }
    document = {
        "schema": "org.leo.research.raw-dwell-doppler/v1",
        "session_id": row["session_id"],
        "run_id": row["run_id"],
        "status": "complete",
        "selected_attempt_rank": 1,
        "candidate_count": 4,
        "selected": {
            "candidate": {
                "stream_id": "stream-0",
                "receiver_id": 1,
                "branch_id": f"branch-{index}",
                "start_s": 1.0,
                "end_s": 2.0,
            },
            "result": {"diagnostics": diagnostics},
        },
    }
    (root / f"T{index:02d}.json").write_text(json.dumps(document))


def test_ten_dwell_results_are_identity_closed_and_pool_matched_errors(
    tmp_path: Path,
) -> None:
    tool = _tool()
    inputs = tmp_path / "inputs.json"
    rows = _write_inputs(inputs)
    for index, row in enumerate(rows, start=1):
        _write_result(tmp_path, row, index)

    specs = tool.validated_inputs(inputs)
    pairs = tool.load_results(specs, tmp_path)
    statistics = tool.aggregate_statistics(tuple(item[0] for item in pairs))

    assert len(pairs) == 10
    assert statistics["complete_dwell_count"] == 10
    assert statistics["first_rank_complete_count"] == 10
    assert statistics["coherent_frame_count"] == 500
    assert statistics["pooled_glrt_odd_validation_rms_hz"] == pytest.approx(60.0)
    assert statistics["pooled_local_odd_validation_rms_hz"] == pytest.approx(30.0)
    assert statistics["pooled_odd_validation_reduction_percent"] == pytest.approx(50.0)


def test_ten_dwell_inputs_reject_duplicate_identity(tmp_path: Path) -> None:
    tool = _tool()
    inputs = tmp_path / "inputs.json"
    rows = _write_inputs(inputs)
    rows[-1]["session_id"] = rows[0]["session_id"]
    rows[-1]["run_id"] = rows[0]["run_id"]
    inputs.write_text(
        json.dumps(
            {
                "schema": "org.leo.research.ten-dwell-raw-doppler-inputs/v1",
                "dwells": rows,
            }
        )
    )

    with pytest.raises(ValueError, match="unique"):
        tool.validated_inputs(inputs)
