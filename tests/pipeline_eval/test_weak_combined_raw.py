"""Paired end-to-end timing and both calibration arms enter the weak-transfer gates."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from weak_combined_score import decision


@pytest.mark.parametrize(
    "duration,fitted,complete,timing_ok,position_ok",
    [(5., 1.25, True, True, True), (5.001, .5, True, False, True),
     (4., 1.251, True, True, False), (4., 1., False, True, False)],
)
def test_gates(duration, fitted, complete, timing_ok, position_ok):
    errors = {"stock": {"c0": 1., "fitted_c": 1.}, "candidate": {"c0": .5, "fitted_c": fitted}}
    result = decision(10., duration, errors, complete=complete)
    assert result["passes_one_recording_timing"] is timing_ok
    assert result["passes_position"] is position_ok


@pytest.mark.parametrize("value", [0., -1., float("inf"), float("nan")])
def test_invalid_clock(value):
    with pytest.raises(ValueError, match="durations"):
        decision(10., value, {}, complete=True)
