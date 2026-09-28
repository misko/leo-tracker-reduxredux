from copy import deepcopy

import pytest

from association_transfer_reporting import cohort_summary, summarize


def row(sid="s0", direction="A_to_B", weight=1, gain=.2):
    out={"session_id":sid,"track_id":"t","direction":direction,
         "weight_seconds":weight,"held_count":3}
    for mode,g in (("normal",gain),("reversed",-gain),("null",0.)):
        out[mode]={"baseline_mean_nll":2.,"reception_mean_nll":2.-g,
                   "improvement_baseline_minus_reception":g}
    return out


def test_weighted_mean_and_candidate_independent_control():
    values=[row(weight=1,gain=.2),row(weight=3,gain=-.2)]
    result=summarize(values)["metrics"]["normal"]["improvement_baseline_minus_reception"]
    assert result["equal_track"]==0
    assert result["occupied_second_weighted"]==pytest.approx(-.1)


def test_complete_cohort_keeps_directions_separate():
    sessions=[f"s{i}" for i in range(6)]
    values=[row(sid,d) for sid in sessions for d in ("A_to_B","B_to_A")]
    result=cohort_summary(values,sessions)
    assert result["pooled_by_direction"]["A_to_B"]["tracks"]==6
    with pytest.raises(ValueError,match="reciprocal"):
        cohort_summary(values[:-1],sessions)


def test_empty_support_is_explicit_not_positive_evidence():
    assert summarize([])["metrics"] is None


def test_rejects_non_canceling_null():
    value=row();value["null"]=deepcopy(value["normal"])
    with pytest.raises(ValueError,match="cancel"):
        summarize([value])
