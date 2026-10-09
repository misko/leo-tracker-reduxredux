from copy import deepcopy

import numpy as np

from leo.application.hard60_b7 import SharedPoints, regional_winners, run_joint_stages
from tests.analysis.test_hard60_joint import setup


def test_region_selection_preserves_ties_and_ignores_nonstationary_lower_scores():
    row = dict(
        arm="fitted-c",
        basin="point:0:0",
        start="association",
        calibration_penalty=10,
        fit=dict(objective=100, converged=True),
    )
    original = dict(finals=[row])
    additional = deepcopy(original)
    additional["finals"][0]["fit"].update(objective=1, converged=False)
    assert (
        regional_winners(dict(baseline=original, sep25=additional))["fitted-c"]["region_source"]
        == "baseline"
    )
    additional["finals"][0]["fit"].update(objective=100, converged=True)
    assert (
        regional_winners(dict(baseline=original, sep25=additional))["fitted-c"]["region_source"]
        == "baseline"
    )
    additional["finals"][0]["fit"]["objective"] = 99
    assert (
        regional_winners(dict(baseline=original, sep25=additional))["fitted-c"]["region_source"]
        == "sep25"
    )


def test_only_coarse_points_share_checkpoint_keys():
    cache = SharedPoints(None)
    assert cache.key("sha256:aaa:point:5:-10") == cache.key("sha256:bbb:point:5:-10")
    assert cache.key("sha256:aaa:point:5:-10:calibration") != cache.key(
        "sha256:bbb:point:5:-10:calibration"
    )


def test_failed_fitted_prerequisite_stops_and_retains_each_arms_qualified_result():
    base, model = setup()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    value = base.evaluate(seed)[0]
    finals = [
        dict(
            arm=arm,
            method="V16",
            basin="point:0:0",
            start="association",
            calibration_penalty=1,
            satellites=base.bank.numbers.tolist(),
            association=dict(final=dict(assigned=1)),
            fit=dict(vector=seed.tolist(), objective=value, converged=True),
        )
        for arm in ("fitted-c", "zero-c")
    ]
    calibration = dict(
        receiver_baseline_hz=base.baseline.tolist(),
        correction=dict(
            nodes_s=model.nodes.tolist(),
            knots_hz=(model.initial_clock.reshape(2, -1) @ model.null.T).tolist(),
        ),
    )
    regions = dict(baseline=dict(finals=finals, calibrations={"point:0:0": calibration}))
    called = []

    def stage(key, budget, operation):
        called.append(key)
        return dict(
            result=dict(converged=key.endswith("zero-c"), objective=value + 1000), reason=None
        )

    selected, _, reasons = run_joint_stages(
        base.observations, base.bank, base.prior, regions, stage
    )
    assert called == ["b7:B3:fitted-c", "b7:B3:zero-c"]
    assert selected["fitted-c"]["accepted_stage"] == "B1"
    assert selected["zero-c"]["accepted_stage"] == "B3"
    assert reasons == ["B3:fitted-c:nonstationary"]
