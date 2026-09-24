import math

import pytest

from tools.report_late_dual_rx_track_phase import (
    circular_standard_deviation_deg,
    residual_phase_change_deg,
)


def test_circular_standard_deviation_converts_resultant() -> None:
    assert circular_standard_deviation_deg(math.exp(-0.5)) == pytest.approx(180 / math.pi)


def test_residual_phase_change_unwraps_and_fits_held_rows() -> None:
    rows = [
        {"center_sample": 0, "residual_phase_rad": 3.0},
        {"center_sample": 1, "residual_phase_rad": -3.0},
        {"center_sample": 2, "residual_phase_rad": -2.7168146928204138},
    ]
    result = residual_phase_change_deg(rows, 1.0)
    assert result["held_span_s"] == 2.0
    assert result["linear_change_deg"] == pytest.approx(
        math.degrees((2 * math.pi - 2.7168146928204138) - 3.0), abs=1e-9
    )
    assert result["post_linear_rms_deg"] == pytest.approx(0.0, abs=1e-9)
