"""Whole-cohort execution must preserve missing members and input identities."""

import argparse
import json
from pathlib import Path

import pytest

from run_algo03_dataset_evaluation import (
    baseline_one, candidate_one, freeze_dataset, freeze_runtime, read, verify_runtime,
)


def freeze_case(tmp_path, rows):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(members=rows)))
    args = argparse.Namespace(manifest=manifest, dataset="DS23", study=tmp_path / "study",
                              historical_root=None, public_map=None, input_map=None)
    freeze_dataset(args)
    return read(args.study / "datasets/DS23.json")


def member(recording, paths=()):
    return dict(recording_id=recording, recording_format="short_window_iq_recording",
                captured_utc_ns=1, session_id=recording, tracking_inputs=list(paths))


def test_freeze_keeps_unavailable_and_refuses_other_acquisition(tmp_path):
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(dict(source=dict(session_id="another", sample_rate_hz=10000000))))
    saved = freeze_case(tmp_path, [member("one"), member("two", [dict(path=str(wrong))])])
    assert saved["member_count"] == 2
    assert all(row["input"] is None for row in saved["cases"])
    assert "another acquisition" in saved["cases"][1]["rejected_input_candidates"][0]["reason"]


def test_duplicate_acquisition_is_not_a_second_denominator_member(tmp_path):
    with pytest.raises(ValueError, match="Duplicate acquisitions"):
        freeze_case(tmp_path, [member("one"), member("one")])


def test_changed_frozen_input_fails_before_launch(tmp_path):
    source = tmp_path / "tracking.json"
    source.write_text(json.dumps(dict(session_id="one", sample_rate_hz=10000000)))
    saved = freeze_case(tmp_path, [member("one", [dict(path=str(source))])])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "runtime-freeze.json").write_text("{}")
    source.write_text("changed")
    result = baseline_one(saved["cases"][0], tmp_path / "study", runtime, Path("unused"), 1)
    assert result["state"] == "failed"
    assert "Frozen tracking input changed" in result["reason"]
    assert not (tmp_path / "study/cases/DS23-0001/baseline.log").exists()


def test_runtime_edit_is_detected(tmp_path):
    (tmp_path / "source.py").write_text("changed")
    (tmp_path / "runtime-freeze.json").write_text(json.dumps(dict(files={"source.py": "wrong"})))
    with pytest.raises(ValueError, match="Frozen executable changed"):
        verify_runtime(tmp_path)


def test_freeze_preserves_virtual_environment_interpreter_path(tmp_path):
    source = tmp_path / "source"
    manifest = source / "reports/ALGO03/releases/2026-10-30-r1/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(dict(sha256={})))
    binary = tmp_path / "base-python"
    binary.write_text("binary")
    interpreter = tmp_path / "venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(binary)
    args = argparse.Namespace(study=tmp_path / "study", runtime_name=None, kind="baseline",
                              source_root=source, production_root=None, python=interpreter)
    freeze_runtime(args)
    saved = read(args.study / "runtime-baseline/runtime-freeze.json")
    assert saved["python"] == str(interpreter)
    assert saved["python"] != str(interpreter.resolve())


@pytest.mark.parametrize("reused", [True, False])
def test_candidate_routes_snapshot_through_deployed_wrapper(tmp_path, monkeypatch, reused):
    import leo.contracts.fast_graph_position_v2 as contract
    import leo.storage.fast_graph_position as storage
    import run_algo03_dataset_evaluation as runner

    study, runtime = tmp_path / "study", tmp_path / "runtime"
    folder = study / "cases/DS23-0001"
    folder.mkdir(parents=True)
    runtime.mkdir()
    (runtime / "runtime-freeze.json").write_text("{}")
    baseline = dict(state="complete", elapsed_seconds=12)
    snapshot = folder / "source/descriptor.json"
    runner.write(snapshot, dict(terminal=baseline))
    runner.write(folder / "baseline-receipt.json", dict(
        state="complete", terminal=baseline, seconds=2, reused_production=reused,
        descriptor_path=str(snapshot)))
    case = dict(case="DS23-0001", dataset="DS23", input=dict(path="input.json", sha256="input"))
    exported = []

    def export(source, output, destination):
        exported.append((source, output, destination))
        runner.write(destination / "descriptor.json", dict(terminal=baseline))

    monkeypatch.setattr(storage, "export_completed_worker_analysis", export)
    terminal = dict(state="complete", baseline=baseline, decision="ALGO02_fallback",
                    recovery_seconds=4)
    validated = []

    def validate(document, *, input_sha256):
        validated.append(input_sha256)
        assert document == terminal
        return document

    monkeypatch.setattr(contract, "validate_terminal", validate)

    def bounded(command, log_path, timeout, *, cwd, environment):
        assert command[:3] == ["python", "-B", str(runtime / "tools/algo03_production_worker.py")]
        expected = snapshot if reused else folder / "evaluation-export/descriptor.json"
        assert command[3:5] == ["--snapshot", str(expected)]
        assert command[5] == "--preparation-seconds"
        assert float(command[6]) == 2 if reused else float(command[6]) >= 0
        assert command[7:] == ["--output", str(folder / "candidate-v2"), "--maximum-seconds", "60"]
        assert cwd == runtime and str(runtime / "src") in environment["PYTHONPATH"]
        assert timeout <= 90
        runner.write(folder / "candidate-v2/terminal.json", terminal)
        return 0, 123

    monkeypatch.setattr(runner, "bounded", bounded)
    receipt = candidate_one(case, study, runtime, Path("python"), 60)
    assert receipt["state"] == "complete", receipt
    assert receipt["same_executable_as_deployment"] is True
    assert receipt["seconds"] == 4
    assert validated == ["input"]
    assert bool(exported) is not reused


def test_failed_baseline_remains_in_candidate_denominator_without_launch(tmp_path, monkeypatch):
    import run_algo03_dataset_evaluation as runner

    folder, runtime = tmp_path / "study/cases/DS23-0001", tmp_path / "runtime"
    folder.mkdir(parents=True)
    runtime.mkdir()
    (runtime / "runtime-freeze.json").write_text("{}")
    runner.write(folder / "baseline-receipt.json", dict(state="failed"))
    monkeypatch.setattr(runner, "bounded", lambda *a, **kw: pytest.fail("Must not launch recovery"))
    receipt = candidate_one(dict(case="DS23-0001", dataset="DS23"), tmp_path / "study",
                            runtime, Path("unused"), 60)
    assert receipt["state"] == "unavailable"
    assert receipt["reason"] == "baseline_failed"
