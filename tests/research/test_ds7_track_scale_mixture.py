import copy
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
import ds7_fast_baseline_adapter as baseline
from ds7_track_scale_mixture import densities, evaluate


def fixture():
    t = np.linspace(-1, 1, 24)
    columns = np.array([t, t**2, np.sin(t * 4)]) * 40
    track = {
        "track_id": "example",
        "mask": np.arange(24) % 3 != 2,
        "y": 80 + 50 * t + 300 * np.sin(7 * t),
        "catalogue_size": 10,
    }

    def prediction(track, x):
        value = x @ columns
        return np.array([value, value + 60 * t]), np.array([True, True])

    return track, prediction


def test_normalized_densities_and_baseline_limit():
    for scale in (100, 1000):
        assert quad(lambda y, scale=scale: float(np.exp(densities(y, scale))), -np.inf, np.inf)[
            0
        ] == pytest.approx(1)
    track, predict = fixture()
    x = np.array([0.2, 0.3, 0.4])
    score, joint, _, _ = baseline.profile(track["y"][None, :] - predict(track, x)[0], track["mask"])
    from scipy.special import logsumexp

    result = evaluate([track], predict, x, scales=(100,), priors=(1,), held=True)
    assert result["training_log_score"] == pytest.approx(logsumexp(score) - np.log(10), abs=1e-10)
    assert result["held_log_score"] == pytest.approx(logsumexp(joint) - logsumexp(score), abs=1e-10)


def test_envelope_gradient_and_held_data_cannot_change_training_weights():
    track, predict = fixture()
    changed = copy.deepcopy(track)
    changed["y"][~changed["mask"]] += 10000
    x = np.array([0.2, 0.3, 0.4])
    result = evaluate([track], predict, x, gradient=True, held=True)
    other = evaluate([changed], predict, x, gradient=True, held=True)
    assert result["training_log_score"] == other["training_log_score"]
    assert result["gradient"] == other["gradient"]
    for key in ("scale_weights", "candidate_weights", "joint_weights", "offsets"):
        assert result["tracks"][0][key] == other["tracks"][0][key]
    assert result["held_log_score"] != other["held_log_score"]
    for i in range(3):
        step = np.eye(3)[i] * 1e-4
        numerical = (
            evaluate([track], predict, x + step)["training_log_score"]
            - evaluate([track], predict, x - step)["training_log_score"]
        ) / 2e-4
        assert result["gradient"][i] == pytest.approx(numerical, abs=1e-5)


def test_whole_track_scale_discriminates_clean_and_broad_noise():
    t = np.linspace(-1, 1, 40)

    def predict(track, x):
        return np.zeros((1, 40)), np.array([True])

    track = {
        "track_id": "a",
        "mask": np.arange(40) % 3 != 2,
        "catalogue_size": 1,
        "y": 30 + 10 * np.sin(t * 20),
    }
    clean = evaluate([track], predict, np.zeros(3), held=True)
    track["y"] = 30 + 1500 * np.sin(t * 20)
    broad = evaluate([track], predict, np.zeros(3), held=True)
    assert clean["tracks"][0]["scale_weights"][1] < 0.001
    assert broad["tracks"][0]["scale_weights"][1] > 0.999
    with pytest.raises(ValueError):
        evaluate([track], predict, np.zeros(3), priors=(0.9, 0.2))
