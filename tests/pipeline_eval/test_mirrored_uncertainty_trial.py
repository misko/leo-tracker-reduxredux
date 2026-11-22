from importlib import import_module

import numpy as np
import pytest


trial = import_module("reports.ALGO08.single-core-2x.mirrored_uncertainty_trial")


@pytest.mark.parametrize(("centre", "state"), (
    ((.7, 0.), "inside"), ((.8, 0.), "unresolved"),
    ((1.2, 0.), "unresolved"), ((1.3, 0.), "exterior"),
))
def test_ellipse_containment_and_intersection(centre, state):
    covariance = np.eye(2) * .25**2 / trial.JOINT_95
    assert trial.overlap(centre, covariance, 1.)[0] == state


def test_ellipse_correlation_changes_corner_overlap_at_equal_face_projections():
    centre = (1.35, 1.35)
    aligned = np.array([[.04, .035], [.035, .04]])
    orthogonal = np.array([[.04, -.035], [-.035, .04]])
    assert trial.overlap(centre, aligned, 1.)[0] == "unresolved"
    assert trial.overlap(centre, orthogonal, 1.)[0] == "exterior"


def test_profile_probes_match_known_quadratic_and_remove_baseline_gradient():
    hessian = np.array([[4., 1.], [1., 3.]])
    covariance = 2 * np.linalg.inv(hessian)

    def loss(point):
        delta = point - np.array([.4, -.5])
        return .5 * delta @ hessian @ delta

    for row in trial.curvature(loss, np.array([.7, -.2])).values():
        assert np.linalg.norm(row["gradient"]) > 0
        np.testing.assert_allclose(row["covariance_km2"], covariance)
        for result in row["profile"]:
            axis = result["axis"]
            assert result["displacement_km"][axis] == pytest.approx(trial.DISPLACEMENT_KM)
            assert result["average_delta"] == pytest.approx(trial.DISPLACEMENT_KM**2 / covariance[axis, axis])


@pytest.mark.parametrize("loss", (lambda point: point[0]**2 - point[1]**2, lambda _: float("inf")))
def test_invalid_curvature_produces_no_covariance(loss):
    result = trial.curvature(loss, np.zeros(2))
    assert all("covariance_km2" not in row for row in result.values())
