import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("ds11_screen_tests", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_plan_rejects_stale_dependencies_and_duplicate_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HERE", tmp_path)
    dependency = tmp_path / "dependency"
    dependency.write_text("frozen")
    job = dict(index=0, family="robust_t8_scale100", norad=1, cache=None)
    plan = dict(schema="ds11-source-loo-exact-screen-plan/v1", jobs=[job],
                sources={str(dependency): runner.digest(dependency)})
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    assert runner.load_plan()["jobs"] == [job]
    dependency.write_text("changed")
    with pytest.raises(ValueError, match="changed plan dependency"):
        runner.load_plan()
    dependency.write_text("frozen")
    plan["jobs"].append(job)
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="duplicate job"):
        runner.load_plan()


def test_cached_job_is_rejected_before_any_numerical_import(monkeypatch):
    job = dict(index=0, family="iid_t4_scale100", norad=1,
               cache={"kind": "family", "path": "/unused"})
    monkeypatch.setattr(runner, "load_plan", lambda: {"jobs": [job]})
    monkeypatch.setattr(runner, "module", lambda *args: pytest.fail("cached fit was re-entered"))
    with pytest.raises(ValueError, match="must not be repeated"):
        runner.one(runner.job_key(job))


def test_timeout_is_persisted_and_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HERE", tmp_path)
    for name in ("run.py", "plan.json", "PROTOCOL.md"):
        (tmp_path / name).write_text("frozen")
    calls = []

    def timeout(command, **kwargs):
        calls.append(command)
        assert command[command.index("timeout") + 1:command.index("timeout") + 3] == ["--kill-after=5s", "90s"]
        assert "OPENBLAS_NUM_THREADS=1" in command
        return SimpleNamespace(returncode=124)

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    job = dict(index=0, family="robust_t8_scale100", norad=1, cache=None)
    first = runner.launch(job)
    second = runner.launch(job)
    assert first["exit_code"] == second["exit_code"] == 124
    assert second["existing_terminal_attempt"]
    assert len(calls) == 1
    receipt = tmp_path / "runs" / f"{runner.job_key(job)}.receipt.json"
    assert json.loads(receipt.read_text())["run_sha256"] == runner.digest(tmp_path / "run.py")


def test_batch_stops_when_previous_scan_cannot_select(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HERE", tmp_path)
    folder = tmp_path / "selections"
    folder.mkdir()
    (folder / "00.json").write_text(json.dumps({"index": 0, "selectable": False}))
    monkeypatch.setattr(runner.sys, "argv", ["run.py", "batch", "4"])
    monkeypatch.setattr(runner, "load_plan", lambda: pytest.fail("later jobs entered after failed scan"))
    with pytest.raises(ValueError, match="not selectable"):
        runner.main()


def test_one_rejects_changed_frozen_weight_before_model_construction(monkeypatch):
    assignment = dict(track_id="track", track_index=0, receiver_id="rx0",
                      rf_hz=11.2e9, norad=1, confidence=0.99, unambiguous=True)
    job = dict(index=4, family="iid_t4_scale100", norad=1, cache=None)
    plan = dict(jobs=[job], scans=[dict(index=4, assignments=[{
        **assignment, "source_receiver_equal_weight": 0.25}])])
    monkeypatch.setattr(runner, "load_plan", lambda: plan)
    pilot = SimpleNamespace(HILL=Path("/unused"),
        fast=SimpleNamespace(baseline=SimpleNamespace(), profile=None),
        eligible_groups=lambda _: {1: ["track"]},
        retained_fold=lambda *a: pytest.fail("changed weights reached model subset"))
    diagnose = SimpleNamespace(FAMILIES={"iid_t4_scale100": {}},
        load_endpoint=lambda *a: (None, None, None, [0, 0, 0], None, None))
    source = SimpleNamespace(freeze_assignments=lambda *a: [assignment],
                             derive_weights=lambda *a: [0.5])
    context = SimpleNamespace(load_scan=lambda _: (
        None, {"config": {}}, {"session_id": "scan"}, [], None, {}))
    modules = {"ds11_atomic_pilot": pilot, "ds11_atomic_diagnose": diagnose,
               "ds11_atomic_exact": object(), "ds11_screen_input_context": context,
               "ds11_atomic_source": source, "ds11_atomic_robust": object()}
    monkeypatch.setattr(runner, "module", lambda name, path: modules[name])
    with pytest.raises(ValueError, match="frozen assignments or source weights"):
        runner.one(runner.job_key(job))
