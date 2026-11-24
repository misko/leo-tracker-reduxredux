import pytest

from reports.ALGO08.v3 import nomination_handoff_transfer as audit


def attempt(decision, completed):
    return dict(decision=decision, cold_clocks={"cpu_s": 2.0},
                cold=dict(routing="ambiguous_gap", prefix=[{}, {}, {}], completed=completed, branch=1,
                          scores=[next((r["score"] for r in completed if r["branch"] == i), None)
                                  for i in (1, 2, 3)]))


def finalist(number, score):
    return dict(branch=number, score=score, point=[0.2, -0.1], labels=[3, 5], posterior=[-17., 1.])


def test_two_pauses_per_nominee_are_not_three_completed_nomination_prefixes():
    row = audit.chronology("lean", [attempt("fallback", [finalist(1, 2.)])])
    assert row["first_refresh_pauses"] == 3
    assert row["completed_prefixes"] == 1
    assert row["named_fallback_consumer"] and not row["handoff_on_archived_trace"]


def test_complete_producer_only_allows_reuse_if_named_fallback_actually_runs():
    finals = [finalist(i, float(i)) for i in (1, 2, 3)]
    accepted = audit.chronology("lean", [attempt("complete", finals)])
    assert accepted["numeric_checkpoint_shape"] and not accepted["handoff_on_archived_trace"]
    eligible = audit.chronology("lean", [attempt("fallback", finals)])
    assert eligible["numeric_checkpoint_shape"] and eligible["handoff_on_archived_trace"] is None
    assert not audit.chronology("named", [])["producer_entered"]
    with pytest.raises(ValueError, match="bypass"):
        audit.chronology("named", [attempt("complete", finals)])


def test_rank_credit_requires_exact_ordered_nodes_and_is_independent_of_reuse():
    both = dict(cold_nodes_byte_equal=True, ordered_signatures_match=True, candidate_digest="same", control_digest="same",
                control={"cpu_ns": 10}, candidate={"cpu_ns": 7})
    assert audit.rank_component(both, 6)["grouped_rank_only_cpu_ns_saved"] == 3
    with pytest.raises(ValueError, match="complete matching"):
        audit.rank_component(both | {"candidate_digest": "mismatch"}, 6)
