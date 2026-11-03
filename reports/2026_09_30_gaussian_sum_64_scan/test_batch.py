import json
import time

import pytest

from batch import ordered_units, run_unit


def test_selection_interleaves_64_unique_sessions_without_dropping_final_scan():
    selection = {"selected": {
        name: [{"unit_id": f"{name}-{i}", "session_id": f"s-{name}-{i}"} for i in range(n)]
        for name, n in (("DS9", 22), ("DS10", 21), ("DS11", 21))}}
    units = ordered_units(selection)
    assert len(set(units)) == 64
    assert units[:3] == ["DS9-0", "DS10-0", "DS11-0"]
    assert units[-1] == "DS9-21"
    selection["selected"]["DS11"][0]["session_id"] = "s-DS9-0"
    with pytest.raises(ValueError, match="identities"):
        ordered_units(selection)


def test_scientific_failure_does_not_skip_authorized_baselines(tmp_path):
    called = []
    def fake(unit, arm, prior, output):
        called.append((unit, arm, prior))
        path = output / f"{arm}.json"
        path.write_text(json.dumps({"status": "gate_failed" if arm == "gaussian_sum" else "complete"}))
        return {"prediction_path": str(path), "unit_id": unit, "arm": arm,
                "status": "complete", "wall_seconds": .1}
    rows = run_unit("DS9-0", tmp_path, time.monotonic() + 900, fake)
    assert [call[1] for call in called] == ["gaussian_sum", "greedy", "prior_only"]
    assert [row["native_status"] for row in rows] == ["gate_failed", "complete", "complete"]


def test_insufficient_batch_budget_preserves_unstarted_arms(tmp_path):
    def forbidden(*args):
        raise AssertionError("must not launch")
    rows = run_unit("DS9-0", tmp_path, time.monotonic() + 1, forbidden)
    assert len(rows) == 3
    assert all(row["native_status"] == "not_started_batch_budget" for row in rows)
