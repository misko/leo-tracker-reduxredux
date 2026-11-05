"""Ordered original predictive recovery, with explicit execution/admission ports.

The caller owns deadlines and cancellation. A stage port returns (completed,
value); failed or canceled work must never return a completed scientific value.
The admission port is queried for each target, preserving explicit omissions.
Neither port may use a reference position or known localization error.
"""

from copy import deepcopy

from leo.analysis.localization_v3.joint_recovery import (
    audit_joint,
    fit_joint,
    joint_numerical_only,
    probe_joint,
)
from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.analysis.localization_v3.recovery_acceptance import (
    joint_pair,
    numerical_only,
    scoped_pair,
    shared_family_route,
    single_candidate,
)
from leo.analysis.localization_v3.recovery_inclusion import audit_inclusion, fit_new, fit_shared
from leo.analysis.localization_v3.recovery_partitions import require_distinct_annotation
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.contracts.fast_graph_position_v2 import RF_CHECKS

ARMS = ("c0", "fitted_c")
METHODS = ("control", "factorized", "joint")


def recover_tracks(context, evidence, *, run_stage, discovery_allowed, on_selection=None):
    """Evaluate original target order and at most one disjoint new-family pair.

    Timing policy is deliberately not invented inside the numerical implementation.
    Exact ordinary-clock equivalence still requires matched caller admission and
    cancellation behavior; executing every operation is a test-harness policy only.
    """
    inventory = dict(evidence["inventory"], publication_support=evidence["publication_support"])
    targets = evidence["selected_targets"]
    result = dict(
        decision="ALGO02_fallback",
        selected=None,
        attempts=[],
        stages=[],
        source_support=evidence["publication_support"],
        inventory_summary=inventory["summary"],
        eligible_tracks=evidence["eligible_targets"],
        selected_track_ids=[t["track_id"] for t in targets],
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
    )
    qualified, records = [], {}
    selected_state = None

    def stage(name, operation):
        ok, value = run_stage(name, operation)
        result["stages"].append(dict(name=name, status="complete" if ok else "failed"))
        return ok, value

    def joint_experiment(pair, probe, *, optimizer):
        experiment = {m: {} for m in METHODS}
        prefix = "retry-" if optimizer == "powell" else ""
        for method in METHODS:
            for arm in ARMS:
                name = prefix + method + "-" + arm
                ok, trial = stage(
                    name,
                    lambda method=method, arm=arm: fit_joint(
                        context, probe, arm, method, optimizer=optimizer
                    ),
                )
                if not ok:
                    return False, experiment
                control = experiment["control"].get(arm, {}).get("audit")
                ok, audit = stage(
                    name + "-audit",
                    lambda trial=trial, control=control: audit_joint(
                        context, inventory, trial, control
                    ),
                )
                if not ok:
                    return False, experiment
                experiment[method][arm] = dict(trial=trial, audit=audit)
        return True, experiment

    def joint_passes(experiment):
        return all(
            experiment[m][a]["audit"]["RF_qualified_arm"]
            for m in ("control", "joint")
            for a in ARMS
        )

    try:
        for index, target in enumerate(targets):
            tid = target["track_id"]
            attempt = dict(
                track_id=tid, points=len(target["observation_ids"]), status="not_started"
            )
            result["attempts"].append(attempt)
            if not discovery_allowed():
                attempt["status"] = "discovery_budget_exhausted"
                continue
            ok, annotation = stage(
                f"target-{index}-annotation",
                lambda target=target: annotate(
                    context,
                    inventory,
                    target["track_id"],
                    inactive_fragment=target["inactive_fragment"],
                ),
            )
            if not ok:
                attempt["status"] = "annotation_execution_failed"
                continue
            vote = identity_consensus(
                annotation["result"]["folds"], score_name="conditional_target"
            )
            attempt["annotation"] = vote
            if vote["status"] != "conditionally_supported_identity":
                attempt["status"] = vote["status"]
                continue
            require_distinct_annotation(annotation["result"], annotation["protocol"])
            shared = shared_family_route(annotation["result"]["folds"], vote["norad"])
            attempt["shared_family"] = shared
            ok, trial = stage(
                f"target-{index}-inclusion",
                lambda shared=shared, annotation=annotation: (fit_shared if shared else fit_new)(
                    context, inventory, [annotation]
                ),
            )
            if not ok:
                attempt["status"] = "inclusion_execution_failed"
                continue
            ok, audit = stage(
                f"target-{index}-audit",
                lambda trial=trial, shared=shared, annotation=annotation: audit_inclusion(
                    context, inventory, [annotation], trial, shared=shared
                ),
            )
            if not ok:
                attempt["status"] = "audit_execution_failed"
                continue
            candidate = single_candidate(inventory, trial, audit, shared)
            chosen_trial, chosen_audit = trial, audit
            if (
                not shared
                and candidate is None
                and numerical_only(trial["control"], trial["new_family"], audit)
            ):
                attempt["numerical_retry"] = True
                ok, retry = stage(
                    f"target-{index}-retry",
                    lambda annotation=annotation: fit_new(
                        context, inventory, [annotation], optimizer="powell"
                    ),
                )
                if ok:
                    ok, replay = stage(
                        f"target-{index}-retry-audit",
                        lambda retry=retry, annotation=annotation: audit_inclusion(
                            context, inventory, [annotation], retry, shared=False
                        ),
                    )
                if ok:
                    candidate = single_candidate(inventory, retry, replay, False)
                    chosen_trial, chosen_audit = retry, replay
            attempt["status"] = "RF_qualified" if candidate else "RF_rejected"
            if candidate:
                qualified.append(candidate)
                records[id(candidate)] = dict(
                    trial=chosen_trial,
                    audit=chosen_audit,
                    annotation=vote,
                    annotation_source=annotation,
                )
        # Original policy chooses the first qualified target in predeclared order.
        if qualified:
            result.update(selected=qualified[0], decision="ALGO03_single")
            record = records[id(qualified[0])]
            selected_state = dict(
                selection=dict(kind=qualified[0]["kind"], trial=record["trial"]),
                annotations=(
                    [record["annotation_source"]]
                    if record["trial"].get("protocol", {}).get("inactive_fragment_sources")
                    else []
                ),
            )
        pair = joint_pair(qualified)
        if pair:
            ok, probe = stage(
                "joint-probe", lambda: probe_joint(context, [records[id(q)] for q in pair])
            )
            if ok:
                completed, experiment = joint_experiment(pair, probe, optimizer="lbfgsb")
                passed = completed and joint_passes(experiment)
                if completed and not passed and joint_numerical_only(experiment):
                    completed, retry = joint_experiment(pair, probe, optimizer="powell")
                    passed = completed and joint_passes(retry)
                    if passed:
                        experiment = retry
                if passed:
                    entries = [t for q in pair for t in q["targets"]]
                    arms = {a: experiment["joint"][a]["trial"]["result"] for a in ARMS}
                    owners = {a: experiment["joint"][a]["audit"]["owners"] for a in ARMS}
                    candidate = dict(
                        kind="joint",
                        targets=entries,
                        arms=scoped_pair(inventory, arms, owners, entries),
                    )
                    if (
                        candidate["arms"]["c0"]["added_points"]
                        > result["selected"]["arms"]["c0"]["added_points"]
                    ):
                        result.update(decision="ALGO03_joint", selected=candidate)
                        selected_state = dict(
                            selection=dict(
                                kind="joint",
                                trials={a: experiment["joint"][a]["trial"] for a in ARMS},
                            ),
                            annotations=[],
                        )
        if result["selected"]:
            for arm in ARMS:
                if any(
                    result["selected"]["arms"][arm]["owners"].get(o) != n
                    for o, n in result["source_support"][arm]["owners"].items()
                ):
                    raise ValueError("Selected candidate changed an incumbent owner")
            result["rf_checks"] = {key: True for key in RF_CHECKS}
    except Exception as error:
        result.update(
            decision="ALGO02_fallback", selected=None, failure=f"{type(error).__name__}: {error}"
        )
    if on_selection is not None:
        if result["selected"]:
            state = dict(
                selected_state,
                arms=result["selected"]["arms"],
                owners={a: r["owners"] for a, r in result["selected"]["arms"].items()},
            )
        else:
            state = dict(
                selection=None,
                annotations=[],
                arms=inventory["policy"],
                owners={a: r["owners"] for a, r in result["source_support"].items()},
            )
        # Publication of the checkpoint cannot mutate the decision or its inputs.
        # Callback failures propagate; they are not scientific fallback decisions.
        on_selection(deepcopy(state))
    return result
