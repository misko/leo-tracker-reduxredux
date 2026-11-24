import pytest

from reports.ALGO08.v3.nomination_handoff_0419_admission import enrollment
from reports.ALGO08.v3.nomination_handoff_0289_local import (
    CASE,
    PAIR_PIN,
    RANK_HASH,
    assigned,
    independent_pool,
    previous_blind,
)
from reports.ALGO08.v3.unseen_saved_holdout_score import published_rows


def test_rank_three_is_committed_and_keeps_original_odd_order():
    evidence = assigned()
    assert (evidence["case"], evidence["rank"], evidence["roster_size"]) == (CASE, 3, 87)
    assert evidence["archived_pair_sha256"] == PAIR_PIN
    assert evidence["order"] == ["routed", "installed"]
    assert 0 < evidence["estimated_worker_ceiling_s"] < 120
    with pytest.raises(ValueError, match="rank"):
        enrollment(ranked=2, case=CASE, ranking_hash=RANK_HASH, pair_pin=PAIR_PIN)


def test_pool_preserves_two_independent_records_and_calibration_deltas():
    earlier = previous_blind()
    current = dict(
        case=CASE, time={metric: {"installed": 40, "routed": 20} for metric in ("elapsed_s", "cpu_s")},
        admission={"setup": {"elapsed_s": 1, "cpu_s": 1}},
        jobs={arm: {"decision": "complete"} for arm in ("routed", "installed")},
        candidate_minus_installed_horizontal_m={"c0": 100, "fitted_c": -100}, geographic={},
    )
    result = independent_pool(earlier, current)
    assert result["cases"] == ["DS30-0419", CASE]
    assert result["fixes"] == {"installed": 2, "routed": 2}
    assert result["candidate_minus_installed_horizontal_m"][CASE] == {"c0": 100, "fitted_c": -100}
    named = earlier["time"]["elapsed_s"]["installed"] + 40
    routed = earlier["time"]["elapsed_s"]["routed"] + 20
    setup = earlier["admission"]["setup"]["elapsed_s"] + 1
    assert result["timing"]["elapsed_s"]["summed_speedup"] == pytest.approx(named / routed)
    assert result["timing"]["elapsed_s"]["summed_with_common_admission"] == pytest.approx(
        (named + setup) / (routed + setup)
    )


def test_withhold_has_zero_owners_but_a_completed_arm_requires_rows():
    withheld = {"decision": "withheld", "publication": {"selected_rows": {}}}
    assert published_rows(withheld, "c0") == published_rows(withheld, "fitted_c") == []
    with pytest.raises(KeyError):
        published_rows({**withheld, "decision": "complete"}, "c0")
    withheld["publication"]["selected_rows"]["fitted_c"] = [["observation", 10, "conditional"]]
    with pytest.raises(ValueError, match="withheld"):
        published_rows(withheld, "c0")
