from types import SimpleNamespace

import numpy as np
import pytest
from position_profile_grid import (
    BEARINGS,
    EARTH_RADIUS_KM,
    RADII_M,
    geodesic_position,
    position_grid,
    run_profile,
    select_best_attempt,
)


def _angular_distance(left, right):
    left_latitude, left_longitude = np.deg2rad(left)
    right_latitude, right_longitude = np.deg2rad(right)
    cosine = (
        np.sin(left_latitude) * np.sin(right_latitude)
        + np.cos(left_latitude)
        * np.cos(right_latitude)
        * np.cos(right_longitude - left_longitude)
    )
    return np.arccos(np.clip(cosine, -1.0, 1.0))


def test_geodesic_positions_have_requested_physical_radius():
    latitude, longitude = 42.0, -71.0
    for _label, bearing in BEARINGS:
        for radius in RADII_M:
            position = geodesic_position(latitude, longitude, bearing, radius)
            from joint_inputs import _coordinates

            destination = _coordinates(position)
            distance_m = 1000.0 * EARTH_RADIUS_KM * _angular_distance(
                [latitude, longitude],
                destination,
            )
            assert distance_m == pytest.approx(radius, abs=1.0e-3)


def test_position_grid_has_eight_labelled_rays_and_24_unique_points():
    protocol = {
        "bearings_deg_clockwise_from_north": [value for _label, value in BEARINGS],
        "radii_m": list(RADII_M),
    }
    grid = position_grid(
        {"latitude_deg": 42.0, "longitude_deg": -71.0},
        protocol,
    )
    assert list(grid) == [label for label, _value in BEARINGS]
    assert sum(map(len, grid.values())) == 24
    labels = [point["label"] for points in grid.values() for point in points]
    assert len(set(labels)) == 24


def test_best_attempt_uses_lowest_finite_objective_even_if_incomplete():
    attempts = [
        {"objective": 4.0, "success": True},
        {"objective": 3.0, "success": False},
        {"objective": None, "success": False},
    ]
    index, best = select_best_attempt(attempts)
    assert index == 1
    assert best is attempts[1]
    assert select_best_attempt([{"objective": None}]) == (None, None)


class FakeLikelihood:
    def __init__(self):
        self.detection_probability = None
        self.last_result = None


class FakeBase:
    def __init__(self, objective, data):
        self.objective = objective
        self.data = data
        self.calls = 0
        self.last = None
        self.deadline = float("inf")

    def check_deadline(self):
        return None

    def state(self, vector):
        return {"ephemeris_valid": True, "parameters": np.asarray(vector).copy()}

    def penalty(self, vector):
        gradient = np.zeros_like(vector)
        gradient[-1] = vector[-1]
        return 0.5 * vector[-1] ** 2, gradient


class FakeObjective:
    def __init__(self, data, initial, _satellites, _separate, _budget):
        self.size = len(initial)
        self.initial = np.r_[np.asarray(initial, dtype=float), 0.0]
        self.bounds = [(-200.0, 200.0), (-200.0, 200.0)] + [(-10.0, 10.0)] * (
            len(self.initial) - 2
        )
        self.scale = np.ones(len(self.initial))
        self.likelihood = FakeLikelihood()
        self.base = FakeBase(self, data)
        self.best = None

    def evaluate(self, vector):
        self.base.calls += 1
        target = np.arange(len(vector), dtype=float) / 10.0
        residual = np.asarray(vector) - target
        data_nll = 0.5 * float(residual @ residual) - 0.5 * vector[self.size - 1] ** 2
        prior, prior_gradient = self.base.penalty(vector[: self.size])
        value = data_nll + prior
        gradient = residual.copy()
        gradient[: self.size] += prior_gradient
        self.likelihood.last_result = {
            "total_log_likelihood": -data_nll,
            "group_values": np.array([10, 20]),
            "log_likelihood": np.array([-data_nll / 2, -data_nll / 2]),
            "satellite_support": np.array([1.5]),
        }
        self.base.last = {"objective": value}
        if self.best is None or value < self.best["objective"]:
            self.best = {"objective": value, "vector": np.asarray(vector).copy()}
        return value, gradient

    def curvature(self, _vector):
        return np.eye(len(self.initial))


def test_public_run_profile_fixes_position_and_supports_probability_override():
    result = run_profile(
        SimpleNamespace(times=np.array([1.0, 2.0]), group=np.array([10, 20])),
        np.zeros(7),
        [0],
        [0.25],
        [2.0, -3.0],
        probability_override=0.2,
        budget_s=1.0,
        objective_factory=FakeObjective,
    )
    np.testing.assert_array_equal(result["vector"][:2], [2.0, -3.0])
    assert result["detection_probability"] == 0.2
    assert result["total_nll"] == pytest.approx(
        result["data_nll"] + result["nuisance_prior_nll"]
    )
    assert result["group_log_likelihood"].sum() == pytest.approx(-result["data_nll"])
    np.testing.assert_array_equal(result["group_time_s"], [1.0, 2.0])
    assert result["parameters"].shape == (7,)


def test_run_profile_rejects_unbounded_stage_and_bad_probability():
    with pytest.raises(ValueError, match=r"\(0,8"):
        run_profile(SimpleNamespace(), np.zeros(7), [0], [0.0], [0.0, 0.0], budget_s=8.1)
    with pytest.raises(ValueError, match="probability_override"):
        run_profile(
            SimpleNamespace(),
            np.zeros(7),
            [0],
            [0.0],
            [0.0, 0.0],
            probability_override=0.0,
        )
