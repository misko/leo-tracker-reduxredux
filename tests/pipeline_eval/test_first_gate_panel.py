import pytest

from tools.pipeline_eval.qualification import first_gate_panel as trial
from tools.pipeline_eval.qualification.first_gate_panel_results import compare_witness


def candidate(rank, margin, cfo=100.0):
    return {
        "candidate_rank": rank,
        "fractional_margin": margin,
        "fractional_tracking_cfo_hz": cfo,
        trial.GATE: margin >= trial.MARGIN,
    }


def test_prefix_keeps_rejections_preserves_ranks_and_accounts_for_rank_holes():
    rows = [
        candidate(0, 0.01),
        candidate(2, 0.03),
        candidate(4, 0.02),
        candidate(5, 0.05),
        candidate(7, 0.08, 130.0),
    ]
    streams, stats = trial.assess_lane(rows)
    assert streams["first"] == rows[:2]
    assert streams["second"] == rows[:4]
    for count, retained, avoided in ((stats["first"], 3, 3), (stats["second"], 6, 1)):
        assert count["proved_unexported_ranks"] == 3
        assert count["kept_anchor_calls_lower"] == count["kept_anchor_calls_upper"] == retained
        assert (
            count["skipped_anchor_calls_lower"]
            == count["skipped_anchor_calls_upper"]
            == 8 - retained
        )
        assert count["removed_complete_continuous_calls"] == avoided
        assert count["winner_rank_flips"] and count["compact_observation_flips"]


def test_no_pass_and_fewer_than_two_passes_complete_the_full_attempt():
    rows = [candidate(0, 0.01), candidate(3, 0.02499)]
    streams, stats = trial.assess_lane(rows)
    assert streams == {"first": rows, "second": rows}
    assert all(c["kept_anchor_calls_upper"] == 8 and not c["stopped"] for c in stats.values())
    rows += [candidate(5, 0.025), candidate(7, -0.03)]
    streams, stats = trial.assess_lane(rows)
    assert streams == {"first": rows[:-1], "second": rows}
    assert stats["first"]["stopped"] and not stats["second"]["stopped"]
    assert not stats["first"]["winner_rank_flips"]


def test_non_exported_distinct_rank_is_counted_without_inventing_a_candidate():
    streams, stats = trial.assess_lane([candidate(2, 0.2)])
    assert streams["first"] == streams["second"]
    assert stats["first"]["proved_unexported_ranks"] == 2
    assert stats["first"]["unknown_trailing_ranks"] == 5
    assert stats["first"]["skipped_anchor_calls_lower"] == 0
    assert stats["first"]["skipped_anchor_calls_upper"] == 5


@pytest.mark.parametrize("ranks", ([None], [0, 0], [1, 0], [8]))
def test_impossible_explicit_ranks_are_rejected(ranks):
    with pytest.raises(ValueError, match="rank"):
        trial.assess_lane([candidate(r, 0.2) for r in ranks])


def test_raw_match_uses_final_attempt_and_keeps_primary_miss_unchanged():
    candidates = [candidate(0, 0.01), candidate(2, 0.032), candidate(3, 0.035)]
    probes = [
        dict(receiver_id=0, probe_index=0, candidates=candidates),
        dict(receiver_id=1, probe_index=0, candidates=[]),
    ]
    raw0 = dict(
        receiver=0,
        probe=0,
        retry=False,
        available=4,
        retained_ranks=[0, 1, 2, 3],
        passing_ranks=[2, 3],
        scored=4,
    )
    raw1 = dict(
        receiver=1,
        probe=0,
        retry=False,
        available=3,
        retained_ranks=[0, 1, 2],
        passing_ranks=[],
        scored=3,
    )
    retry = dict(raw1, retry=True)
    full = [raw0, raw1, retry]
    first = [dict(raw0, retained_ranks=[0, 1, 2], passing_ranks=[2], scored=3), raw1, retry]
    witness = {"attempts": {"full": full, "first": first, "second": full}}
    facts = compare_witness(probes, probes, witness)
    assert facts["first"]["original_fractional_calls"] == 10
    assert facts["first"]["stopped_fractional_calls"] == 9
    assert facts["first"]["retry_attempts"] == 1
    witness["attempts"]["first"] = first[:-1]
    with pytest.raises(ValueError, match="retry"):
        compare_witness(probes, probes, witness)
