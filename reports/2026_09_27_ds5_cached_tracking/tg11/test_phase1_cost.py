from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_phase1_cost as runner


def test_timing_membership_is_exactly_two_per_rate():
    cases = runner.dataset.timing_cases()
    assert len(cases) == 4
    assert [sum(case.rate == rate for case in cases) for rate in runner.dataset.RATES] == [2, 2]


def test_per_rate_summary_requires_complete_six_calls_and_both_gates():
    rows = []
    for rate, app, candidate in ((2_500_000, 1000.0, 90.0), (5_000_000, 4000.0, 300.0)):
        for case in range(2):
            measurements = []
            for repeat in range(3):
                measurements += [
                    {"method": "application", "process_cpu_ms": app,
                     "wall_ms": app + repeat},
                    {"method": "tg11", "process_cpu_ms": candidate,
                     "wall_ms": candidate + repeat},
                ]
            rows.append({"rate_hz": rate, "measurements": measurements})
    summary = runner.summarize(rows)
    assert summary["2500000"]["process_cpu_speedup"] == 1000 / 90
    assert summary["2500000"]["cost_gate_passed"]
    assert summary["5000000"]["cost_gate_passed"]
    rows[0]["measurements"].pop()
    assert not runner.summarize(rows)["2500000"]["cost_gate_passed"]


@dataclass
class FakeObservation:
    receiver: int
    probe_index: int
    probe_start_sample: int
    dwell_epoch_sample: float
    local_epoch_sample: float
    tracking_cfo_hz: float
    margin: float = 0.1
    supported: bool = True
    fractional_complete: bool = True


@dataclass
class FakePair:
    receiver: int
    first: FakeObservation
    second: FakeObservation


@dataclass
class FakeDecision:
    active: bool
    pair: FakePair | None


def test_scientific_comparison_fails_closed_for_reference_extra_and_loss(monkeypatch):
    case = runner.dataset.timing_cases()[0]
    monkeypatch.setattr(runner.dataset, "reference_positive_pair_inventory", lambda *_: ())
    monkeypatch.setattr(
        runner.dataset,
        "associate_candidate_to_reference",
        lambda *_: runner.dataset.Association(
            False, None, None, None, None, "no reference inventory"
        ),
    )
    inactive = FakeDecision(False, None)
    analysis = SimpleNamespace(first=None)
    assert runner.scientific_comparison(case, analysis, ((inactive, inactive), inactive))["passed"]
    active = FakeDecision(True, SimpleNamespace(receiver=0))
    assert not runner.scientific_comparison(case, analysis, ((active, inactive), active))["passed"]


def test_method_order_is_counterbalanced():
    assert runner.METHODS[0:] + runner.METHODS[:0] == ("application", "tg11")
    assert runner.METHODS[1:] + runner.METHODS[:1] == ("tg11", "application")


def test_application_serialization_handles_pydantic_first_detection():
    first = runner.scanner_detector.Glrt64FirstDetection(
        receiver_id=0, probe_index=2, probe_start_ms=20, candidate_rank=0,
        epoch_sample=100, acquired_cfo_hz=1.0, residual_cfo_hz=2.0,
        tracking_cfo_hz=3.0, exact_score=0.2, control_score=0.1, margin=0.1,
    )
    analysis = runner.scanner_detector.DwellGlrt64Analysis(
        first=first, decision_best_margin=0.1, full_best_margin=0.1,
        reason="test", probes=(),
    )
    payload = runner.serialize_application(analysis)
    assert payload["first"]["receiver_id"] == 0
    runner.stable_json(payload)
