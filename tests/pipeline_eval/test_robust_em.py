import numpy as np
import pytest

from tools.pipeline_eval.variants import robust_em as receiver


def _planted(*, duplicate=False, c_hz_per_ghz=0):
    rng = np.random.default_rng(5119)
    xy = np.array([3.25, -4.0])
    biases = [5300, -9300, 2100, 1200]
    drifts = [75, -130, 110, -25]
    phases = [0.1, 0.35, -0.07, 0.2, -0.15]
    arcs = []
    centers = (13, 19, 28, 41, 48, 61, 70, 79, 93, 89, 101, 112, 149)
    t0 = np.linspace(-1, 1, 37)
    for i, center in enumerate(centers):
        t = center + 6.0 * t0
        lane, orbit = i % 4, i % 5
        rf = 11.4e9 + (i % 3) * 130e6
        dt = (t - 80) / 100
        tracker = receiver.Track(t, np.zeros_like(t), rf, lane, True, dt, np.eye(len(t)) / 150)
        grad = rng.normal(0, 140, (3, 2))
        spatial = np.column_stack((np.ones_like(t0), t0, t0**2)) @ grad
        phase = 180 + 1450 * np.sin((0.4 + i / 20) * np.pi * t0)
        unwrapped = (
            spatial @ xy
            + phase * phases[orbit]
            + biases[lane]
            + dt * drifts[lane]
            + receiver.PERIOD * (i % 3 - 1)
            + (rf / 1e9 - 11.5) * c_hz_per_ghz
        )
        fake = unwrapped + 3500 + 7000 * t0**2
        arcs.append(
            receiver.Arc(
                tracker,
                np.array([orbit, 5 + orbit]),
                np.array([unwrapped, unwrapped if duplicate else fake]),
                np.array([spatial, spatial]),
                np.array([phase, phase]),
                np.array([0.1, 0.1 if duplicate else 49]),
                np.zeros(2),
            )
        )
    return arcs, xy


def test_planted_position_uses_shared_radio_and_orbit_with_track_wide_aliases():
    arcs, xy = _planted()
    fits, metrics, reason = receiver.solve(arcs, 10, 12.5)
    assert reason is None
    assert metrics["orbit_count"] == 5
    assert metrics["associated_observations"] == sum(len(arc.track.t) for arc in arcs)
    assert metrics["held_orbits"] == 3
    for arm in receiver.ARMS:
        np.testing.assert_allclose(fits[arm].state.xy, xy, atol=0.1)
        assert fits[arm].rms_hz < 10


def test_duplicate_orbits_withhold_a_position():
    arcs, _ = _planted(duplicate=True)
    _, metrics, reason = receiver.solve(arcs, 10, 12.5)
    assert reason == "ambiguous_orbit_assignments"
    assert metrics["separated_orbits"] < 3


def test_fitted_rf_term_reduces_frequency_residual_on_the_same_support():
    arcs, xy = _planted(c_hz_per_ghz=2000)
    fits, metrics, reason = receiver.solve(arcs, 10, 12.5)
    assert reason == "weak_held_track_support"
    assert metrics["associated_observations"] > 0
    fitted = fits["fitted_c"]
    assert fitted.state.c_hz_per_ghz == pytest.approx(2000, abs=50)
    assert fitted.rms_hz < fits["c0"].rms_hz
    np.testing.assert_allclose(fitted.state.xy, xy, atol=0.1)


def test_empty_and_duplicate_support_are_accounted_for():
    result = receiver.infer(dict(duration_s=20, tracks=[]), dict(center=[0, 0], id="test"), "")
    assert result["status"] == "withheld" and result["reason"] == "insufficient_track_inventory"
    assert all(v["latlon"] is None for v in result["arms"].values())
    track = dict(times=[1, 2, 3, 4], values=[5, 7, 8, 10], channel=1, receiver=1, rf_hz=11e9)
    duplicate = dict(track, values=[v + receiver.PERIOD for v in track["values"]])
    tracks, metrics = receiver.observations(dict(duration_s=20, tracks=[track, duplicate]))
    assert len(tracks) == 1
    assert metrics["input_points"] == 8 and metrics["duplicates_removed"] == 4
    assert int(metrics["unique_fit_points"]) == 4
    with pytest.raises(ValueError, match="invalid anonymous track"):
        receiver.observations(dict(duration_s=20, tracks=[dict(track, times=[1, 2, 1, 4])]))
