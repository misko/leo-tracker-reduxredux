import numpy as np

from leo.analysis.gaussian_sum_location import FilterState, GaussianComponent
from physics import PhysicsConfig
from run import independent_tracks, location_components, support_failures


def _track(name, start, end, ids, n=3):
    return {"track_id": name, "support_start_utc_ns": start, "support_end_utc_ns": end,
            "physical_observation_ids": ids, "measured_hz": [0.] * n}


def test_track_selection_is_chronological_and_rejects_duplicate_physical_evidence():
    evidence = {"tracks": [
        _track("later", 0, 20, ["shared", "b", "c"]),
        _track("first", 0, 10, ["shared", "d", "e"]),
        _track("short", 0, 5, ["x"], n=1),
    ]}
    retained, excluded = independent_tracks(evidence)
    assert [row["track_id"] for row in retained] == ["first"]
    assert {row["track_id"]: row["reason"] for row in excluded} == {
        "short": "too_short", "later": "same_receiver_source_overlap"}


def test_support_gate_uses_five_sigma_covariance_and_height():
    config = PhysicsConfig(support_radius_km=250., height_support_km=1.)
    safe = GaussianComponent(1., np.zeros(6), np.diag([20.**2, 20.**2, .1**2, 1., 1., 1.]))
    assert support_failures(FilterState((safe,)), config) == []
    wide = GaussianComponent(1., np.zeros(6), np.diag([51.**2, 1., .1**2, 1., 1., 1.]))
    assert "position_support_boundary" in support_failures(FilterState((wide,)), config)
    high = GaussianComponent(1., np.array([0., 0., .7, 0., 0., 0.]),
                             np.diag([1., 1., .1**2, 1., 1., 1.]))
    assert "height_support_boundary" in support_failures(FilterState((high,)), config)


def test_receipt_components_exclude_satellite_states_but_preserve_location_nuisance_block():
    component = GaussianComponent(1., np.arange(9.), np.eye(9), ("sat",))
    encoded = location_components(FilterState((component,)))[0]
    assert encoded["mean"] == list(np.arange(6.))
    assert np.asarray(encoded["covariance"]).shape == (6, 6)
    assert encoded["identity_history"] == ["sat"]
