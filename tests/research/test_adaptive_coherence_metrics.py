import numpy as np

from tools.research.adaptive_coherence_metrics import (
    common_raw_offset,
    common_training_starts,
    pair_metrics,
    source_window,
)


def test_source_rate_is_train_only_under_held_phase_mutation():
    """A held phase change cannot alter the fitted source product rate."""
    times = np.arange(90) / 750.0
    train = np.array([(index * 17) % 29 < 14 for index in range(len(times))])
    expected_rate_hz = 143.0
    c0 = np.ones(len(times), dtype=np.complex128)
    c1 = np.exp(2j * np.pi * expected_rate_hz * (times - 0.06))
    clean = source_window(c0, c1, times, train, np.ones(len(times), bool), 0.06)
    mutated = c1.copy()
    mutated[~train] *= np.exp(1j * np.linspace(-2.7, 2.9, (~train).sum()))
    held_mutated = source_window(c0, mutated, times, train, np.ones(len(times), bool), 0.06)
    assert clean["failure"] is None and held_mutated["failure"] is None
    assert abs(clean["rate_hz"] - expected_rate_hz) < 0.1
    np.testing.assert_allclose(held_mutated["rate_hz"], clean["rate_hz"], atol=1e-10, rtol=0)
    assert held_mutated["weighted_R"] < clean["weighted_R"] - 0.2


def test_common_nonlinear_receiver_phase_cancels_in_dd_and_wrong_time_loses_resultant():
    """DD cancellation is tested with a shared nonlinear nuisance, not a flat fixture."""
    times = np.arange(90) / 750.0
    train = np.array([(index * 7) % 19 < 9 for index in range(len(times))])
    common = 2.2 * np.sin(2 * np.pi * 71.0 * times) + 1.1 * np.sin(2 * np.pi * 187.0 * times)
    left_phase = common + 0.41
    right_phase = common - 1.17
    left = {
        "times": times,
        "train": train,
        "product": np.exp(1j * left_phase),
        "weights": np.ones(len(times)),
        "metrics": {"pilot_supported_both_rx": True},
    }
    right = {
        "times": times,
        "train": train,
        "product": np.exp(1j * right_phase),
        "weights": np.ones(len(times)),
        "metrics": {"pilot_supported_both_rx": True},
    }
    result = pair_metrics(left, right)
    expected = right_phase[0] - left_phase[0]
    assert result["weighted_R"] > 0.999999
    assert abs(np.angle(np.exp(1j * (result["phase_rad"] - expected)))) < 1e-10
    assert result["wrong_time_control"]["weighted_R"] < 0.5
    assert result["screened_DD"]


def test_common_raw_offset_uses_only_windows_inside_every_anchor_training_frames():
    fs = 2_500_000.0
    frame_length = 2_200
    starts = np.array([0, 2_500, 5_000])
    specs = [
        (starts, np.array([True, False, True])),
        (starts, np.array([True, True, False])),
    ]
    windows = common_training_starts(specs, sample_count=7_500, frame_length=frame_length)
    assert len(windows) >= 3
    for window_start in windows:
        for frame_starts, train in specs:
            assert any(
                start + 8 <= window_start and window_start + 512 <= start + frame_length - 8
                for start in frame_starts[train]
            )
            assert not any(
                start + 8 <= window_start and window_start + 512 <= start + frame_length - 8
                for start in frame_starts[~train]
            )

    expected_offset_hz = -676_812.5
    index = np.arange(7_500)
    iq = np.column_stack(
        (
            np.exp(2j * np.pi * 261_000.0 * index / fs),
            np.exp(2j * np.pi * (261_000.0 + expected_offset_hz) * index / fs),
        )
    )
    recovered = common_raw_offset(iq, windows, fs)
    assert abs(recovered - expected_offset_hz) < 5.0
