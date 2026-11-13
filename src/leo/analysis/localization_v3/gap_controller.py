"""Ordered conditional gap recovery over owned scientific checkpoints.

The numerical pass supplies rejected attempts and completed annotations. The
adopted incumbent supplies protected ownership, which can come from a different
pass. Stage execution/cancellation and the monotonic clock are explicit ports.
"""

import hashlib
import math
from copy import deepcopy

from leo.analysis.localization_v3.gap_fragments import prepare_gap
from leo.analysis.localization_v3.gap_fragments import partitions
from leo.analysis.localization_v3.gap_recovery import annotate_gap, audit_gap, fit_gap
from leo.analysis.localization_v3.recovery_acceptance import shared_family_route
from leo.analysis.localization_v3.recovery_partitions import require_distinct_annotation
from leo.contracts.fast_graph_position_v4 import qualify

ARMS = ("c0", "fitted_c")


def direct_timing_targets(context, inventory, incumbent_owners):
    """Select one proper native timing component with radio evidence only."""
    grouped = {arm: {} for arm in ARMS}
    for row in inventory["tracks"]:
        if row["arm"] in grouped:
            grouped[row["arm"]][row["track_id"]] = row
    occupied = set().union(*(set(owners) for owners in incumbent_owners.values()))
    candidates = []
    for tid, target in grouped["c0"].items():
        other = grouped["fitted_c"].get(tid)
        if other is None or not target["current_large"] or not other["current_large"]:
            continue
        ids = set(target["observation_ids"])
        if (ids != set(other["observation_ids"])
                or ids != set(target["all_track_observation_ids"])
                or ids != set(other["all_track_observation_ids"])
                or ids & occupied):
            continue
        parent = context["scan"].tracks[target["track_index"]]
        if set(parent["observation_ids"]) != ids:
            raise ValueError("Direct gap parent differs from matched inventory")
        times = parent["times"]
        if not any(b - a > 5 for a, b in zip(times[:-1], times[1:])):
            continue
        for start, stop in partitions(times):
            branch_ids = parent["observation_ids"][start:stop]
            if len(branch_ids) == len(ids):
                continue
            branch_id = hashlib.sha256("\n".join(branch_ids).encode()).hexdigest()[:20]
            candidates.append(dict(track_id=tid, points=len(branch_ids),
                                   parent_points=len(ids), branch_id=branch_id))
    return sorted(candidates, key=lambda row: (-row["points"], row["track_id"],
                                                row["branch_id"]))[:1]


def validate_direct_trial(trial, annotation, incumbent_owners):
    """A qualified direct fit must add precisely the independently annotated component."""
    required = dict(matched_c_arms=True, phase_rounds=5, steps=48,
                    target_calibrates_receiver=False,
                    target_updates_unobserved_satellite_parameters=False,
                    original_noise_weights_and_priors=True,
                    conditional_satellite_refresh=True)
    protocol = trial["protocol"]
    if any(protocol.get(key) != value for key, value in required.items()):
        raise ValueError("Original paired conditional gap fitting protocol required")
    expected = set(annotation["protocol"]["target"]["observation_ids"])
    identity = annotation["result"]["annotation"]["norad"]
    targets = protocol["targets"]
    if (len(targets) != 1 or set(targets[0]["observation_ids"]) != expected
            or targets[0]["norad"] != identity):
        raise ValueError("Direct gap trial changed the independently annotated component")
    fit = trial["target_0"]
    for arm in ARMS:
        before = incumbent_owners[arm]
        proposed = fit["arms"][arm]["proposed_owners"]
        if (any(proposed.get(oid) != norad for oid, norad in before.items())
                or set(proposed) - set(before) != expected
                or any(proposed[oid] != identity for oid in expected)):
            raise ValueError("Direct gap trial changed ownership or branch additions")


def eligible(decision, annotations, incumbent_owners):
    occupied = set().union(*(set(v) for v in incumbent_owners.values()))
    rows = []
    for attempt in decision["attempts"]:
        if not attempt.get("shared_family") or attempt["status"] != "RF_rejected":
            continue
        tid = attempt["track_id"]
        annotation = annotations.get(tid)
        if annotation is None:
            continue
        result, protocol = annotation["result"], annotation["protocol"]
        if result["track_id"] != tid:
            raise ValueError("completed annotation belongs to another parent")
        if (
            result["annotation"]["status"] != "conditionally_supported_identity"
            or result.get("graph_bundle")
            or result.get("inactive_graph_fragment")
            or "gap_source" in annotation
            or protocol["target"].get("native_branch_source")
            or set(protocol["target"]["observation_ids"]) & occupied
        ):
            continue
        rows.append(dict(track_id=tid, points=len(protocol["target"]["observation_ids"])))
    return rows


def select(rows):
    passed = [r for r in rows if r["qualification"]["qualified"]]
    return (
        min(
            passed,
            key=lambda r: (
                -r["identity"]["minimum_margin"],
                -r["qualification"]["added_points"]["fitted_c"],
                r["track_id"],
            ),
        )
        if passed
        else None
    )


def compact(trial, audit, identity, universe, parent_ids):
    rows = []
    for row in audit["rows"]:
        rows.append(
            dict(
                role=row["role"],
                arm=row["arm"],
                verified=row["verified"],
                gate_slacks={
                    k: v
                    for family in row["exact_family_replays"]
                    for k, v in family["all_gate_slacks"].items()
                },
                phase_reference_check=row["phase_reference_check"],
                incumbent_ownership_changes=row["incumbent_ownership_changes"],
            )
        )
    return dict(
        policy="gap_conditional",
        identity=identity,
        observation_ids=sorted(universe),
        target_ids=trial["target_entries"][0]["observation_ids"],
        parent_ids=parent_ids,
        target_times_s=trial["arms"]["fitted_c"]["target_diagnostics"][0]["times_s"],
        trial=dict(
            paired_valid=trial["paired_valid"],
            arms={
                a: {
                    k: r[k]
                    for k in (
                        "endpoint_latlon",
                        "proposed_owners",
                        "proposed_associated_ids",
                        "final_phase_change_s",
                    )
                }
                for a, r in trial["arms"].items()
            },
        ),
        audit=dict(all_verified=audit["all_verified"], rows=rows),
    )


def recover_gaps(
    context,
    inventory,
    observations,
    decision,
    annotations,
    incumbent_owners,
    *,
    run_stage,
    clock,
    maximum_seconds=1200,
    on_selection=None,
    direct_gap_policy=None,
    annotation_training_fit=None,
):
    """Use original eligibility/order/caps and select exactly one qualified fit.

    ``run_stage(name, operation, timeout_s)`` returns (completed, value). It must
    enforce cancellation and return no completed value on failure. A deadline
    expiry raises TimeoutError. The controller reserves the original 20 seconds
    and floors remaining time before admission; there is no internal wall clock.
    """
    if (
        isinstance(maximum_seconds, bool)
        or not math.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= 1200
    ):
        raise ValueError("gap budget must be positive and at most 1200 seconds")
    universe = {o["observation_id"] for o in observations}
    if set(incumbent_owners) != set(ARMS) or any(
        not owners
        or not set(owners) <= universe
        or any(
            not isinstance(sat, int) or isinstance(sat, bool) or sat <= 0 for sat in owners.values()
        )
        for owners in incumbent_owners.values()
    ):
        raise ValueError("explicit matched incumbent ownership required")
    began = clock()
    if not math.isfinite(began):
        raise ValueError("finite monotonic clock required")
    previous = began
    if direct_gap_policy is not None:
        from leo.contracts.localization_v5 import validate_direct_gap_policy

        validate_direct_gap_policy(direct_gap_policy)
    targets = (direct_timing_targets(context, inventory, incumbent_owners)
               if direct_gap_policy is not None else
               eligible(decision, annotations, incumbent_owners))
    rows, stages, excluded, candidates, receipts = [], [], [], {}, {}
    selected_states = {}

    def stage(name, operation, cap):
        nonlocal previous
        now = clock()
        if not math.isfinite(now) or now < previous:
            raise ValueError("finite monotonic clock required")
        remaining = int(began + maximum_seconds - now - 20)
        if remaining < 1:
            raise TimeoutError("conditional gap recovery deadline")
        limit = min(cap, remaining)
        ok, value = run_stage(name, operation, limit)
        ended = clock()
        if not math.isfinite(ended) or ended < now:
            raise ValueError("finite monotonic clock required")
        previous = ended
        stages.append(
            dict(
                name=name,
                status="complete" if ok else "failed",
                seconds=ended - now,
                timeout_s=limit,
            )
        )
        return ok, value

    try:
        for index, target in enumerate(targets):
            tid = target["track_id"]
            prefix = f"gap-{index}"
            ok, source = stage(
                prefix + "-prepare",
                lambda tid=tid: prepare_gap(context, inventory, observations, tid),
                180,
            )
            if not ok:
                continue
            parent_ids = source["protocol"]["parent_observation_ids"]
            for branch in source["branches"]:
                if direct_gap_policy is None and len(branch["observation_ids"]) == target["points"]:
                    continue
                if direct_gap_policy is not None and branch["branch_id"] != target["branch_id"]:
                    continue
                bid = branch["branch_id"]
                name = prefix + "-" + bid
                ok, annotated = stage(
                    name + "-annotation",
                    lambda source=source, bid=bid: annotate_gap(
                        context, inventory, source, bid, observations,
                        **({"training_fit": annotation_training_fit}
                           if direct_gap_policy is not None and annotation_training_fit is not None
                           else {}),
                    ),
                    240,
                )
                if not ok:
                    continue
                annotation, receipts[name + "-annotation"] = annotated
                identity = annotation["result"]["annotation"]
                if identity["status"] != "conditionally_supported_identity":
                    excluded.append(dict(track_id=tid, branch_id=bid, identity=identity))
                    continue
                if direct_gap_policy is not None:
                    require_distinct_annotation(annotation["result"], annotation["protocol"])
                    if annotation_training_fit is not None and (
                            annotation["protocol"].get("training_optimizer_policy")
                            != annotation_training_fit.policy):
                        raise ValueError("Direct gap annotation training policy changed")
                    shared = shared_family_route(annotation["result"]["folds"],
                                                 identity["norad"])
                    if not shared:
                        excluded.append(dict(track_id=tid, branch_id=bid, identity=identity,
                                             reason="independent shared identity failed"))
                        continue
                ok, fitted = stage(
                    name + "-inclusion",
                    lambda annotation=annotation: fit_gap(
                        context, inventory, annotation, observations
                    ),
                    240,
                )
                if not ok:
                    continue
                trial, receipts[name + "-inclusion"] = fitted
                ok, audited = stage(
                    name + "-audit",
                    lambda annotation=annotation, trial=trial: audit_gap(
                        context, inventory, annotation, trial, observations
                    ),
                    180,
                )
                if not ok:
                    continue
                audit, receipts[name + "-audit"] = audited
                fit = trial["target_0"]
                qualification = qualify(fit, audit, incumbent_owners, universe)
                if direct_gap_policy is not None and qualification["qualified"]:
                    validate_direct_trial(trial, annotation, incumbent_owners)
                row = dict(
                    track_id=tid, branch_id=bid, identity=identity, qualification=qualification
                )
                rows.append(row)
                if qualification["qualified"]:
                    candidates[(tid, bid)] = compact(fit, audit, identity, universe, parent_ids)
                    if on_selection is not None:
                        selected_states[(tid, bid)] = dict(
                            selection=dict(kind="gap_conditional", trial=trial),
                            annotations=[annotation],
                            arms=fit["arms"],
                            owners={a: r["proposed_owners"] for a, r in fit["arms"].items()},
                        )
    except TimeoutError as error:
        excluded.append(dict(budget_exhausted=str(error)))
    chosen = select(rows)
    if chosen and on_selection is not None:
        checkpoint = selected_states[(chosen["track_id"], chosen["branch_id"])]
        on_selection(deepcopy(checkpoint))
    return dict(
        **({"policy": direct_gap_policy} if direct_gap_policy is not None else {}),
        selected=chosen,
        candidate=candidates[(chosen["track_id"], chosen["branch_id"])] if chosen else None,
        trials=rows,
        excluded=excluded,
        stages=stages,
        targets=targets,
        numerical_receipts=receipts,
        no_GPS_inference=True,
        causal_only=True,
    )
