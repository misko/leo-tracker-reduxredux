import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("waveform_summary_test", Path(__file__).with_name("assess_measurements.py"))
assess = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assess)


def test_constant_correction_has_no_shape_change():
    summary = assess.shape_summary([100., 103., 107.], [250., 250., 250.])
    assert summary["median_correction_hz"] == 250.
    assert summary["centered_rms_hz"] == 0.
    assert summary["diagnostic_linear_slope_hz_s"] == 0.


def test_shape_diagnostic_separates_offset_and_slope():
    summary = assess.shape_summary([100., 102., 105.], [20., 26., 35.])
    assert summary["median_correction_hz"] == 26.
    assert summary["diagnostic_linear_slope_hz_s"] == pytest.approx(3.)
    assert summary["centered_rms_hz"] > 0.
    assert assess.shape_summary([], []) is None
