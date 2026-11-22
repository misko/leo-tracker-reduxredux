from importlib import import_module
from pathlib import Path

import pytest


def test_restoring_only_the_missing_donor_recovers_primary(monkeypatch):
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(reports))
    trace = import_module("primary_donor_trace")
    row = dict(receiver_id=1, channel=2, actual_rf_hz=10e9, valid_start_counter=30_000_000,
               candidates=[dict(candidate_rank=0, fractional_tracking_cfo_hz=1000, fractional_margin=1.)])
    full = [(0, (75000, 1000)), (10_000_000, (1000,)), (20_000_000, (1000,))]
    partial = [(0, (75000,)), *full[1:]]
    result = trace.explain(row, full, partial, [13, 21, 29])
    assert result["current_factors"] == [dict(rank=0, hz=1000, full_votes=3, conditional_votes=2)]
    assert result["selected_rank_on_full_history"] == 0
    assert result["selected_rank_on_conditional_history"] is None
    donor, = result["differing_donors"]
    assert donor["visit"] == 13 and donor["selected_rank_after_restoring_slot"] == 0
    with pytest.raises(ValueError, match="chronological donor slots"):
        trace.explain(row, full, list(reversed(partial)), [13, 21, 29])
