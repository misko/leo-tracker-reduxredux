from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from named_cold_owner_trace import observe as installed_observer
from pre_screen_owner import Curve, activate, alternative_ids, nominate
from second_curve_gate_trace import ReachedSecondGate, instrumented_gate, observe as charted_observer, read_gates
from second_curve_gate_grade import row_headroom


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


def test_original_gate_instrumentation_recovers_family_and_local_failure(monkeypatch):
    import numpy as np
    from leo.analysis.localization_v3 import conservative_recovery as gate_module

    track = dict(key="a",times=np.arange(3.),values=np.zeros(3),rf_hz=11.5e9,receiver=1,channel=1,
                 observation_ids=["o0","o1","o2"])
    scan = SimpleNamespace(tracks=[track],hardware=lambda *args: np.zeros(3),rx_basis=[np.zeros((3,1))])
    model = SimpleNamespace(scan=scan, rows=[dict(candidate_norad=12345,candidate_index=0)],
        members=[0],slices=[slice(0,3)],alias=[0],keep=np.ones(3,dtype=bool),
        state=lambda _:dict(beta=None,smooth=[np.zeros(1)]),
        calculate=lambda _:dict(conditional_residual_hz=np.zeros(3)),
        conditional_frequency=lambda _:(np.zeros(3),np.ones(3)))
    monkeypatch.setattr(gate_module,"whitening",lambda _:())
    monkeypatch.setattr(gate_module,"profile",lambda *_:dict(rms=[12.],bias=[0.],innovations=None,alias=[0]))
    monkeypatch.setattr(gate_module,"conditional_gate",lambda *_:dict(compatible=True,rms_hz=20.,mean_hz=0.,diagnostics={}))
    monkeypatch.setattr(gate_module,"requires_multiple_orbital_owners",lambda *_:True)
    for passing in (True,False):
        monkeypatch.setattr(gate_module,"batch_noise_screen",lambda *_:dict(noise_screen_pass=[passing]))
        original = gate_module.retained_metrics(model,None)
        candidate = instrumented_gate(gate_module.retained_metrics)(model,None)
        row, = candidate["tracks"]
        assert {k:row[k] for k in original["tracks"][0]} == original["tracks"][0]
        trace, = read_gates(candidate)
        assert trace["actual_tests"]["profile_noise"] is passing
        assert trace["family_support_groups"] == (1 if passing else None)


def test_derive_unsigned_slope_at_exact_original_floor():
    row = dict(conditional=dict(compatible=False,rms_hz=12.,mean_hz=3.,diagnostics=dict(
        mean_z=.1,slope_z=3.01,quadratic_bic_gain=-1.,maximum_step_z=1.,lag1_acf=.2)))
    measured = row_headroom(row,[10.,11.,12.,13.])
    assert measured["span_s"] == 3.
    assert measured["conditional_sigma_from_moments_hz"] == 75.
    assert measured["absolute_slope_from_z_hz_per_s"] == pytest.approx(3.01*75./5**.5)
    assert measured["conditional_failed"] == ["slope_z"]
    assert measured["signed_slope_hz_per_s"] is None
