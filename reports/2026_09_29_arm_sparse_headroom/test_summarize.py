from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("sparse_headroom_summarize", HERE / "summarize.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_distribution_uses_nearest_rank_and_deadline_counts() -> None:
    result = MODULE.distribution([120, 1, 101, 2, 3])
    assert result == {
        "count": 5,
        "mean": 45.4,
        "p50": 3,
        "p95": 120,
        "max": 120,
        "over_100_ms": 2,
        "at_least_120_ms": 1,
    }
    assert MODULE.distribution([]) is None
    with pytest.raises(AssertionError):
        MODULE.distribution([math.nan])
    with pytest.raises(AssertionError):
        MODULE.distribution([-0.1])


def test_science_removes_only_row_timings() -> None:
    candidate = {"epoch": 7, "margin": 0.5}
    row = {
        "receiver_id": 0,
        "conditioned_bins_screened": 25,
        "timings_ms": {"total_cpu": 2.0},
        "candidates": [candidate],
    }
    assert MODULE.science({"rows": [row]}) == [
        {"receiver_id": 0, "conditioned_bins_screened": 25, "candidates": [candidate]}
    ]


def test_stress_identity_normalizes_only_published_completion_representation() -> None:
    from stress import identity

    def call(complete, score=0.25):
        return {"rows": [{"candidates": [{"glrt_complete": complete, "margin": score}]}]}

    assert identity(call(True)) == identity(call(1))
    assert identity(call(False)) == identity(call(0))
    assert identity(call(True, 0.25000000000000006)) != identity(call(True))
    with pytest.raises(AssertionError):
        identity(call(2))


def test_thermal_summary_keeps_missing_and_direction_counts_separate() -> None:
    records = [
        {
            "result": {
                "thermal_available_before": True,
                "thermal_available_after": True,
                "thermal_millidegrees_before": 40_000,
                "thermal_millidegrees_after": 40_250,
            }
        },
        {
            "result": {
                "thermal_available_before": True,
                "thermal_available_after": True,
                "thermal_millidegrees_before": 41_000,
                "thermal_millidegrees_after": 40_900,
            }
        },
        {
            "result": {
                "thermal_available_before": False,
                "thermal_available_after": False,
                "thermal_millidegrees_before": 0,
                "thermal_millidegrees_after": 0,
            }
        },
    ]
    result = MODULE.thermal_summary(records)
    assert result["available_calls"] == 2
    assert result["missing_calls"] == 1
    assert result["warming_calls"] == 1
    assert result["cooling_calls"] == 1
    assert result["flat_calls"] == 0
    assert result["absolute_delta_millidegrees"]["max"] == 250
    for field in (
        "before_millidegrees",
        "after_millidegrees",
        "absolute_delta_millidegrees",
    ):
        assert "over_100_ms" not in result[field]
        assert "at_least_120_ms" not in result[field]


def test_load_binds_summary_end_to_end_arrays_to_call_order(tmp_path: Path) -> None:
    (tmp_path / "execution-panel.json").write_text("{}")
    folder = tmp_path / "local" / "candidate"
    folder.mkdir(parents=True)
    group = {
        "id": "2500000-lower-000",
        "calls": [{"sequence": 0}, {"sequence": 1}],
    }
    calls = [
        {
            "serialization_cpu_ms": 0.1,
            "serialization_wall_ms": 0.2,
            "result": {
                "kind": "call",
                "sequence": sequence,
                "stride_ms": 120,
                "dwell_ms": 120,
                "rows": [
                    {"receiver_id": 0, "probe_start_ms": 0},
                    {"receiver_id": 1, "probe_start_ms": 0},
                ],
            },
        }
        for sequence in range(2)
    ]
    rows = [
        {"kind": "setup"},
        *calls,
        {
            "kind": "summary",
            "destroy_status": 0,
            "e2e_cpu_ms": [11.0, 12.0],
            "e2e_wall_ms": [13.0, 14.0],
        },
    ]
    data = "".join(json.dumps(row) + "\n" for row in rows)
    output = folder / (group["id"] + ".jsonl")
    output.write_text(data)
    manifest = {
        "execution_panel_sha256": MODULE.digest(tmp_path / "execution-panel.json"),
        "files": {output.name: MODULE.digest(output)},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    previous = MODULE.HERE
    try:
        MODULE.HERE = tmp_path
        records, _, _, _ = MODULE.load("candidate", [group])
    finally:
        MODULE.HERE = previous
    assert [(row["e2e_cpu_ms"], row["e2e_wall_ms"]) for row in records] == [
        (11.0, 13.0),
        (12.0, 14.0),
    ]
