import signal
import subprocess
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from leo.application.automatic_shared_model import execute, pending, process
from leo.cli.watch_shared_fast_position import tick
from tests.storage.test_shared_fast_scan import source, terminal


def test_success_no_retry_and_corrupted_input_failure(tmp_path):
    _, store, job = source(tmp_path)
    calls = []
    def runner(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        terminal(store, job)
        return 0
    result = process(job, store=store, command=["python", "-m", "model"], runner=runner)
    assert result["state"] == "complete" and calls[0][1] == 1215
    assert calls[0][0][-2:] == ["--maximum-seconds", "1200"]
    repeated = process(job, store=store, command=["python"], runner=runner)
    assert repeated == store.status(job["job_id"])
    assert len(calls) == 1 and pending(store) is None


@pytest.mark.parametrize("mode", ["exception", "nonzero", "missing", "invalid"])
def test_failure_persistent_no_retry(tmp_path, mode):
    _, store, job = source(tmp_path)
    def runner(*args, **kwargs):
        if mode == "exception":
            raise subprocess.TimeoutExpired("model", 1)
        if mode == "invalid":
            terminal(store, job, selection=None)
        return 1 if mode == "nonzero" else 0
    errors = {"exception": subprocess.TimeoutExpired, "nonzero": RuntimeError,
              "missing": FileNotFoundError, "invalid": ValueError}
    with pytest.raises(errors[mode]):
        process(job, store=store, command=["python"], runner=runner)
    assert store.detail(job["job_id"])["state"] == "failed"
    assert pending(store) is None


def test_interrupted_and_launch_without_status_never_retried(tmp_path):
    _, store, job = source(tmp_path)
    store.launch(job)
    (store.workspace(job["job_id"])/"status.json").unlink()
    result = process(job, store=store, command=["python"],
                     runner=lambda *a, **k: pytest.fail("orphan must not retry"))
    assert result["state"] == "failed" and "Interrupted" in result["failure"]


def test_owner_exclusion_and_one_pending_submission(tmp_path):
    _, store, job = source(tmp_path)
    with store.owner(job["job_id"]):
        assert process(job, store=store, command=["python"]) is None
    class Pool:
        calls = []
        def submit(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return Future()
    pool, active = Pool(), {}
    tick(store, pool, active, command=["python"], maximum_seconds=1200)
    tick(store, pool, active, command=["python"], maximum_seconds=1200)
    assert len(pool.calls) == len(active) == 1


def test_timeout_terminates_and_kills_group_even_when_leader_exits(monkeypatch, tmp_path):
    import leo.application.automatic_shared_model as module
    calls = []
    class Process:
        pid = 123
        waits = 0
        def wait(self, timeout=None):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("model", timeout)
            return 0
    def popen(*args, **kwargs):
        assert kwargs["start_new_session"] and kwargs["env"]["OMP_NUM_THREADS"] == "1"
        return Process()
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(module.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    with (tmp_path/"log").open("ab") as log, pytest.raises(subprocess.TimeoutExpired):
        execute(["python"], log=log, timeout=1)
    assert calls == [(123, signal.SIGTERM), (123, signal.SIGKILL)]


def test_disappearing_export_visible_without_restarting_watcher(monkeypatch, tmp_path, capsys):
    import leo.cli.watch_shared_fast_position as watcher
    class Stop(Exception):
        pass
    def disappeared(*args, **kwargs):
        raise FileNotFoundError("export vanished")
    def stop_after_tick(seconds):
        assert seconds == 5
        raise Stop
    monkeypatch.setattr(watcher, "tick", disappeared)
    monkeypatch.setattr(watcher.time, "sleep", stop_after_tick)
    with pytest.raises(Stop):
        watcher.watch(SimpleNamespace(bulk_root=tmp_path, model_version="shared-scan-q-v1",
                                     shared_python="unused", maximum_seconds=1200))
    assert "shared_discovery_failure" in capsys.readouterr().out


@pytest.mark.parametrize("budget", [1201, 0, float("nan"), float("inf")])
def test_unsupported_budget_never_launches(tmp_path, budget):
    _, store, job = source(tmp_path)
    with pytest.raises(ValueError, match="bounded budget"):
        process(job, store=store, command=["unused"], maximum_seconds=budget)
    assert not store.launched(job["job_id"]) and store.status(job["job_id"]) is None
