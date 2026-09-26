import importlib.util
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("high_bandwidth_phase_analysis", MODULE_PATH)
assert SPEC and SPEC.loader
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def test_high_rate_geometry_matches_original_window_time() -> None:
    samples, window, stride, starts = ANALYSIS.window_geometry(10_000_000)
    assert samples == 1_200_000
    assert window == 32_768
    assert stride == 16_384
    assert len(starts) == 71
    assert np.all(np.diff(starts) == stride)


def test_random_windows_are_disjoint() -> None:
    _, window, _, _ = ANALYSIS.window_geometry(10_000_000)
    stratum = round(0.020 * 10_000_000)
    offset = (stratum - 6 * window) // 2
    starts = np.asarray(
        [group * stratum + offset + index * window for group in range(6) for index in range(6)]
    )
    assert np.all(starts[1:] >= starts[:-1] + window)
    assert starts[0] >= 0
    assert starts[-1] + window <= 1_200_000


def test_circular_r() -> None:
    assert ANALYSIS.circular_r(np.zeros(4)) == 1.0
    assert ANALYSIS.circular_r(np.asarray([0, np.pi])) < 1e-12


def test_interval_is_exactly_eight_hours() -> None:
    assert ANALYSIS.STOP_NS - ANALYSIS.START_NS == 8 * 60 * 60 * 1_000_000_000


def test_decimation_geometry_and_common_phase() -> None:
    time = np.arange(40_000) / ANALYSIS.HIGH_RATE
    tone = np.exp(2j * np.pi * 100_000 * time).astype(np.complex64)
    iq = np.column_stack((tone, tone * np.exp(0.7j)))
    reduced = ANALYSIS.decimate_four(iq)
    assert reduced.shape == (10_000, 2)
    phase = np.angle(np.vdot(reduced[100:-100, 0], reduced[100:-100, 1]))
    np.testing.assert_allclose(phase, 0.7, atol=1e-5)
