"""All original points are scored; linear tracks cannot establish calibration."""

import importlib
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km


def test_tight_drift_bounds_apply_even_when_no_update_is_accepted(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("evaluate_shared_satellite_phase")

    def objective(stats, beta, phase, sigma, *, drift_sigma_hz_s):
        assert drift_sigma_hz_s == 0.5
        return 0.0, None, {"test": True}

    monkeypatch.setattr(tool, "penalized_score", objective)
    beta = np.array([100.0, 200.0, 300.0, 400.0, 750.0, -750.0, 600.0, -600.0])
    original = beta.copy()
    for bound in (0.0, 1.0):
        fit = tool.improve(
            {},
            beta,
            np.zeros(1),
            np.ones(1),
            np.ones(1),
            gates=(),
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=bound,
        )
        np.testing.assert_allclose(fit[1][4:8], [150 * bound, -150 * bound] * 2)
        np.testing.assert_array_equal(beta, original)


@pytest.mark.parametrize("sigma,bound", [(0, 1), (np.nan, 1), (0.5, -1), (0.5, np.inf)])
def test_invalid_drift_policy_rejected_before_loading_data(monkeypatch, sigma, bound):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("evaluate_shared_satellite_phase")
    with pytest.raises(ValueError, match="drift"):
        tool.Experiment(
            None,
            None,
            fitted_c=False,
            phase_enabled=True,
            drift_sigma_hz_s=sigma,
            drift_bound_hz_s=bound,
        )


def test_linear_association_needs_curved_hardware_support_and_shared_phase(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("evaluate_shared_satellite_phase")
    latitude, longitude = 37.5, -122.0
    site = geodetic_to_ecef_km(latitude, longitude, 0)
    east, _, up = ecef_to_enu_matrix(latitude, longitude)
    t = np.arange(-20.0, 321)
    p = site[None, :] + 550 * up[None, :] + (t * 7)[:, None] * east[None, :]
    sky = dict(
        time_s=t,
        position_km=p[None, :, :],
        velocity_km_s=np.broadcast_to(7 * east, p.shape)[None, :, :],
        norad=np.array([123]),
    )
    experiment = tool.Experiment.__new__(tool.Experiment)
    experiment.sky, experiment.phase_enabled = sky, True
    experiment.tracks = []
    for key, rx, sample in (
        ("curve", 1, np.arange(20.0, 121)),
        ("linear-supported", 1, np.arange(0.0, 11)),
        ("linear-unsupported", 2, np.arange(0.0, 11)),
    ):
        frequency, _ = phase_frequency_grid(sky, sample, latitude, longitude, phase_seconds=0.2)
        offset = 500 if rx == 1 else 1000
        experiment.tracks.append(
            dict(
                key=key,
                receiver=rx,
                channel=1,
                rf_hz=11.5e9,
                times=sample,
                values=frequency[0] + offset,
            )
        )
    fit = dict(
        latitude_deg=latitude,
        longitude_deg=longitude,
        phases_s=[0.2],
        beta=[500.0, 0, 1000.0, 0, 0, 0, 0, 0],
    )
    result = experiment.associate(fit)
    rows = {r["component"]: r for r in result["rows"]}
    assert result["points"] == sum(len(t["times"]) for t in experiment.tracks)
    assert rows["curve"]["active_curvature"] and rows["curve"]["compatible"]
    assert not rows["linear-supported"]["active_curvature"]
    assert rows["linear-supported"]["compatible"]
    assert rows["linear-unsupported"]["frequency_compatible_before_calibration_support"]
    assert not rows["linear-unsupported"]["compatible"]
    assert {row["phase_s"] for row in result["rows"]} == {0.2}
