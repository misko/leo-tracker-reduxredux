from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import exact_named_raw as entry


def test_scope_times_real_operations_and_keeps_ordered_selection():
    calls = []
    scan = SimpleNamespace(acquire=lambda: calls.append("acquire"), solve=lambda: calls.append("solve"),
                           render=lambda: calls.append("render"))
    rows = {"c0": [{"observation_id": "b", "norad": 2, "role": "roster"},
                   {"observation_id": "a", "norad": 1, "role": "continuation"}],
            "fitted_c": []}
    position = SimpleNamespace(selected_packet=lambda: {"rows": rows})

    def analyze():
        scan.acquire()
        scan.solve()
        position.selected_packet()
        scan.render()
        return "terminal"

    scan.analyze = analyze
    timings = {key: [] for key in ("analyze", "acquire", "solve", "render")}
    owners = []

    @contextmanager
    def active():
        calls.append("enter")
        yield
        calls.append("exit")

    with ExitStack() as stack:
        entry.observe(scan, position, stack, timings, owners, active=active, timed_acquire=False)
        assert scan.analyze() == "terminal"
    assert calls == ["enter", "acquire", "solve", "render", "exit"]
    assert [len(timings[k]) for k in timings] == [1, 0, 1, 1]
    assert owners == [{"c0": [["b", 2, "roster"], ["a", 1, "continuation"]], "fitted_c": []}]
    assert scan.analyze is analyze


def test_parser_keeps_the_same_receiver_and_named_layout_in_every_region():
    options = ["recording", "archive", "region", "output", "short-binary", "geographic-library",
               "regional-track-library", "frontier-block-library", "archive-sha256"]
    args = entry.parser().parse_args([item for option in options for item in ("--"+option, "staged")])
    assert args.eight_ms_native_history and args.held_anchor_route
    assert args.prove_graph_time_support and args.prove_no_active_curvature
    assert not args.one_pass_web_png and args.portable_orbit_index is None
    assert args.history_risk_route is False
    assert args.strict_packed_eight is False


def test_strict_packed_checks_all_pins_before_ordinary_acquisition(monkeypatch):
    seen = []
    monkeypatch.setattr(entry, "staged_path", seen.append)
    args = SimpleNamespace(strict_packed_eight=False)
    entry.check_strict_input(args)
    assert seen == []
    args.packed_ci16_map = Path("/dev/shm/map.json")
    with pytest.raises(ValueError, match="requires --strict-packed-eight"):
        entry.check_strict_input(args)
    args.strict_packed_eight = True
    args.packed_ci16_codec = Path("/dev/shm/codec.so")
    with pytest.raises(ValueError, match="together"):
        entry.check_strict_input(args)
    assert seen == []
    args.packed_ci16_map_sha256 = "sha256:"+"a"*64
    entry.check_strict_input(args)
    assert seen == [args.packed_ci16_map, args.packed_ci16_codec]


def test_history_risk_scope_calls_original_solve_and_boundary_once(monkeypatch):
    import history_risk_route
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    events = []
    audit = {}
    native, reader, assets, offer, stock_rank = (object() for _ in range(5))
    expected = {"bound_arms": [], "evaluated": False, "would_withhold": False}
    endpoints = {"c0": (12.0, -1.0), "fitted_c": (11.0, -1.0)}

    @contextmanager
    def binding(source, cutoff, proof, rank):
        assert (source, cutoff, proof, rank) == (reader, 25, audit, stock_rank)
        events.append("binding")
        yield
        events.append("restore")

    def inspect(points, width, score, *, terminal_only):
        assert points is endpoints and width == 25.0 and terminal_only
        return expected

    def ordinary(*args):
        assert args == (native, reader, assets, offer)
        events.append("solve")
        return regional_bound_guard.inspect_boundary(endpoints, 25.0, object(), terminal_only=True)

    monkeypatch.setattr(history_risk_route, "binding", binding)
    monkeypatch.setattr(regional_bound_guard, "inspect_boundary", inspect)
    scan = SimpleNamespace(solve=ordinary)
    with entry.risk_solve(scan, 25, stock_rank, audit):
        assert scan.solve(native, reader, assets, offer) is expected
    assert scan.solve is ordinary and regional_bound_guard.inspect_boundary is inspect
    assert events == ["binding", "solve", "restore"]
    assert audit["boundary_checks"] == [dict(width_km=25.0, terminal_only=True, result=expected,
                                             endpoints_east_north_km={"c0": [12.0, -1.0], "fitted_c": [11.0, -1.0]})]


def test_scientific_witness_serializes_real_lean_trace_structure(tmp_path):
    prefix = [dict(branch=np.int64(1), cpu_ns=6343617, parameters=np.array([2.5, -1.25, 0.0, 0.6]))]
    cold = dict(cold=dict(prefix=prefix))
    route = dict(ports=dict(history_risk=dict(lean_attempts=[cold])))
    witness = tmp_path/"exact-named-raw-witness.json"
    entry.write(witness, route, scientific=True)
    loaded = json.loads(witness.read_text())["ports"]["history_risk"]["lean_attempts"][0]["cold"]["prefix"]
    assert loaded == [dict(branch=1, cpu_ns=6343617, parameters=[2.5, -1.25, 0, 0.6])]


def test_staged_scope_denies_symlinks_and_escapes(tmp_path):
    origin = tmp_path/"origin"
    origin.mkdir()
    raw = origin/"member"
    raw.touch()
    unsafe = origin/"link"
    unsafe.symlink_to(raw)
    assert entry.staged_path(raw, root=origin) == raw
    with pytest.raises(ValueError, match="direct"):
        entry.staged_path(unsafe, root=origin)
    with pytest.raises(ValueError, match="escapes"):
        entry.staged_path(tmp_path, root=origin)
    guard = entry.deny_backing(Path("/srv/bulk/approved-private-bind"))
    with pytest.raises(ValueError, match="QNAP"):
        guard("open", ("/mnt/qnap01/something",))
