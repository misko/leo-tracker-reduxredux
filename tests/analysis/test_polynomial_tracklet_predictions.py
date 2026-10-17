"""Independent predictive-density and fold-isolation checks."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.polynomial_tracklets import TrackConfig

SPEC = importlib.util.spec_from_file_location(
    "tracklet_predictions",
    Path(__file__).resolve().parents[2] / "tools/validate_polynomial_tracklet_predictions.py",
)
prediction = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prediction)


def test_circular_prediction_density_normalizes_and_preserves_alias_invariance():
    period, sigma = 1000.0, 80.0
    grid = (np.arange(20000) + 0.5) * period / 20000 - period / 2
    density = prediction.wrapped_normal(grid - 420, sigma, period)
    assert abs(density.mean() * period - 1) < 1e-10
    np.testing.assert_allclose(
        density, prediction.wrapped_normal(grid + 3 * period - 420, sigma, period), atol=1e-14
    )


def test_no_prediction_uses_uniform_background_and_never_extrapolates():
    config = TrackConfig()
    result = {
        "tracks": [
            {
                "pieces": [
                    {
                        "indices": [0, 1],
                        "reference_time_s": 0,
                        "time_scale_s": 1,
                        "coefficients_hz": [0],
                    }
                ]
            }
        ]
    }
    gain, distance, count = prediction.score_predictions(
        result, np.array([5.0, 10.0]), np.array([0.0, 7.0, 20.0]), np.zeros(3), config
    )
    np.testing.assert_array_equal(count, [0, 1, 0])
    np.testing.assert_array_equal(gain[[0, 2]], [0, 0])
    assert gain[1] > 0
    assert np.isinf(distance[[0, 2]]).all()


def test_discovery_never_sees_excluded_blocks_and_every_point_is_scored():
    rows = [
        {"receiver": 1, "channel": 1, "time_s": i + 0.1, "measured_cfo_hz": float(i)}
        for i in range(40)
    ]
    calls = []

    def fitter(t, y, config):
        present = set((t // 5).astype(int) % 4)
        assert len(present) == 3
        calls.append(present)
        return {"tracks": []}

    result = prediction.cross_validate(rows, TrackConfig(), fitter=fitter)
    assert len(calls) == 4
    assert result["observations"] == 40
    assert sum(f["excluded_points"] for f in result["folds"]) == 40
    assert result["mean_log_density_gain_over_uniform_nats"] == 0
    assert result["predictive_coverage_fraction"] == 0


def random_rows():
    return [
        {
            "observation_id": f"rx{rx}-{i:03}",
            "receiver": rx,
            "channel": 1,
            "time_s": i + 0.1,
            "measured_cfo_hz": float(i),
        }
        for rx in (1, 2)
        for i in range(41)
    ]


def test_random_folds_are_balanced_reproducible_and_independent_of_measurements():
    rows = random_rows()
    folds = prediction.make_folds(rows, split="random_points", seed=1701)
    for rx in (1, 2):
        counts = np.bincount(
            folds[[i for i, r in enumerate(rows) if r["receiver"] == rx]], minlength=4
        )
        assert counts.max() - counts.min() <= 1
    changed = [{**r, "measured_cfo_hz": -1e9} for r in rows]
    np.testing.assert_array_equal(
        folds, prediction.make_folds(changed, split="random_points", seed=1701)
    )
    permutation = np.random.default_rng(5).permutation(len(rows))
    reordered = prediction.make_folds([rows[i] for i in permutation], split="random_points")
    np.testing.assert_array_equal(folds, reordered[np.argsort(permutation)])
    assert np.any(folds != prediction.make_folds(rows, split="random_points", seed=1702))
    # This is a scattered point split, with many changes inside a 5-second block.
    assert len(set(folds[:5])) > 1


def test_random_crossfit_never_trains_on_held_points_and_scores_every_point_once():
    rows = [r for r in random_rows() if r["receiver"] == 1]
    assignment = prediction.make_folds(rows, split="random_points")
    calls = []

    def fitter(t, y, config):
        fold = len(calls)
        expected = {r["time_s"] for i, r in enumerate(rows) if assignment[i] != fold}
        assert set(t) == expected
        calls.append(t)
        return {"tracks": []}

    result = prediction.cross_validate(rows, TrackConfig(), fitter=fitter, split="random_points")
    assert len(calls) == 4
    assert sum(f["excluded_points"] for f in result["folds"]) == len(rows)
    assert result["split"]["mode"] == "random_points"
    assert result["split"]["seed"] == 1701
    assert result["predictive_coverage_fraction"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"folds": 1},
        {"folds": 2.5},
        {"split": "unknown"},
        {"split": "random_points", "seed": -1},
        {"block_s": 0},
    ],
)
def test_invalid_split_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        prediction.make_folds(random_rows(), **changes)
