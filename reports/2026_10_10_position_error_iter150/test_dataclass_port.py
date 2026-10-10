"""Real receipt serialization and KKT class, without an optimizer or orbit input."""

import copy
import json
from types import SimpleNamespace

import numpy as np

from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.regional_position_fit import PositionFit
from leo.application.regional_position_runner import json_value
from transition import recovery_port


def test_real_positionfit_nested_diagnostics_and_actual_constraint_audit():
    vector = np.zeros(9)
    vector[:2] = [1, 2]
    saved = json_value(PositionFit(vector, 3, None, 0, 0, True, False, "seed", 1, 0))

    class Model:
        size = 9
        prior = SimpleNamespace(radius_km=100)
        bank = SimpleNamespace(numbers=[1, 2], nodes_s=np.array([-100, 100]))
        observations = SimpleNamespace(times_s=np.array([0, 1]))
        basis = np.array([[1], [-1]]) / np.sqrt(2)

        def evaluate(self, value):
            gradient = np.zeros(9)
            gradient[6] = 0 if value[6] == 2 else 1
            return (2 if value[6] == 2 else 3), gradient, None

    def bounded(model, start, **options):
        np.testing.assert_array_equal(start, vector)
        assert options == dict(
            rf_arm="fitted-c",
            fixed_position=True,
            slope_half_width_hz_s=60,
            maximum_seconds=5,
            maximum_iterations=200,
        )
        start[6] = 2
        fit = PositionFit(start, 2, None, 0, 0, True, False, "synthetic", 7, 0.1)
        return fit, dict(terminal=fit, solver_success=np.bool_(True))

    def unexpected(*args, **kwargs):
        raise AssertionError("already qualified bounded result must not be polished")

    direct = SimpleNamespace(
        continuation=SimpleNamespace(_Problem=_Problem, fit_bounded_position=bounded),
        qualification=SimpleNamespace(qualify=unexpected),
        validated_postfit=lambda model, fit, point: fit,
        fresh_calibration=lambda *args: dict(status="qualified", calibration={"fresh": True}),
    )
    environment = dict(
        direct=direct,
        np=np,
        core=SimpleNamespace(json_value=json_value),
        verify_coarse=lambda *args: (Model(), saved),
    )
    exec("def recovered_region(o,b,p,t,s):\n return recover_calibration(o,b,p,t)", environment)
    trigger = dict(
        key="point:1:2",
        identity={"original": True},
        original={"bootstrap": {"satellite_indices": [0, 1]}},
    )
    before = copy.deepcopy(trigger)
    result = recovery_port({"recovered_region": environment["recovered_region"]}, "zero-c")(
        None, None, None, trigger, None
    )
    handoff = result["handoff"]
    assert handoff["discovery_audit"]["stationarity"] == 0
    assert handoff["fitted_audit"]["stationarity"] == 200
    assert handoff["promoted_audit"]["stationarity"] == 0
    assert handoff["nonlinear"]["solver"]["terminal"]["evaluations"] == 7
    assert handoff["promoted"]["vector"][6] == 2
    assert saved["vector"][6] == 0 and trigger == before
    json.dumps(result, allow_nan=False)
