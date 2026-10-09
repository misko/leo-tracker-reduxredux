import json
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(str(Path(__file__).with_name("publish_completed.py")))


def test_incomplete_snapshot_refuses_publication(tmp_path):
    (tmp_path / "DS16_COMPLETE_SNAPSHOT.json").write_text(
        json.dumps(
            {
                "rows": [{}] * 63,
                "metrics": {"full_census_position_metrics_withheld": True},
            }
        )
    )
    MODULE["main"].__globals__["HERE"] = tmp_path
    with pytest.raises(AssertionError):
        MODULE["main"]("DS16")
    assert not list(tmp_path.glob("*.png"))


def test_complete_snapshot_retains_raw_failed_recovery(tmp_path):
    rows = []
    for i in range(63):
        endpoint = {
            "error_km": 1.0,
            "posterior_rms_hz": 50.0,
            "signal_windows": 10.0,
            "converged": True,
        }
        rows.append(
            {
                "label": f"DS16-{i + 1:03d}",
                "dataset": "DS16",
                "exact_parity": {a: {"vector": True} for a in ("fitted-c", "zero-c")},
                "trigger_count": int(i == 0),
                "candidate_fallback": False,
                "baseline_status": "complete",
                "candidate_status": "complete",
                "recoveries": (
                    [
                        {
                            "calibration_status": "prefit-unqualified",
                            "calibration_qualified": False,
                            "association_available": False,
                            "final_qualified_counts": {"fitted-c": 0, "zero-c": 0},
                        }
                    ]
                    if i == 0
                    else []
                ),
                "stage_failures": {p: [] for p in ("baseline", "candidate")},
                "runtime": {
                    p: {"known_elapsed_s": 2.0, "completed_slices": 1}
                    for p in ("baseline", "candidate")
                },
                "arms": {
                    a: {p: endpoint for p in ("baseline", "candidate")}
                    for a in ("fitted-c", "zero-c")
                },
            }
        )
    metrics = {
        "full_census_position_metrics_withheld": False,
        "arms": {
            a: {
                "paired_regressions": [],
                **{
                    p: {k: 1.0 for k in ("mean_km", "median_km", "p95_km", "worst_km")}
                    for p in ("baseline", "candidate")
                },
            }
            for a in ("fitted-c", "zero-c")
        },
    }
    (tmp_path / "DS16_COMPLETE_SNAPSHOT.json").write_text(
        json.dumps(
            {
                "rows": rows,
                "metrics": metrics,
                "datasets": {"DS16": metrics},
                "protocol_sha256": "synthetic",
                "receipt_sha256": {},
            }
        )
    )
    for name in ("plot_completed.py", "report_completed.py", "publish_completed.py"):
        (tmp_path / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    MODULE["main"].__globals__["HERE"] = tmp_path
    MODULE["main"]("DS16")
    text = (tmp_path / "DS16_COMPLETE_SNAPSHOT.md").read_text()
    assert '"prefit-unqualified": 1' in text
    assert "DS16-001" in text
    assert "63/63 selected endpoints qualified" in text
