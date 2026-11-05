"""Verify a full fresh prefix and conditional replay against individual oracles.

Scope is the two-target fixture with an unchanged shared rejection and one
qualified new-family candidate. This does not qualify production wall-clock
admission or the general multi-target conditional replay policy.
"""

from compare_algo07v3_inclusion import first_difference
from compare_algo07v3_recovery_controller import compare as compare_controller


def exact(expected, actual, what):
    difference = first_difference(expected, actual)
    if difference:
        raise ValueError(what + ": " + difference)


def compare(candidate, previous, shared_reference, numerical_reference):
    prefix = {
        k: v
        for k, v in candidate.items()
        if k not in ("numerical_recovery", "numerical_stage_replay")
    }
    exact(previous, prefix, "Preceding predictive result changed")
    numerical = candidate["numerical_recovery"]
    expected_fields = {
        "candidate",
        "retained",
        "selected",
        "decision",
        "admission_reason",
        "completed_target_ids",
        "numerical_receipts",
        "no_GPS_selection",
        "causal_only",
        "matched_c_arms",
    }
    if set(numerical) != expected_fields:
        raise ValueError("Unexpected numerical result fields")
    if not all(numerical[k] is True for k in ("no_GPS_selection", "causal_only", "matched_c_arms")):
        raise ValueError("Numerical inference invariants changed")
    inventory_prefix = {k: v for k, v in previous.items() if k != "predictive_recovery"}
    controller = dict(inventory_prefix, predictive_recovery=numerical["candidate"])
    verdict = compare_controller(
        controller, inventory_prefix, [shared_reference, numerical_reference]
    )
    exact(
        sorted(t["track_id"] for t in inventory_prefix["recovery_inventory"]["selected_targets"]),
        numerical["completed_target_ids"],
        "Completed target list changed",
    )
    expected_plan = [
        dict(
            name="inventory",
            original_name="inventory",
            reused=True,
            status="complete",
            reason="graph_and_original_baseline_unchanged",
        )
    ]
    for i in (0, 1):
        for kind in ("annotation", "inclusion", "audit"):
            reuse = i == 0 or kind == "annotation"
            reason = (
                "all_saved_reference_updates_inside_15s"
                if kind == "annotation"
                else (
                    "unchanged_shared_fit"
                    if kind == "inclusion"
                    else "unchanged_shared_exact_replay"
                )
                if reuse
                else "numerical_dependency_changed"
            )
            name = f"target-{i}-{kind}"
            expected_plan.append(
                dict(name=name, original_name=name, reused=reuse, status="complete", reason=reason)
            )
    exact(expected_plan, candidate["numerical_stage_replay"], "Conditional reuse changed")
    exact(numerical["candidate"]["selected"], numerical["selected"], "Selected candidate differs")
    exact(numerical["candidate"], numerical["retained"], "Retained result differs")
    if numerical["decision"] != "ALGO04_additive" or numerical["admission_reason"] != (
        "paired_qualified_candidate_preserves_published_ALGO03_owners"
    ):
        raise ValueError("Expected additive adoption on this fixture")
    for arm in ("c0", "fitted_c"):
        old = previous["predictive_recovery"]["selected"]["arms"][arm]["owners"]
        new = numerical["selected"]["arms"][arm]["owners"]
        if any(new.get(o) != n for o, n in old.items()):
            raise ValueError("Published predictive owner changed")
    receipts = numerical["numerical_receipts"]
    if set(receipts) != {"target-1-inclusion", "target-1-audit"}:
        raise ValueError("Unexpected numerical work")
    combined = dict(receipts["target-1-inclusion"])
    constants = {
        k: v
        for k, v in combined.items()
        if k not in ("reference_updates", "optimizer_calls", "problem_count")
    }
    exact(
        constants,
        {
            k: v
            for k, v in receipts["target-1-audit"].items()
            if k not in ("reference_updates", "optimizer_calls", "problem_count")
        },
        "Fit and audit numerical policies differ",
    )
    for key in ("reference_updates", "optimizer_calls"):
        combined[key] = combined[key] + receipts["target-1-audit"][key]
    combined["problem_count"] += receipts["target-1-audit"]["problem_count"]
    exact(
        numerical_reference["predictive_inclusion"]["numerical_policy"],
        combined,
        "Numerical optimizer/domain receipts differ",
    )
    return dict(
        verdict,
        conditional_replay=True,
        additive_owners_preserved=True,
        exact_numerical_receipts=True,
        completed_targets=2,
        reused_stages=sum(r["reused"] for r in expected_plan),
        recomputed_stages=sum(not r["reused"] for r in expected_plan),
        scope="Fresh native-prepared prefix and two-target conditional numerical replay",
    )
