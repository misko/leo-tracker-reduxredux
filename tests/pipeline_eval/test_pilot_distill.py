from dataclasses import replace

import pytest

from tools.pipeline_eval.qualification.pilot_distill_labels import (
    agreements,
    label,
    prevalence_cutoff,
)
from tools.pipeline_eval.qualification.pilot_distill_oracle import solver_eligible
from tools.pipeline_eval.variants.pilot_distill import (
    ALIAS_HZ,
    GATE,
    Rule,
    apply_winners,
    describe,
    strongest,
)


def candidate(epoch, cfo=0, margin=0.4, rank=0, passed=True):
    return dict(
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0.0,
        fractional_tracking_cfo_hz=cfo,
        fractional_exact_score=margin + 0.04,
        fractional_control_score=0.04,
        fractional_margin=margin,
        candidate_rank=rank,
        passed_fractional_margin_gate=passed,
    )


def test_teacher_match_uses_one_physical_family_across_duplicate_epochs_and_aliases():
    teacher = [candidate(1, cfo=100)]
    fast = [
        candidate(100, ALIAS_HZ, 0.2, 2),
        candidate(0, -ALIAS_HZ + 200, 0.4, 1),
        candidate(50, 0, 0.5, 0),
    ]
    peaks = describe(fast, frame=100, tolerance=2)
    outcome = label(teacher, fast, peaks, 100, 2)

    assert outcome.category == "shareable"
    assert sorted(peaks[outcome.positive].members) == [0, 1]
    assert peaks[outcome.positive].representative == 1
    oracle, counts, by_method = agreements(
        [(fast, peaks, outcome)], {"branch_variant": {0: 0}, "strong_wrong": {0: 2}}
    )
    assert oracle == {0: 1}
    assert counts["duplicate_fast_members"] == 1
    assert by_method["branch_variant"]["correct_family"] == 1
    assert by_method["strong_wrong"]["correct_family"] == 0


def test_teacher_ambiguity_absence_and_no_roster_match_keep_distinct_meanings():
    fast = [candidate(18), candidate(22, rank=1)]
    peaks = describe(fast, frame=100, tolerance=2)

    assert label([candidate(20)], fast, peaks, 100, 2).category == "ambiguous"
    assert label([candidate(27)], fast, peaks, 100, 2).category == "no_roster_match"
    assert label([candidate(18, passed=False)], fast, peaks, 100, 2).category == "teacher_negative"
    assert label([candidate(18)], [], (), 100, 2).category == "no_roster_match"

    teacher = [candidate(18), candidate(22, rank=1, passed=False)]
    fast = [candidate(20)]
    assert label(teacher, fast, describe(fast, 100, 2), 100, 2).category == "ambiguous"


def test_linear_order_and_gate_are_monotone_in_candidate_margin_and_threshold():
    rule = Rule((0,) * 4, (1,) * 4, (1, 1, 0, 0.2), 0, 0.3)
    weaker = [candidate(10, margin=0.1), candidate(50, margin=0.1, rank=1)]
    stronger = [candidate(10, margin=0.4), weaker[1]]

    assert rule.select(weaker, 100, 2) is None
    assert rule.select(stronger, 100, 2) == 0
    assert replace(rule, threshold=0.8).select(stronger, 100, 2) is None
    assert rule.select([], 100, 2) is None
    with pytest.raises(ValueError, match="monotone"):
        replace(rule, coefficients=(1, -1, 0, 0))


def test_count_control_and_private_gate_keep_fast_measurements():
    candidates = [candidate(31, margin=0.1), candidate(49, margin=0.3, rank=1)]
    probes = [candidates, [candidate(82, margin=0.4)], []]
    selection = strongest(probes, 1)
    native = {"source": {"probes": [{"candidates": rows, "clock": 1} for rows in probes]}}

    assert selection == {1: 0}
    result = apply_winners(native, selection)
    assert result["source"]["probes"][0]["candidates"] == [
        dict(row, **{GATE: False}) for row in candidates
    ]
    assert result["source"]["probes"][1:] == native["source"]["probes"][1:]
    assert all(row[GATE] for row in candidates)


def test_operating_threshold_weights_recordings_not_pooled_probe_counts():
    threshold = prevalence_cutoff([[3.0, 2.0, 1.0, 0.0], [10.0]], 0.5)

    assert 3 < threshold <= 10


def test_attainable_oracle_preserves_only_compact_eligible_native_measurements():
    rows = [{"candidates": [candidate(9, margin=margin)]} for margin in (-0.01, 0, 0.001)]
    assert solver_eligible([(0, 0), (1, 0), (2, 0)], rows) == {2: 0}


def test_score_is_monotone_in_margin_while_the_family_representative_is_fixed():
    rule = Rule((0,) * 4, (1,) * 4, (1, 1, 0, 1), 0, 0)
    before = describe([candidate(10, margin=0.2), candidate(30, margin=0.15, rank=1)], 100, 2)
    after = describe([candidate(10, margin=0.4), candidate(30, margin=0.15, rank=1)], 100, 2)

    assert rule.score(after[0]) > rule.score(before[0])
    assert rule.score(after[1]) < rule.score(before[1])


def test_scoring_has_no_absolute_epoch_or_cfo_feature():
    rule = Rule((0,) * 4, (1,) * 4, (1, 1, 0, 1), 0, 0)
    peaks = [candidate(11, margin=0.4), candidate(41, margin=0.2, rank=1)]
    moved = [
        dict(
            row,
            integer_epoch_sample=row["integer_epoch_sample"] + 173,
            fractional_tracking_cfo_hz=row["fractional_tracking_cfo_hz"] + 127_319,
        )
        for row in peaks
    ]

    assert rule.select(peaks, 100, 2) == rule.select(moved, 100, 2) == 0
