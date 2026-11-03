import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("ds11_atomic_tests", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_plan_rejects_stale_dependencies_and_duplicate_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HERE", tmp_path)
    dependency = tmp_path / "dependency"
    dependency.write_text("frozen")
    job = dict(index=0, family="robust_t8_scale100", norad=1, cache=None)
    plan = dict(schema="ds11-source-loo-atomic-plan/v1", jobs=[job],
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
    for name in ("run.py", "plan.json", "PLAN_PROTOCOL.md"):
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
