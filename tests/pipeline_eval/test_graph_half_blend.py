from copy import deepcopy
from types import SimpleNamespace

import graph_half_blend as blend
import numpy as np
import pytest


def fixture():
    native = {
        "a": dict(receiver_id=0, edge="upper", channel=2, actual_rf_hz=11.7e9, sample_counter=7,
                  measured_signed_cfo_hz=-110.),
        "b": dict(receiver_id=0, edge="upper", channel=2, actual_rf_hz=11.7e9, sample_counter=8,
                  measured_signed_cfo_hz=42.),
    }
    record = dict(
        key="track", observation_ids=["a","b"], indices=[2,4], pieces=[{"indices":[2,4]}],
        times=np.array([1.,2.]), values=np.array([890.,42.]),
        receiver=1, channel=2, rf_hz=11.7e9,
    )
    rows = {key:dict(row, observation_id=key, short=True, donor_ids=["x","y"] if i==0 else None,
                     half_blend_delta_hz=20. if i==0 else None, graph_lifted_cfo_hz=value,
                     graph_time_s=t, piece=["track",0], ordinal=i)
            for i,(key,row,t,value) in enumerate(zip(native,native.values(),record["times"],
                                                     record["values"],strict=True))}
    scope = {"assigned": 2}
    plan = dict(native_sha256="pin", scope=scope, proposals={
        "a":dict(interpolation_minus_center_hz=40.,graph_alias_changes=False,neighbors=["x","y"]),
    })
    graph = dict(candidate_native_sha256="pin",graph=scope,observation_rows=list(rows.values()))
    scan = SimpleNamespace(tracks=[record], curved=[0], norads=np.array([10,20]),
                           groups=[("track",[record])], geometry=object(), cache={})
    return rows, native, plan, graph, scan


def test_ledger_and_lift_use_exact_original_signed_rows():
    rows, native, plan, graph, scan = fixture()
    checked, changes = blend.make_ledger(plan,graph,native,"pin",expected=1)
    assert checked==rows and changes=={"a":20.}
    blend.verify_graph(scan.tracks,rows)
    assert blend.raw_values(scan.tracks,native,1_000.)==2
    graph["observation_rows"][0]["half_blend_delta_hz"] *= -1
    with pytest.raises(blend.ProposalBindingError,match="signed half-blend"):
        blend.make_ledger(plan,graph,native,"pin",expected=1)


def test_detached_view_keeps_curvature_and_ignores_future_fit_mutation():
    rows, native, _, _, scan = fixture()
    view = blend.proposal_view(scan,{"a":20.})
    assert view.geometry is scan.geometry and view.curved==scan.curved
    assert view.groups[0][1][0] is view.tracks[0]
    assert view.groups[0][1][0]["values"].tolist()==[910.,42.]
    view.cache["private"] = object()
    assert scan.cache=={}
    blend.verify_graph(scan.tracks,rows)
    with pytest.raises(blend.ProposalBindingError,match="nonnative CFO"):
        blend.raw_values(view.tracks,native,1_000.)


def test_scope_returns_only_categorical_nominations_then_uses_original_fit():
    rows, native, _, _, scan = fixture()
    prepared = {"tracks":{"observations":[dict(observation_id=key,
                                               measured_cfo_hz=row["measured_signed_cfo_hz"])
                                          for key,row in native.items()], "tracks":scan.tracks}}
    scientific = []

    class Model:
        def __init__(self, scan):
            scientific.append(scan.tracks[0]["values"].tolist())

    def cold_node(scan, proposal):
        return dict(aliases=proposal["aliases"],
                    seed=dict(rows=proposal["seed"]["rows"],state="raw-zero-state"))

    decision = dict(component="track",candidate_index=1,candidate_norad=20,active_curvature=True,
                    residual_hz="proposal residual")

    def rank(view):
        Model(view)
        return [dict(seed=dict(rows=[decision],state="proposal state"),aliases=[-1])]

    v5 = SimpleNamespace(ranked_initial_nodes=rank,cold_node=cold_node)

    def original_refine(mode, prepared, region, bound):
        proposals = v5.ranked_initial_nodes(scan)
        assert proposals[0]["seed"]["state"]=="raw-zero-state"
        assert "residual_hz" not in proposals[0]["seed"]["rows"][0]
        Model(scan)
        return proposals[0], None, None, {"branch":1}

    cold = SimpleNamespace(refine=original_refine)
    evidence = SimpleNamespace(selected_packet=lambda *_: "eight figure evidence")
    audit = {}
    with blend.scoped_rank(cold,v5,Model,evidence,rows,native,{"a":20.},1000.,audit):
        cold.refine("race",prepared,None,None)
        signed = dict(scan=scan,arms={"c0":1,"fitted_c":2})
        assert evidence.selected_packet(prepared,signed,None)=="eight figure evidence"
        wrong = deepcopy(prepared)
        wrong["tracks"]["observations"][0]["measured_cfo_hz"] += 20.
        with pytest.raises(blend.ProposalBindingError,match="native observations"):
            evidence.selected_packet(wrong,signed,None)
    assert scientific==[[910.,42.],[890.,42.]]
    assert audit["raw_cold_models"]==audit["evidence_calls"]==1
    assert audit["ranked"]==[[["track",20,-1]]]
    assert cold.refine is original_refine
