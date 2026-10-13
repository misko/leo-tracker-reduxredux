import pytest

from leo.analysis.wrapped_glrt_likelihood import circular
from tools.check_glrt_doppler_frequency_convention import injection


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_actual_subcarrier_injection_tracks_pilot_rf_not_channel_carrier_rf(edge):
    base = injection(edge, 0)
    for speed in (3000, -3000):
        row = injection(edge, speed)
        measured = circular(row["score"]["tracking_cfo_hz"] - base["score"]["tracking_cfo_hz"])
        assert abs(circular(measured - row["expected_doppler_hz"])) < 25
        carrier_prediction = -speed / 299792458 * row["carrier_hz"]
        assert abs(circular(measured - carrier_prediction)) > 1000
        assert row["score"]["exact_score"] > 0.99
        assert row["effective_pilot_rf_hz"] == row["nominal_pilot_rf_hz"] - 117187.5
