import itertools

import pytest
from alias_family import group_alias_families
from finite_set_likelihood import DEFAULT_ALIAS_HZ


def row(
    candidate_id,
    residual_class,
    frequency,
    epoch,
    *,
    margin=0.2,
    rank=0,
    probe=(1, 0, 3),
):
    return {
        "candidate_id": candidate_id,
        "probe_key": list(probe),
        "residual_class": residual_class,
        "tracking_cfo_hz": frequency,
        "fractional_epoch_samples": epoch,
        "fractional_margin": margin,
        "candidate_rank": rank,
        "persisted_score": 10.0 + margin,
    }


def family_map(result):
    return {
        tuple(family["member_candidate_ids"]): (
            family["family_id"],
            family["representative_candidate_id"],
            family["kind"],
        )
        for family in result["families"]
    }


def test_cross_anchor_ambiguity_is_not_tie_broken():
    rows = [
        row("zero-a", "zero", 0.0, 10.0),
        row("zero-b", "zero", 600.0, 10.0),
        row("edge", "edge", 300.0, 10.0, margin=0.9),
    ]

    result = group_alias_families(rows, frame_period_samples=100.0)

    assert [item["candidate_id"] for item in result["ambiguous_edges"]] == ["edge"]
    assert len(result["ambiguous_edges"][0]["qualifying_zero_anchor_family_ids"]) == 2
    assert ("edge",) in family_map(result)
    assert result["policy"]["physical_ambiguity_tie_break_used"] is False


def test_exact_zero_anchors_use_full_alias_and_not_half_alias():
    rows = [
        row("zero-a", "zero", 100.0, 4.0, margin=0.3),
        row("zero-full", "zero", 100.0 + DEFAULT_ALIAS_HZ, 4.1, margin=0.4),
        row("zero-half", "zero", 100.0 + DEFAULT_ALIAS_HZ / 2, 4.1, margin=0.5),
        row("edge", "edge", 150.0 + DEFAULT_ALIAS_HZ, 4.2, margin=0.8),
    ]

    result = group_alias_families(rows, frame_period_samples=100.0)
    grouped = family_map(result)

    assert ("edge", "zero-a", "zero-full") in grouped
    assert ("zero-half",) in grouped
    assert result["policy"]["alias_period_hz"] == DEFAULT_ALIAS_HZ


def test_exact_frequency_zeros_with_distinct_epochs_remain_distinct():
    rows = [
        row("zero-a", "zero", 1000.0, 1.0),
        row("zero-b", "zero", 1000.0 + DEFAULT_ALIAS_HZ, 2.0),
    ]

    result = group_alias_families(rows, frame_period_samples=20.0)

    assert set(family_map(result)) == {("zero-a",), ("zero-b",)}


def test_highest_margin_representative_preserves_original_score_fields():
    rows = [
        row("zero-a", "zero", 10.0, 2.0, margin=0.4, rank=0),
        row("zero-b", "zero", 10.0 + DEFAULT_ALIAS_HZ, 2.1, margin=0.4, rank=1),
        row("edge", "edge", 30.0, 2.2, margin=0.8, rank=7),
    ]

    result = group_alias_families(rows, frame_period_samples=50.0)
    family = next(family for family in result["families"] if len(family["lineage"]) == 3)

    assert family["representative_candidate_id"] == "edge"
    assert family["representative_row"] == rows[2]
    assert family["representative_selection"]["scores_changed"] is False


def test_complete_link_rejects_edge_bridge_without_partial_grouping():
    rows = [
        row("zero", "zero", 0.0, 5.0),
        row("edge-left", "edge", -400.0, 5.0),
        row("edge-right", "edge", 400.0, 5.0),
    ]

    result = group_alias_families(rows, frame_period_samples=50.0)

    assert set(family_map(result)) == {("zero",), ("edge-left",), ("edge-right",)}
    assert {item["reason"] for item in result["ambiguous_edges"]} == {
        "anchor_family_failed_complete_link"
    }
    assert result["policy"]["transitive_closure_used"] is False


def test_other_residual_classes_pass_through_unchanged():
    source = row("other", "plus_or_minus_one", 42.0, 3.0, margin=0.6)

    result = group_alias_families([source], frame_period_samples=20.0)

    assert result["representative_rows"] == [source]
    assert result["families"][0]["kind"] == "passthrough"


def test_family_ids_and_membership_are_permutation_invariant():
    rows = [
        row("zero-a", "zero", 100.0, 4.0, margin=0.3),
        row("zero-b", "zero", 100.0 + DEFAULT_ALIAS_HZ, 4.1, margin=0.4),
        row("edge", "edge", 120.0, 4.2, margin=0.9),
        row("other", "plus_or_minus_one", 9000.0, 8.0),
    ]
    expected = family_map(group_alias_families(rows, frame_period_samples=100.0))

    for permutation in itertools.permutations(rows):
        result = group_alias_families(permutation, frame_period_samples=100.0)
        assert family_map(result) == expected
        assert [row["candidate_id"] for row in result["representative_rows"]] == [
            value[1] for _, value in sorted(expected.items(), key=lambda item: item[1][0])
        ]


def test_invalid_or_duplicate_candidate_ids_are_rejected():
    duplicate = row("same", "zero", 0.0, 0.0)
    with pytest.raises(ValueError, match="not unique"):
        group_alias_families([duplicate, duplicate], frame_period_samples=10.0)
    with pytest.raises(ValueError, match="epoch_tolerance_samples"):
        group_alias_families([duplicate], frame_period_samples=0.5)
