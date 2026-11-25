from types import SimpleNamespace

import ds30_0212_moment_preserving_publication as trial
import numpy as np
import pytest


def test_extracted_frozen_projection_respects_original_membership_and_leaves_other_winners():
    project = trial.projector(SimpleNamespace(BIN_HZ=400.))
    packet = dict(graph_points=4, observations=[dict(observation_id=str(i),time_s=float(i), measured_cfo_hz=0.)
        for i in range(5)], tracks=[dict(key="fixed",indices=list(range(4)),observation_ids=list("0123"),
        pieces=[dict(indices=list(range(4)),degree=1,reference_time_s=1.5,time_scale_s=1.5)])])
    edits = {oid:dict(original_hz=0.,updated_hz=value) for oid,value in zip("0124",(10.,-20.,10.,5.),strict=True)}
    revised, proof = project(packet,edits)
    assert set(revised) == set(edits) and revised["4"] == 0.
    assert np.allclose([revised[str(i)] for i in range(3)], [10.,-20.,10.],rtol=0,atol=1e-12)
    assert proof["surviving_edits"] == 3 and proof["unassigned_edits"] == 1 and proof["moments_valid"]


def test_formation_rejects_replaced_native_handoff_before_any_graph():
    def forbidden(*args):
        raise AssertionError("A changed case could not reach feature formation")

    with pytest.raises(ValueError,match="original saved native"):
        trial.formed_features({"native":"different"},object(),object(),forbidden,{})


def test_exact_online_scope_keeps_original_graph_entry_and_applies_only_formed_features(monkeypatch):
    events = []
    feature = SimpleNamespace(identity=object(),apply_to_winners=object())
    graph = SimpleNamespace(prepare_tracks=object())

    def formed(packet, config, original, ordinary, report):
        assert (packet,config,original,ordinary) == ("native","config",feature,graph.prepare_tracks)
        report["proof"] = True
        events.append("formed")
        return "projected"

    def bind(app, tracks, adapted, config, native, audit, **_kwargs):
        assert adapted.identity is feature.identity and adapted.apply_to_winners is feature.apply_to_winners
        assert adapted.derive(native,config) == "projected"
        return "original-scoped-context"

    def attach(native,audit):
        return trial.graph_overlay.bind_graph(None,graph,feature,"config",native,audit)

    monkeypatch.setattr(trial,"formed_features",formed)
    monkeypatch.setattr(trial.graph_overlay,"bind_graph",bind)
    audit = {}
    assert trial.attach_projected(attach,"native",audit) == "original-scoped-context"
    assert events == ["formed"] and audit["moment_preserving"] == {"proof":True}
