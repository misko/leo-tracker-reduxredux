from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.regional_position_association import RegionalAssociation
from leo.analysis.regional_position_bootstrap import PositionBootstrap
from leo.analysis.regional_position_calibration import ReceiverCorrection
from leo.analysis.regional_position_fit import PositionFit
from leo.application import hard60_runner as runner
from tests.analysis.test_regional_position_score import synthetic_inputs
from tests.application.test_regional_position_runner import Checkpoints


def test_single_method_resumes_and_applies_identical_policy_to_both_arms(monkeypatch):
    obs, bank, prior = synthetic_inputs()
    calls, seeds = [], []

    def bootstrap(observations, orbit_bank, region, point, tracks, **options):
        seeds.append(tuple(point))
        return PositionBootstrap((0, 1, 2), np.r_[point, np.zeros(8)], ())

    def fit(objective, start, **options):
        vector = np.array(start, float)
        if options.get("rf_arm") == "zero-c":
            vector[6] = 0
        calls.append((objective, vector.copy(), options))
        return PositionFit(
            vector,
            float(vector[:2] @ vector[:2]),
            100.0,
            10.0,
            0.0,
            True,
            False,
            "stationary",
            1,
            0.01,
        )

    monkeypatch.setattr(runner, "bootstrap_position", bootstrap)
    monkeypatch.setattr(runner, "fit_position", fit)
    monkeypatch.setattr(
        runner,
        "receiver_correction",
        lambda *a: ReceiverCorrection(
            np.arange(3), np.ones((2, 3)), np.zeros(len(obs.window_ids)), ()
        ),
    )
    monkeypatch.setattr(
        runner,
        "associate_calibration",
        lambda o, b, p, c, **kw: RegionalAssociation(
            (0, 1, 2), c.postfit.vector, {"final": {"assigned": 20}}, 2
        ),
    )
    config = runner.Hard60Configuration(point_budget=16, levels_km=(100, 50, 25, 12.5), basins=1)
    checkpoints = Checkpoints(interrupt_after=3)
    with pytest.raises(runner.RegionalSliceExpired):
        runner.run_hard60(obs, bank, prior, (), checkpoints, configuration=config)
    checkpoints.interrupt_after = None
    result = runner.run_hard60(obs, bank, prior, (), checkpoints, configuration=config)
    assert set(result["searches"]) == {"V16"}
    assert len(seeds) == len(set(seeds)) == 16
    assert len(result["finals"]) == 6
    assert {r["start"] for r in result["finals"]} == set(config.final_starts)
    assert {r["arm"] for r in result["finals"]} == {"zero-c", "fitted-c"}
    for objective, _start, options in calls:
        assert objective.observations is obs
        assert objective.score.relative_sigma_s == 2
        assert objective.score.common_sigma_s == 3
        assert options["slope_half_width_hz_s"] == 60
        if not options.get("fixed_position"):
            assert options["maximum_iterations"] == 600
            assert options["maximum_seconds"] == 20
    count = len(calls)
    assert runner.run_hard60(obs, bank, prior, (), checkpoints, configuration=config) == result
    assert len(calls) == count
    runner.run_hard60(
        obs, bank, prior, (), checkpoints, configuration=replace(config, final_iterations=601)
    )
    assert len(calls) > count


def test_budget_yields_before_work_and_invalid_policy_is_rejected():
    obs, bank, prior = synthetic_inputs()
    with pytest.raises(runner.RegionalSliceExpired):
        runner.run_hard60(obs, bank, prior, (), Checkpoints(), maximum_seconds=0.001)
    with pytest.raises(ValueError):
        runner.Hard60Configuration(slope_half_width_hz_s=30)
