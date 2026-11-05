from copy import deepcopy

import pytest
from compare_algo07v3_numerical_recovery import compare

from leo.contracts.fast_graph_position_v2 import RF_CHECKS


def fixture():
    targets = [dict(track_id=f"t{i}", observation_ids=[f"n{i}"]) for i in (0, 1)]
    support = {a: dict(owners={"old": 1}) for a in ("c0", "fitted_c")}
    evidence = dict(
        selected_targets=targets,
        publication_support=support,
        eligible_targets=2,
        inventory=dict(summary=[]),
    )
    selected = dict(
        kind="new_family", arms={a: dict(owners={"old": 1, "n1": 3}) for a in ("c0", "fitted_c")}
    )
    previous = dict(recovery_inventory=evidence, predictive_recovery=dict(selected=selected))
    refs, attempts, stages, replay = (
        [],
        [],
        [],
        [
            dict(
                name="inventory",
                original_name="inventory",
                status="complete",
                reused=True,
                reason="graph_and_original_baseline_unchanged",
            )
        ],
    )
    for i in (0, 1):
        vote = dict(status="conditionally_supported_identity", norad=i + 2)
        refs.append(
            dict(
                predictive_annotation=dict(result=dict(track_id=f"t{i}")),
                predictive_inclusion=dict(
                    annotation=vote,
                    shared_family=i == 0,
                    retry=None,
                    selected=None if i == 0 else selected,
                ),
            )
        )
        attempts.append(
            dict(
                track_id=f"t{i}",
                points=1,
                annotation=vote,
                shared_family=i == 0,
                status="RF_rejected" if i == 0 else "RF_qualified",
            )
        )
        for kind in ("annotation", "inclusion", "audit"):
            name = f"target-{i}-{kind}"
            stages.append(dict(name=name, status="complete"))
            reason = (
                "all_saved_reference_updates_inside_15s"
                if kind == "annotation"
                else (
                    "unchanged_shared_fit"
                    if kind == "inclusion"
                    else "unchanged_shared_exact_replay"
                )
                if i == 0
                else "numerical_dependency_changed"
            )
            replay.append(
                dict(
                    name=name,
                    original_name=name,
                    status="complete",
                    reason=reason,
                    reused=i == 0 or kind == "annotation",
                )
            )
    candidate = dict(
        decision="ALGO03_single",
        selected=selected,
        attempts=attempts,
        stages=stages,
        source_support=support,
        inventory_summary=[],
        eligible_tracks=2,
        selected_track_ids=["t0", "t1"],
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
        rf_checks={k: True for k in RF_CHECKS},
    )
    receipt = dict(
        reference_updates=[1], optimizer_calls=[2], problem_count=1, reference_limit_s=30
    )
    refs[1]["predictive_inclusion"]["numerical_policy"] = dict(
        receipt, reference_updates=[1, 1], optimizer_calls=[2, 2], problem_count=2
    )
    numerical = dict(
        candidate=candidate,
        retained=candidate,
        selected=selected,
        decision="ALGO04_additive",
        admission_reason="paired_qualified_candidate_preserves_published_ALGO03_owners",
        completed_target_ids=["t0", "t1"],
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
        numerical_receipts={k: deepcopy(receipt) for k in ("target-1-inclusion", "target-1-audit")},
    )
    return (
        dict(previous, numerical_recovery=numerical, numerical_stage_replay=replay),
        previous,
        *refs,
    )


def test_compare_requires_prefix_selection_reuse_and_numerical_receipts():
    inputs = fixture()
    assert compare(*inputs)["exact_numerical_receipts"]
    candidate = deepcopy(inputs[0])
    candidate["numerical_recovery"]["numerical_receipts"]["target-1-audit"]["reference_limit_s"] = (
        60
    )
    with pytest.raises(ValueError, match="policies differ"):
        compare(candidate, *inputs[1:])
    candidate = deepcopy(inputs[0])
    candidate["numerical_stage_replay"][1]["reused"] = False
    with pytest.raises(ValueError, match="reuse changed"):
        compare(candidate, *inputs[1:])
    candidate = deepcopy(inputs[0])
    candidate["numerical_recovery"]["completed_target_ids"].pop()
    with pytest.raises(ValueError, match="target list changed"):
        compare(candidate, *inputs[1:])
