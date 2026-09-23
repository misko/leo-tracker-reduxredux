import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("train_pointing_cone_run", PATH)
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)


def brute_profile(midpoint, endpoints, receiver_ids, weights, mapping, fractions, orientations):
    best = {fraction: None for fraction in fractions}
    for orientation in orientations:
        mount = RUN.axes(*orientation)[list(mapping)]
        angle = np.degrees(
            np.arccos(np.clip(np.sum(midpoint * mount[receiver_ids], axis=1), -1, 1))
        )
        for fraction in fractions:
            value = RUN.weighted_quantile(angle, weights, fraction)
            if best[fraction] is None or value < best[fraction][0]:
                endpoint_angle = np.degrees(
                    np.arccos(
                        np.clip(np.sum(endpoints * mount[receiver_ids, None, :], axis=2), -1, 1)
                    )
                )
                best[fraction] = (
                    value,
                    RUN.weighted_quantile(np.max(endpoint_angle, axis=1), weights, fraction),
                    tuple(orientation),
                )
    return best


def test_batched_quantiles_match_scalar_definition():
    values = np.array([[4.0, 1.0, 3.0, 2.0], [7.0, 9.0, 6.0, 8.0]])
    weights = np.array([1.0, 4.0, 2.0, 3.0])
    fractions = (0.5, 0.8, 0.95)
    actual = RUN.weighted_quantiles_batched(values, weights, fractions)
    expected = np.array(
        [[RUN.weighted_quantile(row, weights, f) for f in fractions] for row in values]
    )
    np.testing.assert_allclose(actual, expected)


def test_batched_axes_are_unit_and_twenty_degrees_apart():
    axes = RUN.axes_batched(np.array([[0, 0, 0], [3, 25, 70], [30, 355, 355]]))
    np.testing.assert_allclose(np.linalg.norm(axes, axis=2), 1.0, atol=1e-12)
    separation = np.degrees(np.arccos(np.sum(axes[:, 0] * axes[:, 1], axis=1)))
    np.testing.assert_allclose(separation, 20.0, atol=1e-10)


def test_batched_sweep_matches_brute_force_on_small_grid(monkeypatch):
    orientations = np.array(
        [[0, 0, 0], [0, 0, 90], [1, 0, 0], [1, 90, 90], [2, 180, 180]], dtype=np.int16
    )
    monkeypatch.setattr(RUN, "orientation_grid", lambda maximum_tilt=30: orientations)
    midpoint = np.array([[1, 0, 1], [0, 1, 1], [-1, 0, 1], [0, -1, 1]], dtype=float)
    midpoint /= np.linalg.norm(midpoint, axis=1)[:, None]
    endpoints = np.stack((midpoint, np.roll(midpoint, 1, axis=0)), axis=1)
    receiver_ids = np.array([0, 1, 0, 1])
    weights = np.array([1.0, 2.0, 3.0, 4.0])
    fractions = (0.5, 0.8, 0.95)
    for mapping in ((0, 1), (1, 0)):
        actual = RUN.profile(
            midpoint, endpoints, receiver_ids, weights, mapping, fractions, batch_size=2
        )["15"]
        expected = brute_profile(
            midpoint, endpoints, receiver_ids, weights, mapping, fractions, orientations
        )
        for fraction in fractions:
            item = actual[str(fraction)]
            midpoint_value, endpoint_value, orientation = expected[fraction]
            np.testing.assert_allclose(item["midpoint_cone_deg"], midpoint_value)
            np.testing.assert_allclose(item["endpoint_cone_deg"], endpoint_value)
            assert (item["tilt_deg"], item["tilt_azimuth_deg"], item["yaw_deg"]) == orientation


def test_mapping_and_endpoint_use_selected_fixed_orientation(monkeypatch):
    orientations = np.array([[0, 0, 0]], dtype=np.int16)
    monkeypatch.setattr(RUN, "orientation_grid", lambda maximum_tilt=30: orientations)
    mount = RUN.axes(0, 0, 0)
    midpoint = np.array([mount[0], mount[1]])
    endpoints = np.stack((midpoint, midpoint), axis=1)
    receiver_ids = np.array([0, 1])
    direct = RUN.profile(midpoint, endpoints, receiver_ids, np.ones(2), (0, 1), (0.95,))["0"][
        "0.95"
    ]
    swapped = RUN.profile(midpoint, endpoints, receiver_ids, np.ones(2), (1, 0), (0.95,))["0"][
        "0.95"
    ]
    assert direct["midpoint_cone_deg"] < 1e-6
    assert direct["endpoint_cone_deg"] < 1e-6
    assert swapped["midpoint_cone_deg"] > 19.9


def test_endpoint_sensitivity_uses_worst_endpoint_per_track(monkeypatch):
    orientations = np.array([[0, 0, 0]], dtype=np.int16)
    monkeypatch.setattr(RUN, "orientation_grid", lambda maximum_tilt=30: orientations)
    mount = RUN.axes(0, 0, 0)
    midpoint = np.array([mount[0], mount[0]])
    endpoints = np.array([[mount[0], -mount[0]], [mount[0], mount[0]]])
    result = RUN.profile(
        midpoint,
        endpoints,
        np.zeros(2, dtype=int),
        np.array([2.0, 1.0]),
        (0, 1),
        (0.5,),
    )["0"]["0.5"]
    np.testing.assert_allclose(result["endpoint_cone_deg"], 180.0, atol=1e-6)
