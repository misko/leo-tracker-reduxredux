from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.presentation import localization_v3_orbits as orbits


def fixture(monkeypatch):
    def frequency(bank, times, labels, phases, latitude, longitude):
        assert latitude == 10.0 and longitude == 20.0
        return np.full(len(times), phases[0] * 10.0), np.ones(len(times))

    monkeypatch.setattr(orbits, "paired_phase_frequency", frequency)
    monkeypatch.setattr(orbits, "projected_receiver_basis", lambda t: None)
    monkeypatch.setattr(
        orbits, "receiver_design", lambda t, *args, **kwargs: np.tile([1.0, 2.0], (len(t), 1))
    )
    p = SimpleNamespace(
        scan=SimpleNamespace(
            search_region=SearchRegion((10.0, 20.0)), norads=np.array([123]), tracks=[]
        ),
        hardware=np.zeros((1, 1)),
        smooth=np.zeros((1, 1)),
        state=lambda x: dict(phases=np.array([2.3])),
        labels=[0],
        supported=[],
        sky=dict(
            time_s=np.array([0.0, 300.0]),
            position_km=np.zeros((1, 2, 3)),
            velocity_km_s=np.zeros((1, 2, 3)),
        ),
        reference=np.array([2.0]),
        fitted_c=True,
    )
    observations = [
        dict(
            observation_id="a",
            receiver=1,
            channel=1,
            time_s=1.0,
            measured_cfo_hz=100.0,
            actual_rf_hz=11.5e9,
        ),
        dict(
            observation_id="b",
            receiver=2,
            channel=8,
            time_s=2.0,
            measured_cfo_hz=101.0,
            actual_rf_hz=12.0e9,
        ),
    ]
    return (
        p,
        np.array([0.0, 0.0]),
        dict(coefficient=np.array([3.0, 4.0])),
        observations,
        {"a": 123},
        [],
        [],
    )


def test_orbits_keep_all_lanes_and_apply_channel_rf_scaling(monkeypatch):
    lanes = orbits.calibrated_lanes(*fixture(monkeypatch))
    assert len(lanes) == 16 and (lanes[0].receiver, lanes[0].channel) == ("RX1", "CH1")
    assert (lanes[-1].receiver, lanes[-1].channel) == ("RX2", "CH8")
    assert lanes[0].peaks[0].frequency_hz == 89.0
    assert lanes[-1].peaks[0].frequency_hz == 90.0
    assert lanes[0].peaks[0].satellite_id == "123" and lanes[-1].peaks[0].satellite_id is None
    assert np.allclose(lanes[0].curves[0].frequency_hz, 23.0, rtol=0, atol=1e-12)
    assert np.allclose(lanes[-1].curves[0].frequency_hz, 24.0, rtol=0, atol=1e-12)
    assert len(lanes[0].curves[0].time_s) == 1201
    assert lanes[1].peaks == ()


def test_missing_owned_satellite_cannot_be_hidden_from_orbit_plot(monkeypatch):
    values = fixture(monkeypatch)
    values[4]["b"] = 999
    with pytest.raises(ValueError, match="missing a published satellite"):
        orbits.calibrated_lanes(*values)


def test_mixed_rf_frames_in_one_lane_are_rejected(monkeypatch):
    values = fixture(monkeypatch)
    values[3].append(dict(values[3][0], actual_rf_hz=12.0e9, observation_id="c"))
    with pytest.raises(ValueError, match="One RF frame"):
        orbits.calibrated_lanes(*values)
