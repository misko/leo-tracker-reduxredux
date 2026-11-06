"""Conditional numerical replay over an owned, completed recovery checkpoint.

The caller supplies stage execution and time-accounting ports. No worker outputs,
paths, clocks, storage or published legacy terminals are runtime dependencies.
"""

import copy
import math

from leo.analysis.localization_v3.annotation_replay import replay_annotation
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.analysis.localization_v3.recovery_acceptance import shared_family_route
from leo.analysis.localization_v3.recovery_controller import recover_tracks
from leo.analysis.research.grouped_prediction import identity_consensus

ARMS = ("c0", "fitted_c")


def overflow(value):
    """Original controller trigger, distinct from the replay validator's trigger."""
    if isinstance(value, dict):
        return value.get("phase_outside_reference_window") is True or any(
            overflow(v) for v in value.values()
        )
    return isinstance(value, list) and any(overflow(v) for v in value)


def additive_admission(incumbent, candidate):
    """Protect every owned point of the freshly audited incumbent, in both arms."""
    if not candidate.get("selected"):
        return False, "no_qualified_numerical_candidate"
    try:
        for arm in ARMS:
            owners = (
                incumbent["selected"]["arms"][arm]["owners"]
                if incumbent.get("selected")
                else incumbent["source_support"][arm]["owners"]
            )
            if not owners or any(
                not isinstance(o, str)
                or not o
                or not isinstance(n, int)
                or isinstance(n, bool)
                or n <= 0
                for o, n in owners.items()
            ):
                raise ValueError("incumbent owner proof missing")
            proposed = candidate["selected"]["arms"][arm]["owners"]
            if any(proposed.get(o) != n for o, n in owners.items()):
                return False, "would_lose_or_change_published_ALGO03_owner"
    except (KeyError, TypeError, ValueError):
        return False, "incumbent_ownership_not_provable"
    return True, "paired_qualified_candidate_preserves_published_ALGO03_owners"


def replay_recovery(
    context,
    evidence,
    incumbent,
    completed_stages,
    *,
    run_stage,
    discovery_allowed,
    clock,
    charge_reused,
    on_selection=None,
):
    """Replay the completed original schedule, then perform additive adoption.

    ``completed_stages`` contains only completed records from the same owned
    predictive run: name -> {value, seconds}. ``charge_reused`` advances the
    caller's logical clock by the original duration minus actual reuse time.
    Admission and execution must consult that clock. Exact ordinary wall-clock
    equivalence still requires separate operational qualification.
    """
    stages = {}
    for name, saved in completed_stages.items():
        seconds = saved["seconds"]
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("finite nonnegative completed stage duration required")
        stages[name] = saved
    completed = []
    for old_index, target in enumerate(evidence["selected_targets"]):
        record = stages.get(f"target-{old_index}-annotation")
        if record is not None:
            if record["value"]["result"]["track_id"] != target["track_id"]:
                raise ValueError("completed annotation belongs to a different target")
            completed.append((old_index, target))
    narrowed = dict(evidence, selected_targets=[target for _, target in completed])
    inventory = dict(evidence["inventory"], publication_support=evidence["publication_support"])
    numerical_context = dict(context)
    annotations, reused_shared, replayed, receipts = {}, set(), [], {}

    def stage(name, operation):
        saved = None
        reason = "numerical_dependency_changed"
        reuse = False
        if name.startswith("target-"):
            _, raw_index, kind = name.split("-", 2)
            index = int(raw_index)
            old_index, target = completed[index]
            old_name = f"target-{old_index}-{kind}"
            saved = stages.get(old_name)
            if kind == "annotation":
                frozen = saved["value"]
                reuse = not overflow(frozen["result"])
                reason = (
                    "all_saved_reference_updates_inside_15s"
                    if reuse
                    else "saved_phase_reference_clipped"
                )
                if not reuse:

                    def operation():
                        return replay_annotation(context, inventory, frozen)
            elif kind == "inclusion":
                annotation = annotations[index]
                vote = identity_consensus(
                    annotation["result"]["folds"], score_name="conditional_target"
                )
                shared = shared_family_route(annotation["result"]["folds"], vote["norad"])
                reuse = bool(
                    shared
                    and saved
                    and "control" in saved["value"]
                    and not annotation["protocol"].get("numerical_replay")
                    and not overflow(saved["value"])
                )
                if reuse:
                    reason = "unchanged_shared_fit"
                    reused_shared.add(index)
            elif kind == "audit":
                reuse = index in reused_shared
                if reuse:
                    reason = "unchanged_shared_exact_replay"
        else:
            index = None
            old_name = name
            if name == "inventory":
                saved = stages.get(name)
                reuse = True
                reason = "graph_and_original_baseline_unchanged"
        record = dict(name=name, original_name=old_name, reused=reuse, reason=reason)
        if reuse:

            def reuse_operation():
                if saved is None:
                    raise ValueError("completed shared audit unavailable; cannot infer its result")
                began = clock()
                value = copy.deepcopy(saved["value"])
                actual = clock() - began
                if not math.isfinite(actual) or actual < 0:
                    raise ValueError("reuse clock must be finite and monotonic")
                charged = max(0.0, saved["seconds"] - actual)
                charge_reused(charged)
                record.update(
                    charged_original_seconds=saved["seconds"],
                    additional_logical_seconds=charged,
                    reuse_wall_seconds=actual,
                )
                return value

            # Reuse remains subject to the original per-stage admission gate.
            ok, value = run_stage(name, reuse_operation)
        else:
            policy = NumericalPolicy(reference_limit_s=30, centered_lbfgsb=True)
            numerical_context["numerical_policy"] = policy
            ok, value = run_stage(name, operation)
            if not name.endswith("-annotation"):
                receipts[name] = copy.deepcopy(policy.receipt)
        record["status"] = "complete" if ok else "failed"
        replayed.append(record)
        if ok and name.endswith("-annotation"):
            annotations[index] = value
        return ok, value

    if "inventory" not in stages:
        raise ValueError("completed inventory and its original duration are required")
    ok, _ = stage("inventory", lambda: None)
    selected_state = []
    if ok:
        candidate = recover_tracks(
            numerical_context,
            narrowed,
            run_stage=stage,
            discovery_allowed=discovery_allowed,
            **({"on_selection": selected_state.append} if on_selection is not None else {}),
        )
    else:
        candidate = dict(selected=None, decision="ALGO02_fallback", failure="Inventory failed")
    admitted, reason = additive_admission(incumbent, candidate)
    if admitted and on_selection is not None:
        if len(selected_state) != 1:
            raise ValueError("Adopted numerical likelihood checkpoint missing")
        on_selection(selected_state[0])
    return dict(
        decision="ALGO04_additive" if admitted else "ALGO03_fallback",
        selected=copy.deepcopy(candidate["selected"] if admitted else incumbent.get("selected")),
        retained=copy.deepcopy(candidate if admitted else incumbent),
        candidate=candidate,
        admission_reason=reason,
        completed_target_ids=sorted(target["track_id"] for _, target in completed),
        stage_replay=replayed,
        numerical_receipts=receipts,
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
    )
