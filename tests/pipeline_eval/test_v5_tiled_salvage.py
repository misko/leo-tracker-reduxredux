from collections import Counter

import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from tools.pipeline_eval.variants import v5_tiled_salvage as tiled


@pytest.mark.parametrize("masked", (False, True))
def test_tiled_phase_costs_preserve_roster_sort_and_horizon_gates(masked):
    rng = np.random.default_rng(762)
    f, elevation, d = [rng.normal(0, s, (41, 55)) for s in (1000, 7, 100)]
    y = f[2] + 2 * PERIOD + rng.normal(0, 200, 55)
    noise = rng.uniform(80, 240, 55)
    elevation[16] = -1
    f[32], elevation[32], d[32] = f[0], elevation[0], d[0]
    q = 0.984
    phases = np.linspace(-10, 10, 81)
    mask = np.arange(len(y)) % 3 == 1 if masked else None
    prediction = q * (f[:, None] + d[:, None] * phases[None, :, None])
    dense_elevation = elevation
    clipped, std = y, noise
    if masked:
        prediction = prediction[:, :, mask]
        dense_elevation = elevation[:, mask]
        clipped, std = y[mask], noise[mask]
    terms = profile(clipped, prediction.reshape(-1, len(clipped)), np.diag(1 / std))
    costs = terms["cost"].reshape(len(f), -1) + phases[None, :] ** 2 / 9
    costs[dense_elevation.max(axis=1) < 0] = np.inf
    expected = costs.min(axis=1)

    shape = []

    def measured(y, frequency, w):
        shape.append(frequency.shape)
        return profile(y, frequency, w)

    counts = Counter()
    result = tiled.coarse_scores(measured, y, noise, f, elevation, d, q, phases, mask, counts)
    np.testing.assert_allclose(result, expected, rtol=1e-13, atol=1e-10)
    np.testing.assert_array_equal(np.argsort(result), np.argsort(expected))
    assert np.isinf(result[16])
    assert result[0] == result[32]
    assert counts["tiles"] == 3 and counts["coarse_windows"] == 1
    assert max(n for n, _ in shape) == 16 * 81
    assert counts["max_prediction_bytes"] == 16 * 81 * len(clipped) * 8
