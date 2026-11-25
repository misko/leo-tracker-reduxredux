from contextlib import nullcontext
from pathlib import Path
import sys
from types import SimpleNamespace

import ds30_0280_moment_fast_publication as entry
import exact_graph_execution
import moment_preserving_fast_graph as fast
import pytest


@pytest.fixture
def capsule_fixture(monkeypatch):
    from leo.analysis import graph_tracklets, polynomial_tracklets
    from leo.analysis.localization_v3 import tracks
    from reports.ALGO08.v3.held_cfo_features import DerivedCfo
    from tools.pipeline_eval.variants.experimental import graph_path

    extended = entry.extended
    moment = extended.transfer.moment
    overlay = moment.graph_overlay
    module_ports = ((tracks, "graph_tracks"), (tracks, "fit_lane"), (graph_tracklets, "_graph"),
                    (polynomial_tracklets, "_best_piece"))
    original_ports = [(module, name, getattr(module, name)) for module, name in module_ports]
    library = Path(graph_path.__file__).resolve().parents[4] / "graph-path.so"
    native, masked = {"kind": "ordinary"}, {"kind": "masked"}
    config = polynomial_tracklets.TrackConfig()
    rows = [dict(observation_id=str(i), receiver=1, channel=1, actual_rf_hz=1e10, time_s=float(i),
                 measured_cfo_hz=float(15*i+11*i*i), fractional_margin=9.) for i in range(32)]
    measured = {"ordinary": rows, "masked": rows[::2]}
    fixture = SimpleNamespace(audit={}, events=[], fail=None, outer_graph={}, outer_native={}, result=None)

    def prepare(current, cfg):
        label = current["kind"]
        if fixture.fail == label:
            raise RuntimeError(f"fixture {label} failure")
        fixture.events.append(label)
        winners, metadata = tracks.winning_observations(current)
        assert metadata["detector_sha256"] == "fixture"
        fitted, assigned = tracks.graph_tracks(winners, cfg)
        return dict(observations=winners, tracks=fitted, graph_points=assigned, status="tracks_prepared")

    monkeypatch.setattr(tracks, "winning_observations", lambda current: (measured[current["kind"]],
                                                                         {"detector_sha256": "fixture"}))
    monkeypatch.setattr(tracks, "prepare_tracks", prepare)
    app = SimpleNamespace(prepare_tracks=prepare)
    edits = {row["observation_id"]: dict(original_hz=row["measured_cfo_hz"],
                                        updated_hz=row["measured_cfo_hz"]+(-1)**i*(i+1.))
             for i, row in enumerate(rows[1:18:2])}
    projected = {}

    def derive(current, cfg):
        assert current is native
        graph = tracks.prepare_tracks(masked, cfg)
        return DerivedCfo(("fixture",), edits, dict(assigned=graph["graph_points"]), {}, {}, {})

    def apply(current, winners, formed):
        assert current is native
        projected.update(formed.edits)
        return [dict(row, measured_cfo_hz=formed.edits[row["observation_id"]]["updated_hz"])
                if row["observation_id"] in formed.edits else row for row in winners]

    feature = SimpleNamespace(BIN_HZ=400., derive=derive, apply_to_winners=apply, identity=lambda _: ("fixture",))
    ordinary = prepare(native, config)
    revised, expected = moment.projector(feature)(ordinary, edits)
    expected.update(binding=dict(ordinary_native_sha256=overlay.signed.canonical(native),
                                 edits_sha256=overlay.signed.canonical(edits)),
                    graph=dict(assigned=ordinary["graph_points"], tracks=len(ordinary["tracks"])))
    monkeypatch.setattr(moment, "development", lambda: {"cases": {moment.CASE: expected}})
    fixture.events.clear()

    def attach(current, audit):
        return overlay.bind_graph(app, tracks, feature, config, current, audit, stock_ports=original_ports)

    monkeypatch.setattr(overlay, "attach", attach)
    monkeypatch.setattr(extended.transfer, "enrollment", lambda: {"fixture": "anonymous"})
    monkeypatch.setattr(extended.transfer, "ports", lambda *_: nullcontext())
    read = extended.saved.document
    monkeypatch.setattr(extended.saved, "document", lambda path, pin=None:
                        {"moment_candidate": {}} if path.name == "plan.json" else read(path, pin))

    def child(cell, pin, mode, *, probe_only):
        assert pin == "fixture-pin" and not probe_only
        assert extended.capsule.WORKER == entry.WORKER
        assert extended.saved.protocol(extended.held.experiment(probe=False)) == entry.PROTOCOL
        with graph_path.native_paths(library, required=True) as paths:
            with exact_graph_execution.graph_execution(enabled=True, audit=fixture.outer_graph):
                context = overlay.attach(native, fixture.audit) if mode == "corrected" else nullcontext()
                with context:
                    fixture.result = app.prepare_tracks(native, config)
        fixture.outer_native = dict(paths)

    monkeypatch.setattr(extended.capsule, "child", child)
    fixture.app, fixture.tracks, fixture.moment, fixture.overlay = app, tracks, moment, overlay
    fixture.stock, fixture.original_formation, fixture.original_attach = original_ports, moment.formed_features, attach
    fixture.original_prepare, fixture.winners, fixture.values = prepare, rows, revised
    fixture.projected = projected
    return fixture


def launch(monkeypatch, role):
    path = Path("/tmp/moment-fast-fixture/field") / role
    monkeypatch.setattr(sys, "argv", [str(entry.WORKER), "child", str(path), "--pin", "fixture-pin", "--cell", role])
    return entry.main()


@pytest.mark.parametrize("role", ["corrected", "ordinary"])
def test_normal_entry_selects_only_corrected_formation_with_separate_released_scopes(monkeypatch, capsule_fixture, role):
    fixture = capsule_fixture
    assert launch(monkeypatch, role) == 0
    assert fixture.outer_graph["graph"]["calls"] == 1
    assert fixture.outer_native["native_paths"] > 0
    assert fixture.app.prepare_tracks is fixture.original_prepare
    assert fixture.moment.formed_features is fixture.original_formation
    assert fixture.overlay.attach is fixture.original_attach
    if role == "ordinary":
        assert fixture.events == ["ordinary"] and fixture.audit == {}
        assert fixture.result["observations"] == fixture.winners
        return
    assert fixture.events == ["masked", "ordinary", "ordinary"]
    proof = fixture.audit["moment_preserving"]["fast_graph_formation"]
    assert proof["method"] == fast.METHOD and proof["sources"]["graph-path.so"] == fast.PINS["graph-path.so"]
    assert {key: scope["graph"]["calls"] for key, scope in proof["scopes"].items()} == {
        "held_odd_mask": 1, "ordinary": 1}
    assert all(scope["native_paths"]["native_paths"] > 0 for scope in proof["scopes"].values())
    assert {oid: row["updated_hz"] for oid, row in fixture.projected.items()} == fixture.values
    assert fixture.audit["attempts"][0]["winners"] == len(fixture.winners)


@pytest.mark.parametrize("scope", ["masked", "ordinary"])
def test_normal_entry_restores_formation_and_publication_on_graph_failure(monkeypatch, capsule_fixture, scope):
    fixture = capsule_fixture
    fixture.fail = scope
    with pytest.raises(RuntimeError, match=f"fixture {scope} failure"):
        launch(monkeypatch, "corrected")
    assert fixture.events == ([] if scope == "masked" else ["masked"])
    assert fixture.app.prepare_tracks is fixture.original_prepare
    assert fixture.moment.formed_features is fixture.original_formation
    assert fixture.overlay.attach is fixture.original_attach
    assert fixture.audit["feature_calls"] == 0 and fixture.audit["attempts"] == []
    assert "fast_graph_formation" not in fixture.audit["moment_preserving"]
    assert all(getattr(module, name) is function for module, name, function in fixture.stock)
    assert entry.extended.WORKER.name == entry.FROZEN_SOURCE
