from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from test_regional_position_score import synthetic_inputs

from leo.analysis.regional_position_association import associate_calibration
from leo.analysis.regional_position_score import predict_orbits
from leo.contracts.regional_position import PositionObservations


def test_full_bank_regional_discovery_preserves_windows_and_selected_timing():
    _, bank, prior = synthetic_inputs()
    n = 120
    rx = np.arange(n) // 60
    owners = np.arange(n) // 20 % 3
    times = np.tile(np.arange(20) * 0.5 + 0.37, 6)
    observations = PositionObservations(
        tuple(f"w{i}" for i in range(n)),
        times,
        np.zeros(n),
        np.full(n, 11.2e9),
        rx,
        np.ones(n),
        np.full(n, 0.2),
    )
    shifts = [0.4, -0.6, 0.8]
    predicted = predict_orbits(bank, observations, prior, [3, -5], shifts)[0]
    baseline = np.where(rx == 0, 100.0, -100.0)
    observations = replace(observations, measured_hz=predicted[np.arange(n), owners] + baseline)
    calibration = SimpleNamespace(
        postfit=SimpleNamespace(vector=np.array([3, -5, 0, 0, 0, 0, 0])),
        receiver_baseline_hz=baseline,
    )
    result = associate_calibration(observations, bank, prior, calibration, maximum_seconds=10)
    assert result.selection["final"]["denominator"] == n
    assert result.selection["final"]["assigned"] == n
    assert len(result.selected_indices) == 3
    assert result.initial_vector[:2].tolist() == [3, -5]
    assert len({a["window_id"] for a in result.selection["final"]["assignments"]}) == n
