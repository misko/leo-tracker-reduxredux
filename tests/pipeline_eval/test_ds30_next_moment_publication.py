from contextlib import nullcontext
from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import ds30_next_moment_custody as custody
import ds30_next_moment_publication as entry
import exact_graph_execution
from ds30_0036_local_preload import snapshot
from test_moment_fast_publication import capsule_fixture


def test_first_eligible_cannot_cross_pending_rank():
    rows = [{"case": f"C{i}", "disposition": value} for i,value in enumerate(
        ("custody_unavailable_exact_roster", "pending_exact_roster", "eligible", "eligible"))]
    assert custody.selection_for(rows) == (None, "pending")
    rows[1]["disposition"] = "custody_unavailable_residency"
    assert custody.selection_for(rows) == ("C2", "enrolled")


def test_exact_causal_digest_selects_only_signed_names():
    a,b,c = (f"{i}-{'a'*64}.tle" for i in (100, 200, 300))
    digest = custody.meta.roster_digest({b:"a"*64})
    assert custody.exact_window((a,b,c), 300, digest) == {b:"a"*64}
    assert custody.exact_window((a,b,c), 200, digest) is None


def test_approved_saved_preload_copies_verified_immutable_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(entry.held, "CAMPAIGN", tmp_path)
    source = tmp_path/"signed.json"
    source.write_bytes(b'{"authenticated":true}\n')
    digest = entry.saved.identifier(source)
    output = tmp_path/"resident.json"
    copied = snapshot(source, output, source.stat().st_size, digest)
    assert copied["sha256"] == digest and copied["logical_reads"] == 1
    assert output.read_bytes() == source.read_bytes()
    with pytest.raises(ValueError, match="official digest"):
        snapshot(source, tmp_path/"wrong.json", source.stat().st_size, "0"*64)
    assert not (tmp_path/"wrong.json").exists()


def test_both_official_flags_and_matching_pins_are_required(tmp_path):
    keys = ("installed", "successor")
    pins = {role:"sha256:"+str(i)*64 for i,role in enumerate(keys)}
    base = dict(state="observed_pair", verified_pair=True, attempt_result_sha256=pins,
                generation=1, authority_sha256="authority")
    (tmp_path/"pair.json").write_text(json.dumps(base))
    def rows(*, both, verified):
        return [json.dumps(dict(algorithm=k, acquisition_verified=both or k=="installed",
                               verified_pair=verified, attempt_result_sha256=pins[k]),
                           separators=(",", ":")).encode() for k in keys]
    assert custody.complete_pair(tmp_path, rows(both=True, verified=False)) is None
    assert custody.complete_pair(tmp_path, rows(both=True, verified=True))["attempts"] == pins
    with pytest.raises(ValueError, match="acquisition rows"):
        custody.complete_pair(tmp_path, rows(both=False, verified=True))


@pytest.mark.parametrize("edits", [{}, {"o":dict(original_hz=3., forecast_hz=4., updated_hz=4.)}])
def test_live_generic_projection_keeps_identity_and_accepts_zero(edits, monkeypatch):
    @dataclass(frozen=True)
    class Proposals:
        edits: dict

    proposals = Proposals(edits)
    revised = {oid:3.5 for oid in edits}
    proof = dict(moments_valid=True, projected_cfo_sha256=entry.signed.canonical(revised))
    monkeypatch.setattr(entry.moment, "projector", lambda _: lambda graph, found: (revised,proof))
    feature = SimpleNamespace(derive=lambda packet,config: proposals)
    report = {}
    projected = entry.formed_features({}, {}, feature, lambda *_: dict(tracks=[],graph_points=1), report)
    assert projected.edits == {oid:dict(original, updated_hz=3.5) for oid,original in edits.items()}
    assert report["source_half_blend_sha256"] == entry.signed.canonical(edits)
    assert set(report["clocks"]) == {"held_odd_proposals","ordinary_graph","projection"}
    proof["moments_valid"] = False
    with pytest.raises(ValueError, match="moment certificate"):
        entry.formed_features({}, {}, feature, lambda *_: dict(tracks=[],graph_points=1), {})


@pytest.mark.parametrize("role", ("ordinary", "corrected"))
def test_new_saved_entry_calls_the_actual_graph_ports(capsule_fixture, monkeypatch, role):
    from tools.pipeline_eval.variants.experimental import graph_path

    fixture = capsule_fixture
    library = Path(graph_path.__file__).resolve().parents[4]/"graph-path.so"
    original_document = entry.saved.document
    monkeypatch.setattr(entry.saved, "document", lambda path,pin=None:
                        dict(case="DS30-fixture",stage="/tmp/test/field/stage")
                        if path.name == "plan.json" else original_document(path,pin))

    def child(cell, pin, mode, *, probe_only):
        assert entry.capsule.WORKER == entry.WORKER
        assert entry.saved.protocol(entry.held.experiment(probe=False)) == custody.PROTOCOL
        with graph_path.native_paths(library, required=True), exact_graph_execution.graph_execution(
                enabled=True, audit=fixture.outer_graph):
            with fixture.overlay.attach(fixture.native, fixture.audit) if mode=="corrected" else nullcontext():
                fixture.app.prepare_tracks(fixture.native, fixture.config)

    monkeypatch.setattr(entry.capsule, "child", child)
    entry.isolated_child(Path("/tmp/new-moment-fixture/field")/role, "fixture-pin", role, probe_only=False)
    assert fixture.outer_graph["graph"]["calls"] == 1
    if role == "ordinary":
        assert fixture.events == ["ordinary"] and fixture.audit == {}
    else:
        assert fixture.events == ["masked","ordinary","ordinary"]
        assert {oid:row["updated_hz"] for oid,row in fixture.projected.items()} == fixture.values
        proof = fixture.audit["moment_preserving"]["fast_graph_formation"]
        assert all(scope["native_paths"]["native_paths"] > 0 for scope in proof["scopes"].values())
