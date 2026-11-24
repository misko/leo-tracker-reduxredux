from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace

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
