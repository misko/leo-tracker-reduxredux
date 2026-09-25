import importlib.util
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("dual_phase_analysis", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def test_correction_cycles_start_at_zero() -> None:
    assert ANALYSIS.correction_cycles(0.0, 650_000.0, 1_000.0) == 0.0


def test_correction_cycles_derivative_matches_frequency_model() -> None:
    center_hz = 650_000.0
    rate_hz_s = 1_200.0
    time_s = 0.043
    step_s = 1e-7
    derivative = (
        ANALYSIS.correction_cycles(time_s + step_s, center_hz, rate_hz_s)
        - ANALYSIS.correction_cycles(time_s - step_s, center_hz, rate_hz_s)
    ) / (2.0 * step_s)
    expected = center_hz + rate_hz_s * (time_s - 0.060)
    assert np.isclose(derivative, expected, atol=1e-3)


def test_circular_r_is_wrap_invariant() -> None:
    phase = np.asarray([-2.8, -0.2, 0.3, 2.7])
    shifted = phase + 8.0 * np.pi
    assert np.isclose(ANALYSIS.circular_r(phase), ANALYSIS.circular_r(shifted))


def test_centered_windows_are_complete_and_have_requested_stride() -> None:
    starts = ANALYSIS.centered_starts()
    assert starts[0] == 2048
    assert starts[-1] + ANALYSIS.FFT_SAMPLES <= ANALYSIS.DWELL_SAMPLES
    assert len(starts) == 71
    assert np.all(np.diff(starts) == ANALYSIS.STRIDE)
