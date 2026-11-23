from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def trial(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(path))
    return import_module("verified_anchor_stack")


def factor(epoch, hz):
    return (0, epoch, 0., hz, .95, .1)


def test_full_anchors_alone_update_history_and_force_confirmation(trial):
    state = trial.History(visits=1)
    assert state.force() is None
    state.observe(0, (factor(13000, 52000),))
    assert state.force() == "confirmation"
    state.observe(4 * trial.ADC, (factor(13000, 56000),))
    assert state.force() is None
    assert state.anchors[-1][0] == 4 * trial.ADC
    state.observe(6 * trial.ADC, (factor(13000, 58000), factor(12000, -62000)))
    assert not state.anchors


def test_bank_is_causal_signed_and_caps_lookback(trial):
    state = trial.History(visits=4)
    state.observe(0, (factor(200, -62000),))
    state.observe(4 * trial.ADC, (factor(200, -58000),))
    signal = (-800_000., 800_000., np.zeros(10_487, dtype=np.float32), 0.)
    assert trial.score_bank(state, 4 * trial.ADC, signal, stack=True) is None
    for i in range(1, 7):
        epoch, hz, candidates, used = trial.score_bank(state, (4 + i) * trial.ADC, signal, stack=True)
        assert epoch == 200.
        assert hz == -58000. + 1000 * i
        assert len(candidates) == 9
        assert used == min(i, 4)
    assert trial.score_bank(state, 21 * trial.ADC, signal, stack=True) is None
    assert len(state.anchors) == 2


def test_new_arrival_guard_preserves_absolute_sign(trial):
    projection = (500, -40000, [-39500, -40000, -40500], 2)
    assert trial.within_bank(-37500, projection)
    assert not trial.within_bank(40000, projection)
    assert not trial.within_bank(-40000, None)


def test_dense_model_uses_all_verifier_cpu_per_positive_factor(trial):
    acq = {"detector_groups": {"anchors": {"cpu_s": 5}, "nonanchors": {"cpu_s": 33, "selections": 1000}},
           "in_process_to_solver_cpu_s": 60, "outside_detector_cpu_s": 22}
    oracle = {"groups": {"dense": {"checks": {"strict_fixed_guard": {
        "cpu_ms": {"mean": 2}, "counts": {"lanes": 8, "total_returned": 10},
    }}}}}
    measured = trial.projection_cost(acq, oracle)
    assert measured["verify_cpu_s"] == 1.6
    assert measured["cold_callback_allowance_s"] == 8
    assert measured["remaining_for_all_reacquisition_and_prediction_cold_cpu_s"] == pytest.approx(1.4)
