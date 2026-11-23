import importlib
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("dense_protected_cost")


def test_model_reproduces_archived_ratios_and_holds_acquisition_constant(study):
    archived = study.read(study.DATA / "regional-dense-budget.json")
    rows = study.read(study.DATA / "acquisition-throughput.json")["rows"]
    unchanged = study.timing_models(archived["solve_cpu_s"], archived, rows)
    reduced = study.timing_models(16., archived, rows)
    for roster, panel in unchanged["panels"].items():
        for reader, scenario in panel["scenarios"].items():
            other = reduced["panels"][roster]["scenarios"][reader]
            assert scenario["reader_MB_s"] == other["reader_MB_s"]
            assert scenario["old_unfiltered_ratio"] == scenario["protected_ratio"]
            assert other["protected_ratio"] == other["ratio_with_16_s_solve"]
    assert unchanged["panels"]["16"]["unchanged_outcomes"] == 1


def test_charged_buckets_keep_repair_veto_and_fallback_without_double_counting(study):
    trial = dict(solve={"cpu_s": 10.}, early_regional=[{"cpu_s": 1.}], route_details=dict(
        candidate_pre_evidence_clocks={"cpu_s": 3.}, cold_clocks={"cpu_s": 2.},
        local_future_repair=dict(cost={"cpu_s": 1.}, refit_clocks={"cpu_s": .5}, exterior_clocks={"cpu_s": .5}),
        fallback_clocks={"cpu_s": 2.}))
    counts = study.clock_buckets(trial, {"selection": {"cpu_s": .5}})
    assert counts["protected_repair"] == 1.
    assert counts["protected_exterior"] == .5
    assert counts["fallback"] == 2. and counts["solve_other"] == 2.
    assert sum(counts.values()) == 10.
