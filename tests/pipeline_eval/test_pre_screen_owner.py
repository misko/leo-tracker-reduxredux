from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from named_cold_owner_trace import observe as installed_observer
from pre_screen_owner import Curve, activate, alternative_ids, nominate
from second_curve_gate_trace import ReachedSecondGate, observe as charted_observer, read_gates


def alternatives(points, index=0, norad=12345, alias=-1):
    return dict(start_index=0,stop_index=points,points=points,candidate_index=index,norad=norad,alias=alias)


def test_nominees_require_bound_full_span_and_independent_radio_support():
    curves = {
        "a":Curve(1,1,123e7,("a0","a1")),
        "b":Curve(1,2,124e7,("b0","b1")),
        "peer":Curve(2,3,125e7,("p0",)),
        "other":Curve(1,3,125e7,("o0",)),
    }
    winner = {k:(0,12345,-1) for k in curves}
    first = {k:winner[k] for k in ("peer","other")}
    same = [winner.copy() for _ in range(3)]
    paid = {"a":alternatives(2),"b":alternatives(1)}
    result = nominate(curves,same,winner,first,paid)
    assert result==dict(components={"a":1},nominee="a")
    assert activate(result,["a","b"])=="a"
    assert activate(result,["a"]) is None
    assert activate(result,["b","c"]) is None
    same[2]["a"]=(0,12345,0)
    assert nominate(curves,same,winner,first,paid)["nominee"] is None
    assert nominate(curves,[winner]*3,winner,first,{"a":alternatives(2),"b":alternatives(2)})["nominee"] is None
    assert nominate(curves,[winner]*3,winner,{"other":winner["other"]},paid)["nominee"] is None
    with pytest.raises(ValueError, match="outside"):
        alternative_ids(curves,"a",alternatives(3))


def test_installed_trace_observes_original_scored_order_and_reports_exact_return():
    node = dict(seed={"rows":[dict(component="a",candidate_index=3,candidate_norad=54321)]},aliases=[-2])
    gate = dict(tracks=[dict(component="a",norad=54321,compatible=True,points=2,aliases_changed=0)])
    answer = dict(choices=[dict(node=node,arms={"c0":{"metrics":gate}})]),1
    scan = SimpleNamespace(tracks=[dict(key="a",observation_ids=("o1","o2"))])

    def screen(received, nodes, metrics):
        assert received is scan
        assert nodes[0] is node
        metrics.update(screen_c0_scores=[256.],winning_rank=0,fallback=False,completed_c0_score=253.)
        return answer

    captured = []
    assert installed_observer(screen,captured.append)(scan,[node],{}) is answer
    assert captured[0]["signatures"] == [[("a",3,54321,-2)]]
    assert captured[0]["gate"] == gate["tracks"]
    assert captured[0]["observations"] == {"a":("o1","o2")}


def gate(passed):
    row = dict(component="a",norad=11111,candidate_index=1,points=2,compatible=passed,observation_ids=["o0","o1"],
               aliases_changed=0,profile_rms_hz=88.,profile_bias_hz=9.,conditional_residual_gate=dict(
                   compatible=passed,rms_hz=90.,mean_hz=9.,diagnostics=dict(slope_z=2.8 if passed else 3.2)))
    return dict(tracks=[row],accepted_points=2 if passed else 0)


def test_charted_observer_captures_each_direct_gate_and_can_stop_before_fit():
    calls, tape = [], []
    def real(keep, rows, slices, gates):
        calls.append(gates)
        return keep, [] if gates["accepted_points"] else ["a"]

    def unrelated(operation):
        return operation(2,(),(),gate(True))

    def proposal(operation):
        assert operation(2,(),(),gate(True)) == (2,[])
        assert unrelated(operation) == (2,[])
        return operation(2,(),(),gate(False))

    traced = charted_observer(proposal,real,tape.append)
    assert proposal(traced) == (2,["a"])
    assert [item["screen"] for item in tape] == ["first","after_salvage"]
    assert tape[-1]["tracks"][0]["conditional"]["diagnostics"]["slope_z"] == 3.2
    assert len(calls) == 3
    with pytest.raises(ReachedSecondGate):
        proposal(charted_observer(proposal,real,tape.append,stop_after_second=True))
    assert tape[-1]["screen"] == "after_salvage"


def test_charted_trace_rejects_duplicate_observations_and_keeps_unknown_metric_null():
    tape = gate(False)
    tape["tracks"][0]["conditional_residual_gate"]["diagnostics"]["lag1_acf"] = float("nan")
    assert read_gates(tape)[0]["conditional"]["diagnostics"]["lag1_acf"] is None
    duplicate = dict(tape["tracks"][0], component="b")
    tape["tracks"].append(duplicate)
    with pytest.raises(ValueError, match="active row membership"):
        read_gates(tape)
