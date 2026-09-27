from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_controls as runner


def decision(*, active=False, route="discovery_cold"):
    return SimpleNamespace(active=active, route=route)


def test_inventory_is_exactly_84_cached_and_20_all_blind_receiver_rows():
    controls, sequences = runner.dataset.controls(), runner.dataset.sequences()
    sequence_count = sum(len(item.steps) for item in sequences)
    assert len(controls) == 32
    assert sequence_count == 10
    assert 2 * (len(controls) + sequence_count) == 84
    assert 2 * sequence_count == 20


def test_route_gates_require_actual_guided_and_wrong_track_fallback():
    assert runner.sequence_route_gate("pilot-dropout", 1, decision(route="guided"))[0]
    assert not runner.sequence_route_gate(
        "pilot-dropout", 1, decision(route="discovery_cold")
    )[0]
    assert runner.sequence_route_gate(
        "changed-pilot", 2, decision(active=True, route="discovery_guided_failure")
    )[0]
    assert not runner.sequence_route_gate(
        "changed-pilot", 2, decision(active=True, route="guided")
    )[0]


def test_dropout_gate_rejects_stale_active():
    assert runner.sequence_route_gate(
        "pilot-dropout", 2, decision(active=False, route="discovery_guided_failure")
    )[0]
    assert not runner.sequence_route_gate(
        "pilot-dropout", 3, decision(active=True, route="guided")
    )[0]


def test_counterbalanced_method_order():
    assert runner.METHODS[0:] + runner.METHODS[:0] == ("cached", "all_blind")
    assert runner.METHODS[1:] + runner.METHODS[:1] == ("all_blind", "cached")


def test_make_key_preserves_all_identity_dimensions():
    case = runner.dataset.controls()[0]
    key = runner.make_key(case, 1)
    assert (key.continuity_epoch, key.receiver, key.channel, key.edge, key.rate_hz,
            key.tuning_identity, key.calibration_identity) == (
        case.session, 1, case.channel, case.edge, case.rate,
        case.tuning_identity, case.calibration_identity,
    )


def test_same_detector_all_blind_comparison_fails_on_activity_or_truth_change(monkeypatch):
    case = runner.dataset.controls()[0]
    monkeypatch.setattr(
        runner,
        "truth_gates",
        lambda _case, decisions: [
            {"passed": True, "matched_trajectory": "pilot" if item.active else None}
            for item in decisions
        ],
    )
    cached = (decision(active=True), decision(active=False))
    same = (decision(active=True), decision(active=False))
    assert all(item["passed"] for item in runner.sequence_comparison(case, cached, same))
    changed = (decision(active=False), decision(active=False))
    assert not runner.sequence_comparison(case, cached, changed)[0]["passed"]
