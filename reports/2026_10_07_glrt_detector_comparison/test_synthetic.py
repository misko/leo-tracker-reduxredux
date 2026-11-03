"""Component-owned simulation checks; no hardware, QNAP, or PostgreSQL required."""

import numpy as np
from synthetic import CONFIG, cfo_error, draw_observations, pilot_geometry, wilson_interval


def test_control_noise_matches_shared_iq_template_gram():
    geometry = pilot_geometry()
    rng = np.random.default_rng(818)
    exact, control, _ = draw_observations(rng, 12000, "white", geometry)
    empirical = np.mean(control * np.conj(exact), axis=0)
    np.testing.assert_allclose(empirical, geometry["overlap"], atol=0.035)
    np.testing.assert_allclose(np.mean(np.abs(exact) ** 2, axis=0), 1, atol=0.035)
    np.testing.assert_allclose(np.mean(np.abs(control) ** 2, axis=0), 1, atol=0.035)


def test_actual_iq_projection_reproduces_joint_gaussian_covariance():
    geometry = pilot_geometry()
    rng = np.random.default_rng(812)
    iq = (rng.standard_normal((10000, 88)) + 1j * rng.standard_normal((10000, 88))) / np.sqrt(2)
    for symbol in (0, 17, 63):
        exact = iq @ np.conj(geometry["exact"][symbol])
        control = iq @ np.conj(geometry["control"][symbol])
        np.testing.assert_allclose(np.mean(control * np.conj(exact)),
                                   geometry["overlap"][symbol], atol=0.035)


def test_signal_control_leakage_uses_same_received_waveform():
    geometry = pilot_geometry()
    null_exact, null_control, _ = draw_observations(
        np.random.default_rng(902), 7, "white", geometry
    )
    exact, control, truth = draw_observations(np.random.default_rng(902), 7, "white", geometry, 0)
    signal = exact - null_exact
    np.testing.assert_allclose(control - null_control, geometry["overlap"] * signal)
    np.testing.assert_allclose(np.abs(signal), 1)
    assert np.all(truth >= CONFIG["true_cfo_uniform_hz"][0])
    assert np.all(truth <= CONFIG["true_cfo_uniform_hz"][1])


def test_cfo_error_respects_periodic_aliasing_and_interval_boundary():
    period = 1 / CONFIG["symbol_step_s"]
    np.testing.assert_allclose(
        cfo_error(np.array([period - 20, 100]), np.array([0, 140])), [20, 40]
    )
    low, high = wilson_interval(0, 5000)
    assert 0 <= low < 1e-10
    assert 0.0007 < high < 0.0008


def test_colored_noise_preserves_unit_variance_and_target_adjacent_covariance():
    exact, _, _ = draw_observations(
        np.random.default_rng(781), 8000, "correlated_ar", pilot_geometry()
    )
    covariance = np.mean(exact[:, 1:] * np.conj(exact[:, :-1]))
    np.testing.assert_allclose(covariance, CONFIG["ar_coefficient"], atol=0.025)
    np.testing.assert_allclose(np.mean(np.abs(exact) ** 2), 1, atol=0.025)


def test_pooled_trials_share_cfo_and_allow_independent_frame_phases():
    geometry = pilot_geometry()
    null_exact, null_control, _ = draw_observations(
        np.random.default_rng(408), 6, "white", geometry, frames=14
    )
    exact, control, truth = draw_observations(
        np.random.default_rng(408), 6, "white", geometry, 0, frames=14
    )
    assert exact.shape == (6, 14, 64)
    signal = exact - null_exact
    np.testing.assert_allclose(control - null_control, geometry["overlap"] * signal)
    np.testing.assert_allclose(np.abs(signal), 1)
    phase_increment = signal[:, :, 1:] * np.conj(signal[:, :, :-1])
    expected = np.exp(2j * np.pi * truth * CONFIG["symbol_step_s"])
    np.testing.assert_allclose(
        phase_increment, np.broadcast_to(expected[:, None, None], (6, 14, 63))
    )
    assert np.std(np.angle(signal[0, :, 0])) > 0.5
