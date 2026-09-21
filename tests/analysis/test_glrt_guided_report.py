from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from report_glrt_guided_broadband_phase import bootstrap_frequency  # noqa: E402


def test_frame_bootstrap_frequency_recovers_offset_and_detects_frame_variation():
    times = np.arange(64) * 4.4e-6
    fixed = SimpleNamespace(
        values=np.tile(np.exp(2j * np.pi * 1234 * times), (16, 1)), symbol_step_s=4.4e-6
    )
    result = bootstrap_frequency(fixed, 100000)
    assert result["frequency_hz"] == pytest.approx(101234, abs=15)
    varied = SimpleNamespace(
        values=np.exp(2j * np.pi * (1234 + np.linspace(-1000, 1000, 16))[:, None] * times),
        symbol_step_s=4.4e-6,
    )
    uncertainty = bootstrap_frequency(varied, 100000)
    assert uncertainty["sigma_hz"] > 10 * result["sigma_hz"]
    assert uncertainty == bootstrap_frequency(varied, 100000)


def test_bootstrap_refuses_too_few_independent_frames():
    with pytest.raises(ValueError, match="four"):
        bootstrap_frequency(SimpleNamespace(values=np.ones((3, 64))), 0)
