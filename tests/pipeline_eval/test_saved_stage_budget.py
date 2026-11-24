from copy import deepcopy

import pytest

from reports.ALGO08.v3.history_risk_route_panel import read_sealed_panel
from reports.ALGO08.v3.saved_stage_budget import gate_ratios, required_reduction, stage_rows


def test_frozen_gates_charge_admission_and_require_simultaneous_reductions():
    rows = stage_rows(read_sealed_panel(6))
    assert len(rows) == 6
    assert sum(r["candidate"] for r in rows) == pytest.approx(103.103735, abs=1e-5)
    assert gate_ratios(rows, {}) == pytest.approx((.650421, .541633), abs=1e-6)
    assert required_reduction(rows, "prepare", 2) is None
    assert required_reduction(rows, "admission", 1.6) is None
    assert required_reduction(rows, "infer", 2) == pytest.approx(.400926, abs=1e-6)
    assert required_reduction(rows, "infer", 1.6) == pytest.approx(.067755, abs=1e-6)
    assert required_reduction(rows, "infer", 1) == 0


def test_partial_or_overlapping_timing_cannot_buy_a_speedup():
    panel = deepcopy(read_sealed_panel(6))
    trace = panel["enrolled"]["0138"]["result"]["prep_timing"]
    trace["infer"][0]["status"] = "failed"
    with pytest.raises(ValueError, match="Incomplete infer"):
        stage_rows(panel)
    trace["infer"][0].update(status="returned", elapsed_ns=10**13)
    with pytest.raises(ValueError, match="exceed"):
        stage_rows(panel)
