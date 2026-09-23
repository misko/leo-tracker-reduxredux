import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import coherent_pilot_frames, fit_linear_phasor
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


def test_frame_origin_gauge_recovers_center_phase_not_symbol_centroid_gauge():
    """Symbol derotation leaves coherent phasors at the shifted frame origin.

    The phasors here are generated independently of the replay helper.  Each
    receiver has a non-zero within-frame residual and the two receiver-frame
    phases have a non-zero differential rate.  Thus this catches a timestamp
    that merely mirrors ``frame_origin_times`` while using the wrong gauge.
    """
    sample_rate_hz = 2_500_000.0
    starts = 145_000 + np.arange(10) * round(sample_rate_hz / 750.0)
    shift_samples = 37
    fractional_epoch_samples = 0.375
    origins_s = (starts + shift_samples + fractional_epoch_samples) / sample_rate_hz
    center_s = float(origins_s[5])
    symbol_offsets_s = (np.arange(2, 66) + 0.5) * 4.4e-6

    # Differential receiver phase at center and its inter-frame rotation.
    receiver_phase_at_center = (0.35, 1.15)
    receiver_frame_hz = (175.0, -175.0)
    receiver_within_frame_hz = (2_300.0, -1_900.0)
    exact_rows = []
    coherent_rows = []
    for phase0, frame_hz, within_hz in zip(
        receiver_phase_at_center, receiver_frame_hz, receiver_within_frame_hz, strict=True
    ):
        symbols = np.exp(
            1j
            * (
                phase0
                + 2 * np.pi * frame_hz * (origins_s[:, None] - center_s)
                + 2 * np.pi * within_hz * symbol_offsets_s[None, :]
            )
        )
        frames, _, fitted_within_hz, _ = coherent_pilot_frames(
            symbols, np.ones_like(symbols), symbol_offsets_s, 4.4e-6
        )
        assert abs(fitted_within_hz - within_hz) < 2.0
        exact_rows.append(symbols)
        coherent_rows.append(frames)

    product = coherent_rows[1] * np.conj(coherent_rows[0])
    weights = np.ones(len(product))
    _, origin_phase, _ = fit_linear_phasor(product, origins_s, weights, center_s)
    _, centroid_phase, _ = fit_linear_phasor(
        product, origins_s + np.mean(symbol_offsets_s), weights, center_s
    )
    expected = receiver_phase_at_center[1] - receiver_phase_at_center[0]
    origin_error = np.angle(np.exp(1j * (origin_phase - expected)))
    centroid_error = np.angle(np.exp(1j * (centroid_phase - expected)))
    assert abs(origin_error) < 1e-6
    assert abs(centroid_error) > np.radians(10.0)
