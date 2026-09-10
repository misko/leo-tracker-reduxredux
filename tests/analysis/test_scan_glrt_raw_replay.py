"""Probe-support and default-window regression checks for the raw IQ study."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "scan_raw_replay", Path(__file__).parents[2] / "tools/replay_scan_glrt_hyperparameters.py"
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.mark.parametrize("fs", [2_500_000, 5_000_000])
def test_support_excludes_incomplete_last_frame(fs):
    epoch = int(fs * 0.00128)
    fractional = 0.25
    symbol_samples = fs * 4.4e-6
    expected = np.mean([epoch + round(frame * fs / 750) for frame in range(14)])
    expected += np.mean(np.arange(2, 66) * symbol_samples) + (symbol_samples - 1) / 2
    expected += fractional
    assert replay.support_center(fs, epoch, fractional, 20) == pytest.approx(expected)


def test_window_grid_contains_current_twenty_milliseconds():
    variants = replay.variants()
    baseline = next(v for v in variants if v["name"] == "fft_512")
    assert baseline == {"name": "fft_512", "nfft": 512, "ms": 20, "symbols": 64}
    assert {v["ms"] for v in variants} == {10, 20, 40, 80}
