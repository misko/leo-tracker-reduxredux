import numpy as np

from tools.research.plot_adaptive_phase_300s import raw_training_offset


def test_raw_training_offset_recovers_rx1_minus_rx0_without_held_frames():
    """The raw cross-product is RX1 times conjugate(RX0), train-only.

    A deliberately destructive held-frame mutation must have no effect.  This
    detects both a sign reversal and accidental use of held frames in the
    receiver-offset estimate.
    """
    fs = 2_500_000.0
    expected_hz = -676_900.25
    starts = 4_096 + np.arange(12) * 3_333
    train = np.array([True, False, True, False, True, False] * 2)
    n = np.arange(50_000)
    carrier0_hz = 238_500.0
    iq = np.column_stack(
        (
            np.exp(2j * np.pi * carrier0_hz * n / fs),
            np.exp(2j * np.pi * (carrier0_hz + expected_hz) * n / fs),
        )
    )

    recovered, prominence = raw_training_offset(iq, starts, train, fs)
    assert abs(recovered - expected_hz) < 1.0
    assert prominence > 1e6

    held_iq = iq.copy()
    rng = np.random.default_rng(20260923)
    for start in starts[~train]:
        held_iq[start : start + 2048] = (
            rng.standard_normal((2048, 2)) + 1j * rng.standard_normal((2048, 2))
        )
    held_mutated, _ = raw_training_offset(held_iq, starts, train, fs)
    np.testing.assert_allclose(held_mutated, recovered, rtol=0.0, atol=1e-9)
