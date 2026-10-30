"""Shared predictive fits need numerical qualification in every paired stage."""

import copy
import json

import pytest
from algo03_shadow_worker import ARMS, single_candidate


def shared_trial(tmp_path, fit=None):
    if fit is None:
        fit = dict(stopped="small_step_and_improvement")
    incumbent = {arm: dict(owners=dict(old=1)) for arm in ARMS}
    inventory = dict(publication_support=incumbent)
    arms = {
        arm: dict(
            endpoint_east_north_km=[0.0, 0.0],
            endpoint_latlon=[37.906, -122.545],
            negative_twice_elbo=123.0,
            proposed_owners=dict(old=1, target=2),
            history=[dict(fit=copy.deepcopy(fit))],
        )
        for arm in ARMS
    }
    documents = {
        "protocol.json": dict(targets=[dict(norad=2, observation_ids=["target"])]),
        "control.json": dict(paired_valid=True, arms=copy.deepcopy(arms)),
        "target_0.json": dict(paired_valid=True, arms=copy.deepcopy(arms)),
        "exact_owner_replay.json": dict(
            all_verified=True,
            rows=[
                dict(role=role, arm=arm, verified=True)
                for role in ("control", "target_0")
                for arm in ARMS
            ],
        ),
    }
    return inventory, documents


def save_trial(path, documents):
    for name, document in documents.items():
        (path / name).write_text(json.dumps(document))


@pytest.mark.parametrize("role", ["control", "target_0"])
@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize(
    "fit",
    [
        dict(success=False),
        dict(stopped="iteration_budget"),
        dict(stopped="no_accepted_damped_step"),
        dict(success=False, stopped="small_step_and_improvement"),
        {},
    ],
)
def test_any_unqualified_control_or_addition_arm_rejects_shared_candidate(tmp_path, role, arm, fit):
    inventory, documents = shared_trial(tmp_path)
    documents[role + ".json"]["arms"][arm]["history"][-1]["fit"] = fit
    save_trial(tmp_path, documents)
    assert single_candidate(inventory, tmp_path, shared=True) is None


@pytest.mark.parametrize("fit", [dict(success=True), dict(stopped="small_step_and_improvement")])
def test_successful_optimizer_or_converged_gauss_newton_can_qualify(tmp_path, fit):
    inventory, documents = shared_trial(tmp_path, fit)
    save_trial(tmp_path, documents)
    candidate = single_candidate(inventory, tmp_path, shared=True)
    assert candidate["kind"] == "shared_family"
    assert candidate["arms"]["c0"]["owners"] == dict(old=1, target=2)
    assert candidate["arms"]["c0"] == candidate["arms"]["fitted_c"]


@pytest.mark.parametrize(
    "failed_stage", ["control.json", "target_0.json", "exact_owner_replay.json"]
)
def test_numerical_completion_does_not_override_failed_scientific_stage(tmp_path, failed_stage):
    inventory, documents = shared_trial(tmp_path)
    documents[failed_stage][
        "all_verified" if failed_stage == "exact_owner_replay.json" else "paired_valid"
    ] = False
    save_trial(tmp_path, documents)
    assert single_candidate(inventory, tmp_path, shared=True) is None
