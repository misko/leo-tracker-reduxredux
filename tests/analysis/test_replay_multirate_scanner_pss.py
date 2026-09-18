from dataclasses import dataclass

from tools.replay_multirate_scanner_pss import select, timing_metrics


@dataclass(frozen=True)
class Window:
    frame_index: int
    frame_phase_samples: float


def test_selection_is_order_independent():
    digest = "sha256:" + "a" * 64
    assert select([2, 4, 8, 16], digest) == select([16, 8, 4, 2], digest)


def test_alternating_timing_metric_recovers_linear_phase():
    rate = 10_000_000
    windows = [Window(i, (100e-9 + i * 2e-9) * rate) for i in range(12)]
    result = timing_metrics(windows, rate)
    assert result["timing_windows"] == 12
    assert result["linear_fit_rms_ns"] < 1e-9
    assert result["alternating_validation_rms_ns"] < 1e-9


def test_timing_metric_refuses_short_mode():
    result = timing_metrics([Window(i, 0) for i in range(7)], 10_000_000)
    assert result["timing_windows"] == 7
    assert result["alternating_validation_rms_ns"] is None
