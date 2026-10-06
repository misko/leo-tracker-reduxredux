from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.regional_position_association import RegionalAssociation
from leo.analysis.regional_position_bootstrap import PositionBootstrap
from leo.analysis.regional_position_calibration import ReceiverCorrection, RegionalCalibration
from leo.analysis.regional_position_fit import PositionFit
from leo.application import regional_position_runner as runner
from tests.analysis.test_regional_position_score import synthetic_inputs


class Checkpoints:
    def __init__(self, interrupt_after=None):
        self.values = {}
        self.interrupt_after = interrupt_after

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.values[key] = value
        if len(self.values) == self.interrupt_after:
            raise runner.RegionalSliceExpired("simulated worker interruption")


def fixture(monkeypatch):
    observations, bank, prior = synthetic_inputs()
    calls = {"bootstrap": [], "final": []}

    def fit(objective, start, **options):
        vector = np.asarray(start).copy()
        if options.get("rf_arm") == "zero-c":
            vector[6] = 0
        if not options.get("fixed_position"):
            calls["final"].append((objective, vector.copy(), options))
        return PositionFit(
            vector,
            float(np.sum(vector[:2] ** 2)),
            100.0,
            10.0,
            0.0,
            True,
            False,
            "stationary",
            1,
            0.01,
        )

    def bootstrap(obs, orbit_bank, region, point, tracks, **options):
        calls["bootstrap"].append(tuple(point))
        return PositionBootstrap((0, 1), np.array([*point, 0, 0, 0, 0, 30, 0.1, 0.1]), ())

    def calibrate(obs, orbit_bank, region, seed, **options):
        fitted = fit(None, seed.vector, fixed_position=True)
        return RegionalCalibration(
            (0, 1),
            fitted,
            fitted,
            ReceiverCorrection(np.arange(3), np.ones((2, 3)), np.zeros(len(obs.window_ids)), ()),
            np.zeros(len(obs.window_ids)),
        )

    def associate(obs, orbit_bank, region, calibrated, **options):
        return RegionalAssociation(
            (0, 1), calibrated.postfit.vector, {"final": {"satellites": [], "assigned": 20}}, 2
        )

    monkeypatch.setattr(runner, "fit_position", fit)
    monkeypatch.setattr(runner, "bootstrap_position", bootstrap)
    monkeypatch.setattr(runner, "calibrate_position", calibrate)
    monkeypatch.setattr(runner, "associate_calibration", associate)
    return observations, bank, prior, calls


def test_resume_reuses_completed_points_and_matches_all_four_final_arms(monkeypatch):
    obs, bank, prior, calls = fixture(monkeypatch)
    checkpoints = Checkpoints(interrupt_after=3)
    config = runner.RegionalRunConfiguration(point_budget=16, basins_per_method=1)
    with pytest.raises(runner.RegionalSliceExpired):
        runner.run_regional_position(obs, bank, prior, (), checkpoints, configuration=config)
    checkpoints.interrupt_after = None
    result = runner.run_regional_position(obs, bank, prior, (), checkpoints, configuration=config)
    assert len(calls["bootstrap"]) == len(set(calls["bootstrap"])) == 16
    assert len(result["finals"]) == 8
    assert {row["method"] for row in result["finals"]} == {"T1AT", "V16"}
    assert {row["arm"] for row in result["finals"]} == {"fitted-c", "zero-c"}
    assert all(row["calibration_penalty"] == pytest.approx(3 / 2500) for row in result["finals"])
    for objective, start, options in calls["final"]:
        assert objective.observations is obs
        assert options["maximum_seconds"] == config.final_fit_seconds
        assert options["maximum_iterations"] == config.final_iterations
        assert options["local_radius_km"] == pytest.approx(100 / np.sqrt(2))
        if options["rf_arm"] == "zero-c":
            assert start[6] == 0
    before = len(calls["final"])
    assert (
        runner.run_regional_position(obs, bank, prior, (), checkpoints, configuration=config)
        == result
    )
    assert len(calls["final"]) == before


def test_changed_configuration_does_not_reuse_old_stage_receipts(monkeypatch):
    obs, bank, prior, calls = fixture(monkeypatch)
    checkpoints = Checkpoints()
    config = runner.RegionalRunConfiguration(point_budget=16, basins_per_method=1)
    runner.run_regional_position(obs, bank, prior, (), checkpoints, configuration=config)
    runner.run_regional_position(
        obs, bank, prior, (), checkpoints, configuration=replace(config, final_iterations=301)
    )
    assert len(calls["bootstrap"]) == 32


def test_slice_yields_before_starting_work_it_cannot_budget(monkeypatch):
    obs, bank, prior, calls = fixture(monkeypatch)
    with pytest.raises(runner.RegionalSliceExpired):
        runner.run_regional_position(obs, bank, prior, (), Checkpoints(), maximum_seconds=0.001)
    assert not calls["bootstrap"]
