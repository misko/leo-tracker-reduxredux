from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest


def test_future_evidence_recovers_first_observation_without_changing_counters(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    supported = import_module("bidirectional_selection").supported
    rows = [
        dict(
            receiver_id=0,
            channel=1,
            actual_rf_hz=10e9,
            valid_start_counter=index * 2_000_000,
            candidates=[
                dict(
                    fractional_tracking_cfo_hz=1000 + 100 * index,
                    fractional_margin=0.4,
                    candidate_rank=0,
                )
            ],
        )
        for index in range(7)
    ]
    snapshot = deepcopy(rows)
    result, counts = supported(rows)
    assert snapshot == result == rows
    assert counts == dict(original=7, both=1, past_only=3, future_only=3, neither=0)
    rows[0]["receiver_id"] = 1
    assert supported(rows)[0][0]["candidates"] == []
    rows[0]["candidates"] *= 2
    with pytest.raises(ValueError, match="single-factor"):
        supported(rows)


def test_assignment_churn_counts_roles_and_satellites_separately(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    compare = import_module("bidirectional_selection").assignment_changes
    before = [("a", 1, "curved"), ("b", 2, "conditional"), ("d", 2, "curved")]
    after = [("a", 3, "curved"), ("b", 2, "curved"), ("c", 4, "conditional")]
    assert compare(before, after) == dict(
        before=3, after=3, added=1, lost=1, changed_satellite=1, changed_role=1
    )
    with pytest.raises(ValueError, match="Duplicate"):
        compare(before, before + [before[0]])


def test_single_case_quality_repair_must_satisfy_both_gates(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    price = import_module("quality_retry_budget").price
    rows = [
        dict(case=str(i), stages=[5, 3, 2], compressed_MB=amount)
        for i, amount in enumerate((1, 1, 0.1, 1))
    ]
    result = price(rows, 1, 3, 1, 0)
    assert result["baseline"] == (0.4, 15.1 / 40)
    assert result["summed_slack_s"] == pytest.approx(4.9)
    assert result["routes_to_stock_passing"] == 0
    assert result["cases"]["0"]["allowed_repair_s"] == pytest.approx(4.9)
    assert price(rows, 3, 3, 1, 0)["cases"]["0"]["allowed_repair_s"] is None
