import sys
from pathlib import Path

import numpy as np
from smooth_joint import SmoothJointObjective

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter57"))
from test_elevation import fixture  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective, predict_orbits  # noqa: E402
from leo.contracts.regional_position import PositionScore  # noqa: E402


def model_fixture():
    bank, obs, prior, point, shifts = fixture()
    obs.times_s = np.array([3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    obs.receiver = np.array([0, 1, 0, 1, 0, 1])
    obs.rf_hz = np.linspace(10.8e9, 11.2e9, 6)
    obs.rf_center_hz, obs.time_center_s = 11e9, 5.5
    obs.measured_hz = predict_orbits(bank, obs, prior, point, shifts)[0][:, 2] + 40
    score = PositionScore("V16", 150, 1.2, 0.3, 3, 1)
    base = Hard60Objective(obs, bank, prior, score)
    nodes = np.linspace(0, 20, 5)
    model = SmoothJointObjective(base, nodes, np.zeros((2, 5)), 2)
    vector = np.r_[point, 12.0, 0.2, -8.0, -0.1, 15.0, 0.05, np.linspace(-0.1, 0.1, 5)]
    clock = np.linspace(-3, 3, len(model.initial_clock))
    return model, vector, clock


def test_all_joint_parameters_against_finite_differences():
    model, vector, clock = model_fixture()
    _, gradient, clock_gradient, _ = model.evaluate_joint(vector, clock)
    for values, expected, kind in ((vector, gradient, "vector"), (clock, clock_gradient, "clock")):
        for index in range(len(values)):
            step = 0.001 if kind == "clock" or index < 7 else 0.0001
            original = values[index]
            values[index] = original + step
            plus = model.evaluate_joint(vector, clock)[0]
            values[index] = original - step
            minus = model.evaluate_joint(vector, clock)[0]
            values[index] = original
            np.testing.assert_allclose(
                (plus - minus) / (2 * step),
                expected[index],
                rtol=2e-5,
                atol=2e-7,
                err_msg=f"{kind}:{index}",
            )


def test_prior_and_frequency_reporting_contract():
    model, vector, clock = model_fixture()
    value, _, _, terms = model.evaluate_joint(vector, clock)
    relative = model.basis @ vector[8:]
    penalty = 0.5 * (vector[7] / model.score.common_sigma_s) ** 2
    penalty += 0.5 * np.sum((relative / model.score.relative_sigma_s) ** 2)
    penalty += 0.5 * clock @ model.precision @ clock
    np.testing.assert_allclose(value - terms.nll, penalty, atol=1e-12)
    np.testing.assert_allclose(terms.responsibilities.sum(axis=1) + terms.clutter_probability, 1)
    assert terms.residual_hz.shape == (6, 6)
    assert np.isfinite(terms.prediction_gradient).all()
