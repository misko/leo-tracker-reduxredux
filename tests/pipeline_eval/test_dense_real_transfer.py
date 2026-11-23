from dataclasses import dataclass
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module


def test_degree_change_retains_all_other_support_settings(modules):
    @dataclass(frozen=True)
    class Config:
        max_degree: int = 4
        min_points: int = 8
        points_per_coefficient: int = 4
        untouched: int = 29

    operation = modules("degree_only_transfer").degree_only
    assert operation(Config()) == Config(max_degree=2)
    with pytest.raises(ValueError, match="configuration changed"):
        operation(Config(min_points=6))


def test_gate_requires_both_errors_and_correct_region_decisions(modules):
    accepted = modules("degree_only_score").accepted
    arms = {"c0": {"delta_error_km": .25}, "fitted_c": {"delta_error_km": -.2}}
    assert accepted(arms, "complete", "withheld")
    assert not accepted(arms, "complete", "complete")
    assert not accepted(arms, "withheld", "withheld")
    arms["c0"]["delta_error_km"] = .251
    assert not accepted(arms, "complete", "withheld")


def test_disjoint_clocks_include_entire_receiver_and_process_tail(modules):
    costs = modules("dense_measured_budget").cost_partition
    assert costs(60, 30, 15, 23) == dict(receiver=15, other_acquisition=15, solver=23, remaining=7)
    with pytest.raises(ValueError):
        costs(52, 30, 15, 23)


def test_dense_raw_model_uses_correct_detector_control_and_unchanged_clocks(modules):
    ledger = modules("dense_measured_budget").evaluate()
    assert sum(ledger["cpu_s"].values()) == pytest.approx(ledger["whole_cpu_s"])
    assert ledger["elapsed_s"] > ledger["whole_cpu_s"]
    assert ledger["controls"]["named_launcher"]["wall_ratio"] > .5
    assert ledger["controls"]["qualification"]["wall_ratio"] > ledger["controls"]["named_launcher"]["wall_ratio"]
    for graph in ledger["modeled"].values():
        assert graph["scenarios"]["observed_dense"]["ratios"][0] > graph["scenarios"]["fastest_prefix"]["ratios"][0]
