"""A failed available member cannot disappear from the cohort denominator."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace


def test_unavailable_and_failed_members_remain_explicit(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("run_merged_catalogue_cohort")
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "coverage.json").write_text(
        json.dumps(
            [
                dict(source_id="test-stage-failure-20261017", status="tracks_evaluated"),
                dict(source_id="adaptive", status="adaptive_observation_adapter_unavailable"),
                dict(source_id="missing", status="no_pinned_tracking_input"),
            ]
        )
    )
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="injected stage failure"),
    )
    output = tmp_path / "output"
    tool.run(cohort, output, 1, 0.0, 0.0)
    summary = json.loads((output / "summary.json").read_text())
    assert summary["members"] == 3 and summary["failed"] == 1 and summary["completed"] == 0
    rows = json.loads((output / "execution.json").read_text())
    assert {r["status"] for r in rows} == {
        "failed",
        "adaptive_observation_adapter_unavailable",
        "no_pinned_tracking_input",
    }
    assert summary["position_estimates"] == 0 and not summary["sub_0_5km_target_verified"]
