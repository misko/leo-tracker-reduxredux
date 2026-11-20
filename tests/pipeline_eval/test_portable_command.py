import json
import os
import subprocess
import sys

import pytest

from tools.pipeline_eval import portable_receiver as receiver
from tools.pipeline_eval.__main__ import ROOT, save_json
from tools.pipeline_eval.qualification import portable_command as study


def test_input_digest_checked_before_launch(tmp_path, monkeypatch, capsys):
    source = tmp_path / "locator.json"
    save_json(source, {"id": "saved"})
    output = tmp_path / "output"
    args = ["--input", str(source), "--cpus", "0", "--out", str(output)]
    with pytest.raises(SystemExit, match="2"):
        receiver.main(args)
    assert "--input-sha256" in capsys.readouterr().err

    def prepare(case, out, cpus, raw_limit, position_limit, calibration, smoke):
        assert case == {"id": "saved"}
        assert (cpus, raw_limit, position_limit, calibration, smoke) == (
            [0],
            600,
            180,
            receiver.original.CALIBRATION,
            True,
        )
        out.mkdir()
        return {"id": case["id"]}

    def run(out, lock):
        assert out == output and lock == {"id": "saved"}
        return dict(id=lock["id"], stage="raw", status="stage_only")

    monkeypatch.setattr(receiver, "prepare", prepare)
    monkeypatch.setattr(receiver, "run", run)
    assert receiver.main(args + ["--input-sha256", receiver._sha(source), "--smoke"]) == 0
    assert json.loads((output / "summary.json").read_bytes())["status"] == "stage_only"
    assert json.loads((output / "run-seal.json").read_bytes())["files"] == {
        "summary.json": receiver._sha(output / "summary.json")
    }


def test_raw_timeout_exports_closed_coverage_without_fitting(tmp_path, monkeypatch):
    save_json(tmp_path / "source-lock.json", {})
    plan = dict(
        id="saved",
        workers=[(3, 2, [])],
        cpus=[3],
        raw_limit_s=1,
        position_limit_s=180,
        smoke=False,
        recording=dict(window_count=2),
    )

    def service(attempt, cpu, limit, stage):
        assert (attempt, cpu, limit, stage) == (tmp_path / "raw-3", 3, 1, "raw")
        return dict(exit_code=1, systemd={"Result": "timeout"})

    def collect(out, lock):
        assert (out, lock) == (tmp_path, plan)
        row = dict(
            visit=0, status="processed", detector_cpu_s=0.01, detector_wall_s=0.02, grid_calls=2
        )
        return {(0, 0): ({}, [row])}, {"3": {"terminal": None}}, 1.0

    def fit(*_):
        pytest.fail("partially replayed recording launched a position fit")

    monkeypatch.setattr(receiver.original, "service", service)
    monkeypatch.setattr(receiver.original, "collect", collect)
    monkeypatch.setattr(receiver.original, "fit", fit)
    result = receiver.run(tmp_path, plan)
    assert result["status"] == "timed_out"
    assert result["completed_visits"] == result["completed_chunks"] == 1
    assert result["recorded_visits"] == 2
    assert result["grid_calls"] == 2


def test_worker_entry_point_can_import_without_supervisor_results():
    code = """\
import sys
sys.modules['tools.pipeline_eval.qualification.capture_whole_results'] = None
from tools.pipeline_eval import portable_receiver
assert callable(portable_receiver.worker)
"""
    subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=ROOT,
        env=os.environ | {"OPENBLAS_NUM_THREADS": "1"},
        check=True,
        timeout=20,
    )


def test_external_clock_retains_full_command_boundary(tmp_path):
    clock = tmp_path / "whole-command.time"
    clock.write_text(
        "\tElapsed (wall clock) time (h:mm:ss or m:ss): 4:35.97\n"
        "\tUser time (seconds): 5.49\n"
        "\tSystem time (seconds): 0.84\n"
        "\tMaximum resident set size (kbytes): 322984\n"
        "\tExit status: 0\n"
    )
    assert study.clock(clock, 275.1) == dict(
        elapsed_s=275.97, user_s=5.49, system_s=0.84, supervisor_rss_kib=322984, exit_code=0
    )
    with pytest.raises(ValueError, match="whole-command clock"):
        study.clock(clock, 300)
