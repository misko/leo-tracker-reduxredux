import numpy as np

from tools.research.evaluate_longarc_phase_advances import fit_and_score, group_weights


def synthetic():
    calibration, response = [], []
    for visit in range(8):
        for times, target in (([-0.05, 0.01, 0.05], calibration), ([-0.03, -0.01, 0.03], response)):
            times = np.asarray(times)
            coefficient = 2 * np.pi * times / 750
            true = coefficient * (1500 + 300 * visit)
            target.append(
                {
                    "measured": true + coefficient * 100 + 0.17 * visit,
                    "prediction": np.stack([np.zeros(3), true]),
                    "rate_phase": coefficient,
                    "weights": np.full(3, 1 / 3),
                }
            )
    return calibration, response


def test_motion_shape_survives_local_intercept_and_common_rate():
    calibration, response = synthetic()
    training = np.asarray([True, False] * 4)
    models = fit_and_score(calibration, response, training, np.arange(-5000, 5001, 25))
    assert models[1]["rate_hz_s"] == 100
    assert models[1]["training_score"] > models[0]["training_score"]
    assert models[1]["held_score"] > models[0]["held_score"]
    assert models[1]["held_rms_rad"] < 1e-12


def test_response_never_changes_training_selection():
    calibration, response = synthetic()
    training = np.asarray([True, False] * 4)
    grid = np.arange(-5000, 5001, 25)
    before = fit_and_score(calibration, response, training, grid)
    for row in response:
        row["measured"] += np.asarray([0.8, -0.4, 1.1])
    after = fit_and_score(calibration, response, training, grid)
    for left, right in zip(before, after, strict=True):
        assert left["rate_hz_s"] == right["rate_hz_s"]
        assert left["training_score"] == right["training_score"]
    assert before[1]["held_score"] != after[1]["held_score"]


def test_pair_population_is_weighted_by_group():
    weights = group_weights([{"group": 0}, {"group": 0}, {"group": 5}])
    np.testing.assert_allclose(weights, [0.25, 0.25, 0.5])
