from copy import deepcopy
from pathlib import Path

import pytest

from reports.ALGO08.v3 import history_risk_0016_cairo as cairo


def test_optional_command_keeps_the_same_ordinary_receiver_and_adds_only_renderer(tmp_path, monkeypatch):
    import exact_named_raw

    parser = exact_named_raw.parser()
    if not any(cairo.OPTION in action.option_strings for action in parser._actions):
        parser.add_argument(cairo.OPTION, action="store_true")
    monkeypatch.setattr(exact_named_raw, "parser", lambda: parser)
    req, _, _, _ = cairo.ordinary.references()
    libs = cairo.ordinary.pinned_archive(cairo.ordinary.LIBRARIES)["raw_binding"]["libraries"]
    commands = cairo.ordinary.arguments(tmp_path, req, "/opt/leo-algo08/algo08v3/run", "/opt/release/python", libs)
    ref = {"admission": {"commands": commands}}
    output = tmp_path/"new"/"candidate"
    actual = cairo.candidate_argv(ref, output)
    expected = commands["candidate"].copy()
    expected[expected.index("--output")+1] = str(output)
    assert actual == expected + [cairo.OPTION]
    assert "--bulk-root" not in actual and commands["stock"] == ref["admission"]["commands"]["stock"]


def test_all_semantic_and_official_media_evidence_is_required_for_optional_launch():
    names = ("ch1-4-all", "ch5-8-all", "ch1-4-residuals", "ch5-8-residuals", "ch1-4-unassociated",
             "ch5-8-unassociated", "position", "track-rms")
    standard_science = dict(evidence=dict(images={name: {"sha256": "a"} for name in names}, owner_rows={}),
                            ports={"png": cairo.PNG_COUNTS})
    optional = dict(evidence=dict(images={name: {"sha256": "b"} for name in names}, owner_rows={}),
                    ports={"png": cairo.PNG_COUNTS, "cairo_layout": cairo.LAYOUT_COUNTS})
    signed = {"decision": "complete", "session_id": "physical"}
    strengths = dict(artists={name: dict(axes=1, changed_tick_sets=0) for name in cairo.ARTISTS}, sidecars={"grid": {}, "path": {}},
                     media={name: dict(stock_file_sha256="a", cairo_file_sha256="b") for name in names},
                     runs={mode: dict(clock=dict(exit_code=0, elapsed_s=s), terminal=signed, receipt=signed, scientific=doc)
                           for mode, s, doc in (("standard", 5, standard_science), ("cairo", 4, optional))})
    trusted = dict(terminal=signed, scientific=standard_science)
    request = dict(session="physical")
    assert cairo.saved_gate(strengths, request, trusted, names)["cairo"] == optional

    changed = deepcopy(strengths)
    changed["media"]["position"]["cairo_file_sha256"] = "tampered"
    with pytest.raises(ValueError, match="official PNG"):
        cairo.saved_gate(changed, request, trusted, names)
    for fault in ({"native_orbit_figures": 3}, {"orbit_fallbacks": 1}):
        changed = deepcopy(strengths)
        changed["runs"]["cairo"]["scientific"]["ports"]["cairo_layout"].update(fault)
        with pytest.raises(ValueError, match="semantic and speed"):
            cairo.saved_gate(changed, request, trusted, names)
    changed = deepcopy(strengths)
    changed["artists"]["ch1-4-orbit"]["changed_tick_sets"] = 1
    with pytest.raises(ValueError, match="visible axis audit"):
        cairo.saved_gate(changed, request, trusted, names)


def test_no_reference_or_child_is_opened_before_stage_readiness(tmp_path, monkeypatch):
    monkeypatch.setattr(cairo.ordinary, "enrolled", lambda: {})
    monkeypatch.setattr(cairo.ordinary, "readiness", lambda *args: dict(ready=False, missing_bytes=123))
    monkeypatch.setattr(cairo, "launch_ready", lambda *args: pytest.fail("incomplete custody attempted a launch"))
    with pytest.raises(ValueError, match="123 signed bytes missing"):
        cairo.launch(tmp_path/"output", tmp_path, Path("/absent-pair"), Path("/absent-score"), "absent-pin")
    assert not (tmp_path/"output").exists()
