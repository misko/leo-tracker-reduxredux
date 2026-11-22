from importlib import import_module

import numpy as np
import pytest

trial = import_module("reports.ALGO08.single-core-2x.mirrored_revision_shape_trial")


def test_profiled_revision_score_matches_dense_gaussian():
    sigma = 4.2
    rng = np.random.default_rng(17)
    z = rng.normal(size=(11, 3))
    residual = rng.normal(size=(11, 4))
    remaining, coefficients = trial.fit_revision(z, sigma, residual)
    profiled = np.sum(remaining**2, axis=0) + sigma**2 * np.sum(coefficients**2, axis=0)
    covariance = sigma**2 * np.eye(len(z)) + z @ z.T
    reference = sigma**2 * np.sum(residual * np.linalg.solve(covariance, residual), axis=0)
    np.testing.assert_allclose(profiled, reference, rtol=2e-14, atol=1e-14)


def test_retained_information_charges_only_overlapping_directions():
    z = np.array([[3.0], [0.0]])
    assert trial.information(z, 1.0, np.array([1.0, 0.0])) == pytest.approx(0.1)
    assert trial.information(z, 1.0, np.array([0.0, 1.0])) == 1.0
    assert trial.information(z[:, :0], 1.0, np.ones(2)) == 1.0
    with pytest.raises(ValueError, match="entire face direction"):
        trial.information(z, 1.0, np.zeros(2))


def test_directional_revision_can_repair_the_face_sign_without_a_mean_change():
    template = np.column_stack((np.zeros(2), [1.0, 0.0]))
    z = np.array([[8.0], [4.0]])
    later = template - z
    ordinary = trial.score(template, later, z[:, :0], 0.2)
    revision = trial.score(template, later, z, 0.2)
    assert [row["preferred"] for row in ordinary.values()] == ["A", "A"]
    assert [row["preferred"] for row in revision.values()] == ["A", "B"]
    b = revision["later_B"]
    assert b["fitted_rms_hz"][1] < b["penalized_equivalent_rms_hz"][1]


def test_midpoint_alias_is_shared_only_when_both_faces_agree():
    period = trial.range_epoch_model.FOLD_HZ
    values = np.asarray([10.0 + period, period / 2])
    nominal = np.asarray([[8.0, 10.0, 12.0], [-1.0, 0.0, 1.0]])
    observed, disagreements = trial.lift_observed(values, nominal)
    assert disagreements == 1
    np.testing.assert_allclose(observed, [10.0, -period / 2])
    np.testing.assert_allclose(
        observed, nominal[:, 1] + trial.range_epoch_model.wrap(values - nominal[:, 1], period)
    )


def test_same_projection_checks_the_absorbed_calibration_for_every_comparison():
    intercept = np.ones((4, 1))
    templates = np.column_stack((np.zeros(4), [2.0, 0.0, 1.0, 0.0]))
    data = templates.copy()
    calibration = np.ones(4) * 300.0
    z = np.array([[5.0], [1.0], [0.0], [2.0]])
    all_inputs = np.column_stack((templates, data, calibration, z))
    result = trial.compare(intercept, all_inputs, 2, 2.0)
    assert result["nuisance_rank"] == 1
    assert 0 < result["retained_information"] < 1
    assert result["independent"]["later_A"]["preferred"] == "A"
    assert result["revision"]["later_B"]["preferred"] == "B"
    all_inputs[0, 4] *= 2
    with pytest.raises(ValueError, match="did not absorb"):
        trial.compare(intercept, all_inputs, 2, 2.0)
