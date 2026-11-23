from pathlib import Path
from types import SimpleNamespace

from reports.ALGO08.v3 import prospective_0155_solver as replay


def snapshot(name, digest, size, collected, where):
    return SimpleNamespace(path=Path(where)/name, sha256=digest, byte_size=size, collected_utc_ns=collected)


def test_content_reuse_keeps_original_name_time_and_reads_no_placeholder_bytes():
    requested = snapshot("original.tle", "a", 150, 120, "/unavailable/bulk")
    original_copy = snapshot("later-duplicate.tle", "a", 150, 140, "/unavailable/tmpfs1")
    competing_copy = snapshot("earlier-duplicate.tle", "a", 150, 100, "/unavailable/tmpfs2")
    plan = replay.archive_plan([requested], [original_copy, competing_copy])
    assert plan == {"original.tle": dict(source=str(original_copy.path), sha256="a", bytes=150, collected_utc_ns=120)}


def test_partial_archive_is_reported_and_never_assigned_a_bulk_source():
    requested = snapshot("original.tle", "a", 150, 120, "/unavailable/bulk")
    wrong_size = snapshot("wrong-size.tle", "a", 149, 120, "/unavailable/tmpfs")
    wrong_sha = snapshot("wrong-sha.tle", "b", 150, 120, "/unavailable/tmpfs")
    plan = replay.archive_plan([requested], [wrong_size, wrong_sha])
    assert plan["original.tle"]["source"] is None and plan["original.tle"]["bytes"] == 150


def test_exact_scope_retains_both_original_processes_and_native_pins():
    assert replay.CASE == "DS30-0155" and replay.ORDER == ("stock", "cumulative")
    assert replay.SETTINGS["windows"] == 6773 and replay.SETTINGS["admitted"] == 6179
    assert set(replay.PINS) >= {"joint_publication.py", "one_pass_web_png.py", "exact_graph_execution.py",
                                "direct_orbit_entry.py", "direct_residual_entry.py"}
