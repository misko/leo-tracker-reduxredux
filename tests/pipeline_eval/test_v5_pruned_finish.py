from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import v5_pruned_finish as method


def mask_partition(train, held):
    return np.ones(train, dtype=bool), np.ones(held, dtype=bool), ()


def test_only_an_impossible_original_fold_or_existing_family_cap_removes_a_target():
    times = np.arange(30.0)
    assert method.target_reason(times, 1, lambda _: [mask_partition(8, 4)] * 3) is None
    for counts in ((7, 4), (8, 3)):
        assert method.target_reason(
            times, 0, lambda _, counts=counts: [mask_partition(*counts)]
        ) == ("required_time_fold_unavailable")
    assert method.target_reason(times, 2, lambda _: pytest.fail("already at family cap")) == (
        "two_existing_families"
    )
    assert method.target_reason([float("nan")], 0, None) is None


def packet(targets, families=0):
    cutoff = 1_000_000_000_000_000
    return dict(
        case="opaque",
        targets=targets,
        scan_receipt=dict(cutoff_utc_ns=cutoff),
        incumbent_family_count=families,
    ), dict(
        cutoff_utc_ns=cutoff,
        elements={"123": dict(element_epoch_utc_ns=cutoff, collected_utc_ns=cutoff)},
    )


def test_ledger_is_checked_at_both_ends_of_the_causal_interval_without_propagation():
    inputs, catalogue = packet([])
    entry = catalogue["elements"]["123"]
    cutoff = catalogue["cutoff_utc_ns"]
    entry["collected_utc_ns"] = cutoff - 72 * 3_600_000_000_000
    counts = {}

    def fail(*args):
        pytest.fail("no residual geometry is needed")

    assert method.residual_targets(inputs, catalogue, None, fail, fail, counts)["targets"] == []
    assert counts["evaluated"] == 0 and not counts["propagated_residual_catalogue"]
    entry["collected_utc_ns"] -= 1
    with pytest.raises(ValueError, match="72-hour"):
        method.residual_targets(inputs, catalogue, None, fail, fail, counts)
    entry["collected_utc_ns"] = cutoff
    entry["element_epoch_utc_ns"] = cutoff + 1
    with pytest.raises(ValueError, match="72-hour"):
        method.check_causal_ledger(catalogue, inputs)
    with pytest.raises(ValueError, match="cutoff"):
        method.check_causal_ledger(dict(catalogue, cutoff_utc_ns=0), inputs)


def test_mixed_residual_targets_preserve_order_and_forward_the_unchanged_measured_winner():
    targets = [
        dict(source=dict(fragment_id=i), times_s=np.arange(n)) for i, n in enumerate([5, 30])
    ]
    inputs, catalogue = packet(targets)
    winner = dict(
        source=targets[1]["source"], summaries=[dict(policy=method.POLICY, screen_pass=True)]
    )

    def numerical(required, ledger, region):
        assert required["targets"] == [targets[1]] and ledger is catalogue and region == "tile"
        return dict(case="opaque", targets=[winner])

    counts = {}
    screened = method.residual_targets(
        inputs, catalogue, "tile", numerical, lambda t: [mask_partition(len(t), 4)], counts
    )
    skipped, evaluated = screened["targets"]
    assert skipped["source"] is targets[0]["source"]
    assert skipped["eligibility"] == "required_time_fold_unavailable"
    assert skipped["summaries"] == [dict(policy=method.POLICY, screen_pass=False)]
    assert evaluated is winner
    assert counts["evaluated"] == 1 and counts["offered"] == 2


def problem(segments):
    rows, slices, keep = [], [], []
    for norad, count, kept in segments:
        rows.append(dict(candidate_norad=norad))
        slices.append(slice(len(keep), len(keep) + count))
        keep.extend([True] * kept + [False] * (count - kept))
    return SimpleNamespace(rows=rows, slices=slices, keep=np.array(keep), reference=())


def test_masked_support_and_first_seen_arm_match_the_final_reassociation_filter():
    a = problem([(12, 15, 15), (12, 16, 15), (4, 35, 35), (6, 20, 14), (6, 18, 15)])
    b = problem([(12, 20, 14), (12, 20, 15), (4, 20, 20), (4, 20, 20), (8, 16, 15), (8, 15, 15)])
    context = dict(problems={"c0": (a, np.zeros(2)), "fitted_c": (b, np.zeros(2))})
    evaluated = []

    def build(ctx, arm, ref, *, omit):
        assert ctx is context
        evaluated.append((arm, omit))
        return (0.5 if omit == 12 else 1.0), {}

    # Each of the two eligible satellites has a total original influence of 1 km.
    oracle = SimpleNamespace(
        derivatives=lambda function, x: (np.zeros(2), np.eye(2)),
        build=build,
        objective=lambda coefficient, _, x: coefficient * x[0],
    )
    counts = {}
    rows, selected = method.rank_eligible(context, oracle, counts)
    assert selected == [8, 12]  # Equal scores are resolved by catalogue ID.
    assert [(r["points"], r["tracks"]) for r in rows] == [(30, 2), (30, 2)]
    assert evaluated == [("c0", 12), ("fitted_c", 8), ("fitted_c", 12)]
    assert counts["original_arm_omissions"] == 6 and counts["evaluated_arm_omissions"] == 3


def test_no_eligible_family_requires_no_objective_or_derivative():
    low = problem([(1, 500, 500), (2, 16, 16), (2, 20, 0)])
    counts = {}
    assert method.rank_eligible({"problems": {"c0": (low, None)}}, None, counts) == ([], [])
    assert counts["observed_families"] == 2 and counts["eligible_families"] == 0
