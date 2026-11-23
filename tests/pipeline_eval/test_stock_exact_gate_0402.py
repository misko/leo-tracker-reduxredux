from collections import Counter
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from exact_noise_gate_0402 import parity
from stock_exact_gate_0402 import GateWork, gate_binding
from leo.analysis.localization_v3 import feasible
from leo.analysis.research import retained_track_likelihood as likelihood


@pytest.mark.parametrize("bias", [300., 1000.])
@pytest.mark.parametrize("layout", ["C", "F"])
def test_white_profile_retains_all_original_diagnostics(layout, bias):
    times = np.cumsum(np.linspace(0.1, 2.3, 109))
    stock, volume = likelihood.whitening(times)
    rng = np.random.default_rng(408)
    observed = rng.normal(0, 90, len(times))
    predicted = np.array(rng.normal(0, 100, (2, len(times))), order=layout)
    predicted[0] += 0.5 * likelihood.PERIOD
    counts = Counter()
    gate = GateWork(feasible, likelihood, counts)
    cached, _ = gate.whitening(times)
    for value in (predicted, predicted[0], predicted[:, ::-1]):
        parity(gate.profile(observed, value, cached, volume, bias_sigma=bias),
               likelihood.profile(observed, value, stock, volume, bias_sigma=bias))
    assert gate.whitening(times.copy())[0] is cached
    assert counts["white_preparations"] == 1
    assert counts["profile_preparations"] == 1
    assert counts["profile_calls"] == 3


def test_time_changes_and_correlated_profile_cannot_reuse_wrong_inputs():
    counts = Counter()
    gate = GateWork(feasible, likelihood, counts)
    times = np.arange(12, dtype=float)
    residual = np.linspace(-700., 700., len(times))[None, :]
    for t in (times, times**2):
        parity(gate.screen(residual, t), feasible.batch_noise_screen(residual, t))
    assert counts["screen_preparations"] == 2
    matrix, volume = gate.whitening(times, correlated_sigma_hz=30.)
    observed = residual[0]
    parity(gate.profile(observed, observed, matrix, volume), likelihood.profile(observed, observed, matrix, volume))
    assert counts["white_stock"] == counts["profile_stock"] == 1


def test_binding_enables_only_the_original_optimizer_callback_and_restores():
    times = np.arange(12, dtype=float)
    residual = np.linspace(-700., 700., len(times))[None, :]
    port = SimpleNamespace(batch_noise_screen=feasible.batch_noise_screen, whitening=feasible.whitening, profile=feasible.profile)
    stock_noise = port.batch_noise_screen

    def fit():
        assert port.batch_noise_screen is not stock_noise
        parity(port.batch_noise_screen(residual, times), stock_noise(residual, times))
        return {"evaluations": 1}

    def constrained():
        assert port.batch_noise_screen is stock_noise
        result = port.feasible_fit()
        assert port.batch_noise_screen is stock_noise
        return result

    cavity = SimpleNamespace(constrained=constrained)
    port.feasible_fit = fit
    counts = Counter()
    with gate_binding(port, cavity, likelihood, counts):
        assert cavity.constrained() == {"evaluations": 1}
    assert cavity.constrained is constrained
    assert port.feasible_fit is fit
    assert port.batch_noise_screen is stock_noise
    assert counts["phase_fits"] == counts["visits"] == counts["screen_calls"] == 1
