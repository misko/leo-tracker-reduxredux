from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from cold_incumbent_ceiling import account, checked, without_clocks


def finalist(branch, score, cpu):
    return dict(branch=branch, score=score, cpu_ns=cpu, first_evaluations=17, second_evaluations=4)


def test_prefix_leader_and_final_winner_have_disjoint_work():
    trace = dict(branch=1, routing="ambiguous_gap", scores=[10, 11, None],
                 prefix=[finalist(1, 17, 2), finalist(2, 12, 3), finalist(3, 21, 3)],
                 completed=[finalist(1, 10, 10), finalist(2, 11, 7)])
    result = account(80, trace, 50)
    assert result["winner"] == 1 and result["prefix_leader"] == 2
    assert result["winner_evaluations"] == [17, 4]
    assert result["competitor_cpu_ns"] == 13
    assert result["unitemized_cpu_ns"] == 5
    assert result["optimistic_saving_cpu_ns"] == 18


def test_exact_ceiling_requires_same_winner_and_preserves_ties():
    trace = dict(branch=2, routing="not_three_finalists", scores=[30, 29], prefix=[],
                 completed=[finalist(1, 30, 3), finalist(2, 29, 4)])
    assert account(10, trace)["optimistic_saving_cpu_ns"] == 0
    trace.update(branch=1, scores=[29, 29], completed=[finalist(1, 29, 3), finalist(2, 29, 4)])
    assert account(10, trace)["optimistic_saving_cpu_ns"] == 7
    with pytest.raises(ValueError, match="tie"):
        account(10, trace | dict(branch=2))


def test_reject_double_spent_clocks_and_different_completed_fit():
    trace = dict(branch=1, routing="not_three_finalists", scores=[40], prefix=[], completed=[finalist(1, 40, 15)])
    with pytest.raises(ValueError, match="enclosing cold stage"):
        account(20, trace, 6)
    with pytest.raises(ValueError, match="ordered finalist results"):
        account(20, trace | dict(scores=[39]))
    with pytest.raises(ValueError, match="branch index"):
        account(35, trace | dict(completed=trace["completed"] * 2))


def test_clock_normalization_preserves_assignment_and_fit():
    baseline = dict(branch=1, prefix=[], completed=[finalist(1, 30, 5)], scores=[30], endpoint=[1, 2])
    replay = baseline | dict(completed=[finalist(1, 30, 2)])
    assert without_clocks(baseline) == without_clocks(replay)
    assert baseline["completed"][0]["cpu_ns"] == 5
    assert without_clocks(baseline) != without_clocks(replay | dict(endpoint=[1, 3]))


def test_changed_receipt_is_rejected_before_accounting(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text("{}")
    assert checked(path, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a") == {}
    path.write_text('{"clocks": []}')
    with pytest.raises(ValueError, match="Receipt SHA-256 mismatch"):
        checked(path, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")
