import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import coherent_pilot_frames
from tools.research.replay_adaptive_multiscale_phase_refined import frame_origin_times


def test_train_residual_can_be_frozen_for_held_symbol_coherence():
    offsets = np.arange(64) * 1e-6
    residual_hz = 2300.0
    exact = np.tile(np.exp(2j * np.pi * residual_hz * offsets), (8, 1))
    control = np.ones_like(exact)
    _, _, fitted, _ = coherent_pilot_frames(exact[:4], control[:4], offsets, 1e-6)
    held, _, applied, _ = coherent_pilot_frames(
        exact[4:], control[4:], offsets, 1e-6, forced_residual_hz=fitted
    )
    assert applied == fitted
    assert np.min(np.abs(held)) > 63.9


def test_coherent_frame_time_retains_shift_and_fractional_origin():
    times = frame_origin_times(np.array([100, 200]), -7, 0.25, 2_500_000)
    np.testing.assert_allclose(times, np.array([93.25, 193.25]) / 2_500_000)
