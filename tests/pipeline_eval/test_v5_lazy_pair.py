from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import lazy_pair_trial
from tools.pipeline_eval.variants import v5_lazy_pair


def history_port(c0_good, fitted_good):
    executed = []
    arms = ("c0", "fitted_c")

    def endpoint(arm):
        return [10, 11] if arm == "c0" else [12, 13]

    curved = {arm: {"endpoint_latlon": endpoint(arm)} for arm in arms}

    def refit(_scan, _node, _keep, _powers, _means, _model, arm, _entries):
        executed.append(arm)
        return dict(
            endpoint_latlon=endpoint(arm),
            compatible=(c0_good if arm == "c0" else fitted_good),
            history=[{}] * 5,
            final_phase_change_s=0.0,
        )

    def original():
        linear = {
            arm: module.linear_refit(None, None, None, None, None, None, arm, []) for arm in arms
        }
        accepted = all(linear[arm]["compatible"] for arm in arms)
        return dict(
            linear_arms=linear,
            curved_arms=curved,
            policy_arms=linear if accepted else curved,
            linear_paired_valid=accepted,
            fallback=None if accepted else "curved_pair",
            linear_offered_tracks=2,
            linear_offered_points=12,
            linear_used_points=12 if accepted else 0,
            mask=np.array([True]),
            original_mask=np.array([True]),
            weights=np.array([1.0]),
            hyperparameters_from_pre_RF_TLE_only={"shrinkage": 0.5},
        )

    module = SimpleNamespace(history_policy=original, linear_refit=refit, ARMS=arms)
    return module, original, executed, curved


@pytest.mark.parametrize(
    "c0_good,fitted_good", [(False, False), (False, True), (True, False), (True, True)]
)
def test_lazy_satisfies_the_original_paired_policy_and_hides_unevaluated_diagnostic(
    c0_good, fitted_good
):
    module, original, executed, curved = history_port(c0_good, fitted_good)
    with v5_lazy_pair.predictive_pair(module) as trace:
        result = module.history_policy()
    assert module.history_policy is original
    assert executed == (["c0", "fitted_c"] if c0_good else ["c0"])
    assert result["linear_paired_valid"] == (c0_good and fitted_good)
    assert result["policy_arms"] is (result["linear_arms"] if c0_good and fitted_good else curved)
    assert ("fitted_c" in result["linear_arms"]) == c0_good
    assert not any(
        isinstance(arm, v5_lazy_pair._FittedArm) for arm in result["policy_arms"].values()
    )
    assert trace[0]["c0_passed"] == c0_good
    assert trace[0]["calls"]["c0"][0]["rounds"] == 5


def test_eager_measures_rejected_arm_without_changing_gate_access():
    module, _, executed, curved = history_port(False, True)
    with v5_lazy_pair.predictive_pair(module, eager=True) as trace:
        result = module.history_policy()
    assert executed == ["c0", "fitted_c"]
    assert result["policy_arms"] is curved
    assert result["linear_arms"]["fitted_c"]["compatible"]
    assert trace[0]["fitted_diagnostic"] == "evaluated"
    assert not trace[0]["c0_passed"]
    assert trace[0]["calls"]["fitted_c"][0]["rounds"] == 5


def test_scoring_retains_absent_conditional_rf_rms_in_both_arms():
    def measurement(eager):
        trace = dict(
            c0_passed=False,
            pair_accepted=False,
            fitted_diagnostic="evaluated" if eager else "omitted_after_c0_failure",
            calls={"c0": [{"rounds": 5}], "fitted_c": [{"rounds": 5}] if eager else []},
        )
        metrics = dict(
            predictive_pair=[trace], c0_frequency_score=123, fitted_c_frequency_score=124
        )
        arms = {arm: {"latlon": [10, 11]} for arm in ("c0", "fitted_c")}
        result = dict(status="ok", metrics=metrics, arms=arms)
        return dict(
            id="sample",
            cpu=0,
            input_sha256="same",
            worker_cpu_s=1.0,
            worker_wall_s=1.1,
            result=result,
        )

    found = lazy_pair_trial.compare(measurement(True), measurement(False))
    assert found["positions_exact"] and found["metrics_exact"] and found["expected_calls"]
    assert found["conditional"]["c0"]["lazy"]["conditional_rms_hz"] is None
    assert found["conditional"]["fitted_c"]["control"]["frequency_score"] == 124
