import numpy as np
import pytest
from evaluate_glrt_information import position_error_km, summarize_width
from joint_inputs import _coordinates


def test_error_uses_geographic_reference_not_optimizer_origin():
    position = np.array([-87., -80.])
    latitude, longitude = _coordinates(position)
    reference = {"latitude_deg": latitude, "longitude_deg": longitude}
    assert position_error_km(position, reference) == pytest.approx(0.)
    assert .99 < position_error_km(position + [1., 0.], reference) < 1.01


def test_summary_keeps_failed_fit_and_does_not_use_loss_as_error():
    latitude, longitude = _coordinates(np.array([0., 0.]))
    record = {"session": "example", "sigma_hz": 50., "fit": {
        "parameters": [0., 0.], "success": False, "status": "time_limit",
        "projected_gradient_inf_norm": 1., "objective": 500.,
        "rf_coefficient_hz_per_ghz": [-700.],
    }}
    row = summarize_width(record, {"latitude_deg": latitude, "longitude_deg": longitude})
    assert row["error_km"] == pytest.approx(0.)
    assert row["success"] is False
    assert row["status"] == "time_limit"
    assert row["sigma_hz"] == 50.
