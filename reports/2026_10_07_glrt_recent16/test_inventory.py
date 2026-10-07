"""Outcome-free selection and sealed metrics admission checks."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory


def rows():
    history = [{"session_id": str(i), "captured_at": f"2026-10-07T{i:02d}:00:00Z",
                "input_manifest_sha256": f"sha256:{i}"} for i in range(20)]
    status = {r["session_id"]: dict(r, metrics_manifest_sha256="sha256:sealed",
                                  checkpoint_visits=20, total_visits=20,
                                  state="metrics_ready") for r in history}
    return history, status


def test_newest_capture_order_and_no_tracking_quality_filter():
    history, status = rows()
    history.reverse()
    for h in history:
        h["capture_qualified"] = False
        h["tracking_complete"] = False
    selected = inventory.select_recent(history, status)
    assert [r["session_id"] for r in selected] == [str(i) for i in range(19, 3, -1)]


def test_partial_excluded_figures_not_required_and_bindings_checked():
    history, status = rows()
    status["19"]["metrics_manifest_sha256"] = None
    status["18"]["checkpoint_visits"] = 19
    selected = inventory.select_recent(history, status)
    assert selected[0]["session_id"] == "17"
    status["17"]["input_manifest_sha256"] = "sha256:wrong"
    with pytest.raises(ValueError, match="digest differs"):
        inventory.select_recent(history, status)
