"""Guard physical units, delay sign and antialiasing in the paired rate experiment."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from review_scan_sample_rates import choose, delay_signal, half_rate, timing_difference


@pytest.mark.parametrize("fs", [2500000, 5000000])
@pytest.mark.parametrize("delay_ns", [-243.7, 173.1])
def test_off_grid_delay_has_exact_tone_phase_and_preserves_energy(fs, delay_ns):
    n = np.arange(4096)
    frequency = 307 * fs / len(n)
    values = np.exp(2j * np.pi * frequency * n / fs)
    shifted = delay_signal(values, fs, delay_ns * 1e-9)
    expected = values * np.exp(-2j * np.pi * frequency * delay_ns * 1e-9)
    assert shifted == pytest.approx(expected, abs=2e-12)
    assert np.vdot(shifted, shifted).real == pytest.approx(np.vdot(values, values).real)


def test_decimation_preserves_in_band_tone_and_rejects_out_of_band_alias():
    fs = 5000000
    n = np.arange(20000)
    low = np.exp(2j * np.pi * 100000 * n / fs)
    high = np.exp(2j * np.pi * 2000000 * n / fs)
    assert half_rate(low)[100:-100] == pytest.approx(low[::2][100:-100], abs=1e-4)
    assert np.sqrt(np.mean(abs(half_rate(high)[100:-100]) ** 2)) < 1e-4


def test_frame_wrap_and_physical_association_gate_do_not_use_cfo():
    assert timing_difference(100e-9, 1 / 750 - 100e-9) == pytest.approx(200e-9)
    candidate = {
        "rank": 0,
        "integer_epoch_s": 700e-9,
        "cfo_hz": 90000,
        "margin": 0.1,
        "exact_score": 0.5,
    }
    assert choose([candidate], 0) == candidate
    assert choose([{**candidate, "integer_epoch_s": 900e-9}], 0) is None
    assert choose([{**candidate, "cfo_hz": -70000}], 0)["cfo_hz"] == -70000
