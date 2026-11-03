"""A partition cannot smooth, relabel or silently drop scientific observations."""

import importlib
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("evaluate_shared_satellite_phase")
    obj = tool.Experiment.__new__(tool.Experiment)
    times = np.arange(-20.0, 321)
    site = geodetic_to_ecef_km(37.5, -122.0, 0)
    east, _, up = ecef_to_enu_matrix(37.5, -122.0)
    p = site[None, :] + 550 * up[None, :] + (times * 7)[:, None] * east[None, :]
    obj.sky = dict(
        time_s=times,
        position_km=p[None, :, :],
        velocity_km_s=np.broadcast_to(7 * east, p.shape)[None, :, :],
    )
    t = np.arange(0.0, 30)
    obj.tracks = [
        dict(
            key="curve",
            receiver=1,
            channel=1,
            rf_hz=11.5e9,
            times=t,
            values=100 * t * t,
            observation_ids=[str(i) for i in range(30)],
        )
    ]
    return obj


def core(track):
    return dict(
        track,
        times=track["times"][:-1],
        values=track["values"][:-1],
        observation_ids=track["observation_ids"][:-1],
    )


def test_partition_binds_all_original_points_and_rebuilds_curved_geometry(experiment):
    original = experiment.tracks[0]
    receipt = experiment.set_observation_partition([core(original)], ["29"])
    assert receipt["original_points"] == 30
    assert receipt["curve_points"] == receipt["calibration_points"] == 29
    assert receipt["background_points"] == 1 and receipt["points_dropped"] == 0
    assert experiment.curved_keys == frozenset({"curve"})
    assert experiment.background_observation_ids == frozenset({"29"})
    np.testing.assert_array_equal(experiment.times, np.arange(29.0))
    assert len(original["times"]) == 30


@pytest.mark.parametrize("change", ["missing", "duplicate", "smoothed", "relabelled", "timestamp"])
def test_invalid_partitions_are_rejected_atomically(experiment, change):
    original = experiment.tracks[0]
    changed = core(original)
    bg = ["29"]
    if change == "missing":
        bg = []
    elif change == "duplicate":
        bg = ["29", "29"]
    elif change == "smoothed":
        changed["values"] = changed["values"].copy() + 1
    elif change == "relabelled":
        changed["receiver"] = 2
    else:
        changed["times"] = changed["times"].copy() + 0.01
    with pytest.raises(ValueError):
        experiment.set_observation_partition([changed], bg)
    assert experiment.tracks[0] is original


def test_linear_remnant_cannot_establish_calibration(experiment):
    original = experiment.tracks[0]
    fragment = dict(
        original,
        times=original["times"][:4],
        values=original["values"][:4],
        observation_ids=original["observation_ids"][:4],
    )
    with pytest.raises(ValueError, match="no measured-curved"):
        experiment.set_observation_partition([fragment], original["observation_ids"][4:])


def test_consolidation_consumes_supplied_core_ids_without_reloading_original_points(experiment):
    tool = importlib.import_module("consolidate_shared_phase_matches")
    bank = dict(experiment.sky, norad=np.array([123]))
    t = experiment.tracks[0]["times"]
    frequency, _ = phase_frequency_grid(bank, t, 37.5, -122)
    first = dict(experiment.tracks[0], values=frequency[0] + 500)
    trimmed = core(first)
    second = dict(first, key="second", observation_ids=[f"other:{i}" for i in range(len(t))])
    fit = dict(
        beta=[500.0, 0, 0, 0, 0, 0, 0, 0], phases_s=[0], latitude_deg=37.5, longitude_deg=-122.0
    )
    association = dict(
        compatible_points=59,
        rows=[
            dict(component=track["key"], candidate_norad=123, compatible=True)
            for track in (trimmed, second)
        ],
    )
    result = tool.consolidate_tracks(
        [trimmed, second], bank, fit, association, check_joined_residual=True
    )
    assert result["points"] == 59 and result["points_dropped"] == 0
    assert result["output_tracks"] == 1
