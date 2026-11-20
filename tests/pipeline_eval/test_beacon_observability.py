from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.measured_transfer import leave_out_scales, shared_epochs
from tools.pipeline_eval.variants import beacon_observability as model


def test_clock_and_arc_projection_agrees_with_explicit_joint_least_squares():
    arc = np.array([0, 1, 2, 0, 2, 1, 2, 3, 3])
    time = np.array([0, 0, 0, 1, 1, 2, 2, 3, 4])
    hz = np.array([2.0, 6, 7, -2, 4, -4, 3, 1, 10])
    nuisance = np.column_stack((np.eye(4)[arc], np.eye(5)[time]))
    control = hz - nuisance @ np.linalg.lstsq(nuisance, hz, rcond=None)[0]
    method = model.contrast(arc, time)

    assert method.rank == 2
    np.testing.assert_allclose(method.project(hz), control, atol=1e-12, rtol=0)
    arbitrary_oscillator = np.array([100000, -70, 40, 0, -50])[time]
    per_tone = np.array([4, 250, -100, 8])[arc]
    np.testing.assert_allclose(method.project(hz + per_tone + arbitrary_oscillator + 77.0),
                               control, atol=1e-10, rtol=0)


def test_single_source_epochs_and_empty_capture_have_zero_information():
    arcs = np.array([0, 0, 1, 1, 2])
    seconds = np.arange(5.0)
    method = model.contrast(arcs, seconds)
    assert method.rank == 0
    np.testing.assert_equal(method.project(np.ones(5)), np.zeros(5))
    packet = dict(time_s=[], frequency_hz=[], arc_index=[], arc_labels=[], duration_s=900,
                  anchor_utc_ns=100, cutoff_utc_ns=90, catalog_timestamp_ns=80)
    result = model.solve(packet, "unused", [37.0, -122.0])
    assert result["status"] == "withheld"
    assert result["metrics"]["held_rank"] == 0
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    assert result["arms"]["c0"]["forced_latlon"] is None


def test_half_second_picker_requires_exact_overlap_and_uses_richer_epoch():
    arcs = [(np.array([0.1, 0.25, 0.7, 1.0]), np.array([1, 2, 3, 4])),
            (np.array([0.1, 0.25, 0.700001]), np.array([5, 6, 7])),
            (np.array([0.25, 1.0]), np.array([8, 9]))]
    assert shared_epochs(arcs) == {
        "time_s": [0.25, 1.0, 0.25, 0.25, 1.0],
        "arc_index": [0, 0, 1, 2, 2], "frequency_hz": [2, 4, 6, 8, 9],
    }


def test_evaluation_site_never_calibrates_its_own_noise_scale():
    assert leave_out_scales({"a": 99999, "b": 80, "c": None, "d": 100}, "a") == 90
    assert leave_out_scales({"a": 99999, "b": 0}, "a") == model.BIN_SIGMA_HZ
    assert leave_out_scales({"a": 99999}, "a") is None


def test_planted_geometry_survives_unknown_clock_and_recovers_on_held_epochs(monkeypatch):
    center = [37.0, -122.0]
    latitude, longitude = center
    tile = SimpleNamespace(ecef_center_km=model.geodetic_to_ecef_km(latitude, longitude, 0.0),
                           enu_frame=model.ecef_to_enu_matrix(latitude, longitude))
    seconds = np.arange(1.0, 30.0)
    arcs = np.tile(np.arange(3), len(seconds))
    times = np.repeat(seconds, 3)
    rng = np.random.default_rng(420)
    positions = tile.ecef_center_km + 700 * tile.enu_frame[2] + rng.normal(0, 30, (len(arcs), 3))
    velocities = rng.normal(0, 1, (len(arcs), 3))
    chosen = np.array([[5.0, -2.5]])
    prediction, _, _ = model._predict(chosen, tile, positions, velocities)
    y = prediction[0] + 3000 * np.sin(times) + np.array([100000.0, -8.0, 14.0])[arcs]
    observation = dict(time_s=times, arc_index=arcs, frequency_hz=y,
                       arc_labels=["alpha", "beta", "gamma"], duration_s=30.0,
                       anchor_utc_ns=100, cutoff_utc_ns=90, catalog_timestamp_ns=80)
    monkeypatch.setattr(model, "_state_rows", lambda *_: (positions, velocities, [1, 2, 3]))
    control = model.solve(observation, "geometry fixture", center)
    assert control["metrics"]["fit_east_north_km"] == chosen[0].tolist()
    assert control["metrics"]["held_rf_rms_hz"] < 1e-9
    assert control["arms"]["c0"] == control["arms"]["fitted_c"]
    with pytest.raises(ValueError, match="causal archive"):
        model.solve(dict(observation, catalog_timestamp_ns=101), "unused", center)
