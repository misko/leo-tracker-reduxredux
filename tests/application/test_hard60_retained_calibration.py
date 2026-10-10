"""The retry trigger is broad, bounded and independent of known coordinates."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from leo.application import hard60_b7
from leo.application import hard60_retained_calibration as recovery
from leo.application.regional_position_runner import json_value


def _ordinary_region(*, source, failed=True):
    original = dict(
        bootstrap=dict(satellite_indices=[0, 1, 2], vector=[5.0, -10.0, *([0.0] * 8)]),
        fits=dict(
            V16=dict(fit=dict(vector=[5.0, -10.0, *([0.0] * 8)], objective=10, converged=False))
        ),
    )
    return dict(
        searches=dict(V16=dict(evaluations=[dict(east_km=5.0, north_km=-10.0, spacing_km=5.0)])),
        points={"point:5:-10": dict(result=deepcopy(original))},
        failures=[dict(stage="calibration", basin="point:5:-10", reason=source)] if failed else [],
        finals=[],
        calibrations={},
    )


def test_all_ordinary_failed_calibrations_trigger_once_across_passes():
    regions = {
        "baseline": _ordinary_region(source="baseline"),
        "sep25": _ordinary_region(source="sep25"),
        "sep50": _ordinary_region(source="sep50", failed=False),
    }
    regions["sep50"]["failures"].extend(
        [
            dict(stage="association", basin="point:5:-10"),
            dict(stage="calibration", basin="recovery:point:5:-10"),
            dict(stage="calibration", basin="point:80:80"),
        ]
    )
    inventory = recovery.regional_triggers(regions)
    assert len(inventory["candidates"]) == 1
    candidate = inventory["candidates"][0]
    assert candidate["basin"] == "point:5:-10"
    assert candidate["source_passes"] == ["baseline", "sep25"]
    assert candidate["identity"]["local_radius_km"] == 25
    assert {row["reason"] for row in inventory["unavailable"]} == {
        "existing-recovery-no-recursion",
        "missing-coarse-or-spacing",
    }
    assert "reference" not in str(inventory).lower()


def test_b7_runs_recovery_before_joint_selection_and_keeps_original_regions(monkeypatch):
    ordinary = _ordinary_region(source="baseline")
    search_calls, recovery_calls, selected = [], [], []

    def search(*args, configuration, **kwargs):
        search_calls.append(configuration.basin_separation_km)
        return deepcopy(ordinary)

    def recover(*args):
        trigger = args[3]
        recovery_calls.append(trigger["basin"])
        return dict(
            finals=[],
            calibrations={},
            recovery=dict(result=dict(status="prefit-unqualified"), reason=None),
        )

    def joint(obs, bank, prior, regions, stage):
        selected.extend(regions)
        assert list(regions)[:3] == ["baseline", "sep25", "sep50"]
        assert len(regions) == 4
        return {}, {}, []

    monkeypatch.setattr(hard60_b7, "run_hard60", search)
    monkeypatch.setattr(hard60_b7, "recovered_region", recover)
    monkeypatch.setattr(hard60_b7, "run_joint_stages", joint)
    result = hard60_b7.run_b7(None, None, None, (), None)
    assert search_calls == [12.5, 25.0, 50.0]
    assert recovery_calls == ["point:5:-10"]
    assert len(selected) == 4
    assert result["b7"]["retained_calibration_recovery"]["candidates"] == 1
    assert (
        next(iter(result["b7"]["retained_calibration_recovery"]["attempts"].values()))[
            "calibration_status"
        ]
        == "prefit-unqualified"
    )
    assert result["searches"] == ordinary["searches"]


def test_recovered_region_keeps_both_c_arms_and_failed_calibration_falls_back(monkeypatch):
    original = _ordinary_region(source="baseline")
    trigger = recovery.regional_triggers({"baseline": original})["candidates"][0]
    monkeypatch.setattr(
        recovery,
        "_recover_calibration",
        lambda *args: dict(status="prefit-unqualified", calibration=None),
    )

    def stage(key, budget, operation):
        return dict(result=operation(), reason=None)

    result = recovery.recovered_region(None, None, None, trigger, stage)
    assert result["finals"] == []
    assert result["calibrations"] == {}
    assert result["recovery"]["result"]["status"] == "prefit-unqualified"
    assert trigger["original"] == original["points"]["point:5:-10"]["result"]


def test_qualified_recovery_matches_both_c_arm_budgets_and_preserves_seed(monkeypatch):
    original = _ordinary_region(source="baseline")
    trigger = recovery.regional_triggers({"baseline": original})["candidates"][0]
    seed = np.r_[5.0, -10.0, np.zeros(9)]
    calls = []

    class Bank:
        numbers = np.array([1, 2, 3, 4])

        def select(self, indices):
            return self

    monkeypatch.setattr(
        recovery, "_recover_calibration", lambda *args: dict(status="qualified", calibration={})
    )
    monkeypatch.setattr(
        recovery,
        "_calibration",
        lambda *args: SimpleNamespace(
            receiver_baseline_hz=np.zeros(4),
            correction=SimpleNamespace(knots_hz=np.zeros((2, 3))),
        ),
    )
    monkeypatch.setattr(
        recovery,
        "associate_calibration",
        lambda *args, **kwargs: dict(
            selected_indices=[0, 1, 2, 3],
            initial_vector=seed.tolist(),
            selection={"final": {"assigned": 4}},
        ),
    )
    monkeypatch.setattr(recovery, "Hard60Objective", lambda *args, **kwargs: object())

    def fit(model, start, **kwargs):
        calls.append((np.asarray(start).copy(), kwargs))
        vector = np.asarray(start).copy()
        if kwargs["rf_arm"] == "zero-c":
            vector[6] = 0
        return dict(vector=vector, objective=1.0, converged=True), {}

    monkeypatch.setattr(recovery, "fit_bounded_position", fit)

    def stage(key, budget, operation):
        return dict(result=json_value(operation()), reason=None)

    result = recovery.recovered_region(None, Bank(), SimpleNamespace(radius_km=250), trigger, stage)
    assert len(result["finals"]) == len(calls) == 6
    assert {row["arm"] for row in result["finals"]} == {"zero-c", "fitted-c"}
    assert all(options["maximum_seconds"] == 20 for _, options in calls)
    assert all(options["maximum_iterations"] == 600 for _, options in calls)
    assert all(options["slope_half_width_hz_s"] == 60 for _, options in calls)
    assert all(row["fit"]["vector"][6] == 0 for row in result["finals"] if row["arm"] == "zero-c")
    assert result["calibrations"] == {"point:5:-10": {}}
    assert trigger["original"] == original["points"]["point:5:-10"]["result"]
