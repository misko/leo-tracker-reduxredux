"""Check optional rank and portable binding at the combined raw entry."""

from contextlib import contextmanager
import json
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from combined_raw_research import Portable, main, portable_factory, rank_status


def test_rank_requires_paid_compact_profiles_to_report_activation():
    assert rank_status(False, {}) == "disabled"
    assert rank_status(True, {"counts": {}}) == "no_compatible_rank_scope"
    assert rank_status(True, {"counts": {"admitted_ranks": 1, "full_fallback": 3}}) == "original_scoring_only"
    assert rank_status(True, {"counts": {"admitted_ranks": 1, "compact_calls": 1}}) == "compacted"


def test_incompatible_producer_uses_cold_without_reading_its_index(tmp_path, monkeypatch):
    import portable_orbit_index
    from historical_orbit_index import SourceIndex

    def unknown(*args):
        raise AssertionError("An unauthenticated producer is rejected before opening the index")

    monkeypatch.setattr(portable_orbit_index, "load_index", unknown)
    audit = {}
    request = Portable(tmp_path / "artifact.bin", "sha256:" + "a" * 64, "a" * 64)
    assert type(portable_factory(request, audit)) is SourceIndex
    assert audit["transfers"][0]["compatibility"]["fallback"]


def test_combined_wrapper_preserves_normal_receiver_arguments_and_reports_actual_scope(tmp_path, monkeypatch):
    import combined_raw_research
    import continued_cfo

    scoped = []

    @contextmanager
    def runtime(orbit, rank, portable, *, use_blocks):
        assert use_blocks and portable.sha256 == "sha256:" + "c" * 64 and portable.producer_sha256 == "b" * 64
        scoped.append(True)
        yield
        rank["counts"] = {"admitted_ranks": 1, "compact_calls": 3}
        orbit["attempts"] = [{"guard": True}]
        scoped.pop()

    output = tmp_path / "candidate"

    def original(library, argv, *, guarded_pack):
        assert scoped == [True] and library is None and guarded_pack == tmp_path / "guarded"
        assert argv == ["--recording", "/tmp/recording", "--region", "/tmp/offer", "--output", str(output)]

    monkeypatch.setattr(combined_raw_research, "combined_runtime", runtime)
    monkeypatch.setattr(continued_cfo, "raw_entry", original)
    options = Portable(tmp_path / "artifact.bin", "c" * 64, "b" * 64).arguments()
    main(["--anchored-cfo-pack", str(tmp_path / "guarded"), "--recording", "/tmp/recording", *options,
          "--output", str(output), "--catalogue-block-rank", "--region", "/tmp/offer"])
    rank = json.loads((tmp_path / "catalogue-block-rank.json").read_bytes())
    assert rank == dict(status="compacted", requested=True, counts={"admitted_ranks": 1, "compact_calls": 3})
    assert json.loads((tmp_path / "orbits-indexed.json").read_bytes())["attempts"] == [{"guard": True}]


def test_planned_physical_commands_keep_the_same_causal_inputs(tmp_path):
    from combined_raw_trial import ENTRY, flags
    from guarded_cfo_0016_raw import PRIOR, RECORDING, commands

    cmds = commands(tmp_path, tmp_path / "pack", tmp_path / "named", candidate_entry=ENTRY, candidate_options=flags(None))
    for opt, path in (("--recording", RECORDING), ("--region", PRIOR / "offer.json"), ("--archive", PRIOR / "tle")):
        assert all(cmd[cmd.index(opt)+1] == path for cmd in cmds.values())
    assert ENTRY in cmds["candidate"] and "--catalogue-block-rank" in cmds["candidate"]
    assert cmds["stock"][0] == tmp_path / "named" and "--catalogue-block-rank" not in cmds["stock"]


def test_incomplete_physical_stage_does_not_enter_original_launch(tmp_path, monkeypatch):
    import guarded_cfo_0016_raw
    from combined_raw_trial import physical_launch

    def reject(*args, **kwargs):
        raise AssertionError("No code should touch the original physical input")

    monkeypatch.setattr(guarded_cfo_0016_raw, "launch", reject)
    with pytest.raises(ValueError, match="No authenticated full DS30-0016 stage"):
        physical_launch(tmp_path / "results", tmp_path)
