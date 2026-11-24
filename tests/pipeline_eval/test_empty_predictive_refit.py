from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from empty_predictive_refit import CurvedCapture, compatible, instrument, same
from leo.analysis.localization_v3 import history_policy, history_position, predictive_linear


def original_fits():
    scan = SimpleNamespace(search_region=SimpleNamespace(latlon=tuple))
    keep = np.ones(2, dtype=bool)
    model = {"multiplier": 2.0, "nu": 3.0}
    inputs = ({"nodes": [1, 2]}, keep, np.ones(2), np.zeros(1), *model.values())

    def make(scan, node, keep, arm, reference, weights, means, multiplier, nu):
        coeff = np.array([3.0, -1.0])
        return SimpleNamespace(
            reference=reference, labels=[0], phase_sigma=np.array([4.0]),
            state=lambda x: {"phases": np.array([20.0 if x[0] < 2 else 5.0])},
            residual=lambda x: np.array([2.0, 3.0]),
            calculate=lambda x: dict(coefficient=coeff, latent_coefficient=coeff,
                                     coefficient_prior_precision=np.ones(2),
                                     conditional_residual_hz=np.array([2.0, 3.0]),
                                     normalization_constant=2.0, negative_twice_elbo=4.0,
                                     noise_precision=np.ones(2), precision_iterations=1,
                                     final_log_precision_change=0.001),
        )

    def fit(p, point, *, iterations):
        return {"parameters": point + 1, "iterations": iterations}

    def gates(p, point):
        return {"tracks": [{"compatible": True}], "at": point.copy()}

    shared = dict(make_problem=make, fit=fit, retained_metrics=gates)
    with patch.multiple(history_position, **shared), patch.multiple(predictive_linear, **shared):
        node, keep, weights, means, multiplier, nu = inputs
        capture = CurvedCapture(scan, inputs)
        capture.record = instrument(history_position.refit)(
            scan, node, keep, "c0", weights, means, multiplier, nu, rounds=2, observe=capture,
        )
        stock = predictive_linear.refit(scan, node, keep, weights, means, model, "c0", [], rounds=2)
    return scan, inputs, capture, stock


def test_clipped_history_and_last_used_reference_reproduced_exactly():
    scan, inputs, capture, stock = original_fits()
    result = capture.readout(scan, inputs, [])
    assert same(result, stock)
    assert np.array_equal(result["phase_reference"], [15.0])
    assert np.array_equal(capture.record["phase_reference"], [5.0])
    assert result["history"][0]["phase_change_s"] == 15.0
    assert capture.record["history"][0]["phase_change_s"] == 20.0
    result["gates"]["at"][0] = -1.0
    assert capture.record["gates"]["at"][0] == 2.0


def test_predictive_entries_or_changed_working_state_decline():
    scan, inputs, capture, stock = original_fits()
    assert capture.readout(scan, inputs, [{"points": 1}]) is None
    assert capture.readout(object(), inputs, []) is None
    inputs[1][0] = False
    assert capture.readout(scan, inputs, []) is None


def test_active_providers_and_mapping_must_match():
    assert compatible(history_policy, history_position, predictive_linear, None)
    assert not compatible(history_policy, history_position, predictive_linear, map)
    with patch.object(predictive_linear, "fit", new=object()):
        assert not compatible(history_policy, history_position, predictive_linear, None)
