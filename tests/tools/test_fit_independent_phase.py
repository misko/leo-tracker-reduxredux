import numpy as np

from tools.research import fit_independent_phase as fit
from tools.research.fit_independent_phase import PRIORS, affine_score, predict_model, regional_grid


def test_affine_profile_recovers_candidate_shape():
    time = np.arange(6.0)
    predicted = np.vstack([time**2, 2 * time])
    observed = time**2 + 4 - 0.3 * time
    rms, coefficient, _ = affine_score(observed, predicted, time)
    assert rms[0] < 1e-10
    assert rms[1] > 1
    assert np.allclose(coefficient[0], [3.25, -0.3])


def test_regional_grid_contains_centres_and_respects_disks():
    _points, metadata = regional_grid()
    for name, (_lat, _lon, radius) in PRIORS.items():
        rows = [row for row in metadata if row["prior"] == name]
        assert any(row["east_km"] == row["north_km"] == 0 for row in rows)
        assert all(np.hypot(row["east_km"], row["north_km"]) <= radius for row in rows)


def test_predict_model_empty_times_needs_no_orbit_payload():
    model = {"model_type": "exact_nominal_sgp4"}
    assert predict_model(model, np.asarray([]), {}).shape == (0,)


def test_wrong_time_requires_dwell_anchor():
    model = {"model_type": "exact_nominal_sgp4", "wrong_time": True}
    with np.testing.assert_raises_regex(ValueError, "dwell observation time"):
        predict_model(model, np.asarray([1.0]), {"wrong_time_mirror_sum_s": 2.0})


def test_exact_wrong_time_preserves_forward_frame_offsets(monkeypatch):
    seen = {}

    monkeypatch.setattr(fit, "parse_element_sets", lambda _text: object())

    def propagate(_catalogue, _indices, _start, times, _taus):
        seen["times"] = times.copy()
        position = np.zeros((1, 1, len(times), 3))
        velocity = np.zeros_like(position)
        return position, velocity, np.asarray([0])

    monkeypatch.setattr(fit, "propagate_candidate_states", propagate)
    monkeypatch.setattr(fit, "doppler_hz", lambda _site, _p, _v: np.asarray([5.0, 6.0]))
    model = {
        "model_type": "exact_nominal_sgp4",
        "wrong_time": True,
        "tle_lines": ["name", "line1", "line2"],
        "receiver_ecef_km": [1, 2, 3],
        "offset_hz": 2.0,
        "drift_hz_s": 0.0,
        "time_centre_s": 0.0,
    }
    predicted = predict_model(
        model,
        np.asarray([10.01, 10.02]),
        {"wrong_time_mirror_sum_s": 30.0, "start_utc_ns": 0},
        visit_time_s=10.0,
    )
    assert np.allclose(seen["times"], [20.01, 20.02])
    assert np.allclose(predicted, [7.0, 8.0])
