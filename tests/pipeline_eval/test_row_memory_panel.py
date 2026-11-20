import gzip
import json

import pytest

from tools.pipeline_eval import corpus
from tools.pipeline_eval.qualification import row_memory_panel as panel
from tools.pipeline_eval.qualification import row_memory_replay as trial
from tools.pipeline_eval.scoring import ARMS


def test_oom_terminal_is_not_a_retry_when_live_optional_controller_was_missing():
    log = """Running as unit: one.service; invocation ID: x
stage: enter signed_context
Finished with result: oom-kill
CPU time consumed: 1min 10.325s
Service runtime: 1min 13.5s
Memory peak: 512M (swap: 0B)
"""
    row = dict(
        id="case",
        unit="one",
        result=dict(status="unavailable"),
        snapshots=[],
        preserved_worker_log=log,
        worker_log_sha256=corpus._sha(log.encode()),
    )
    observed = panel.terminal_evidence(row)
    assert observed["result"] == "oom-kill"
    assert observed["last_stage"] == "enter signed_context"
    assert observed["cpu_s"] == pytest.approx(70.325)
    assert observed["runtime_s"] == 73.5
    assert not panel.precedes_retry(row, observed)
    with pytest.raises(ValueError, match="differs from the original attempt"):
        panel.terminal_evidence(dict(row, preserved_worker_log=log + "changed"))


def test_live_kernel_limits_and_single_thread_are_checked():
    snapshot = {
        "pid": 91,
        "cgroup": "/parent/job.service",
        "affinity": [20],
        "nice": 10,
        "memory.max": str(trial.MEMORY),
        "memory.peak": str(trial.MEMORY),
        "memory.swap.max": "0",
        "memory.swap.current": "0",
        "memory.events": "oom 0\noom_kill 0",
        "cpu.stat": "usage_usec 2500000",
        "io.stat": None,
        "process": {"Threads": "1"},
        "process_io": {"read_bytes": 973},
        "observed_ns": 11,
    }
    verified = panel.audit_snapshots([snapshot], "job", 20)
    assert verified["cgroup_peak_bytes"] == trial.MEMORY
    assert verified["cpu_sample_s"] == 2.5
    assert verified["process_io_sample"]["read_bytes"] == 973
    with pytest.raises(ValueError, match="memory.swap.max"):
        panel.audit_snapshots([dict(snapshot, **{"memory.swap.max": "max"})], "job", 20)


def test_published_failure_panel_rescores_identically_without_solver(tmp_path):
    folder = trial.REPORT
    attempts = list(
        map(json.loads, gzip.decompress((folder / panel.ATTEMPTS).read_bytes()).splitlines())
    )
    panel.publish(folder / "source-lock.json", attempts, tmp_path)
    assert (tmp_path / "prediction-lock.json").read_bytes() == (
        folder / "prediction-lock.json"
    ).read_bytes()
    assert (tmp_path / "scores.csv").read_bytes() == (folder / "scores.csv").read_bytes()
    rows = panel.read_predictions(tmp_path / panel.CAPTURE)
    assert set(rows) == set(trial.CASES.values())
    for row in rows.values():
        assert row["result"]["status"] == "failed"
        assert row["result"]["reason"] == "oom-kill"
        assert all(row["result"]["arms"][arm]["latlon"] is None for arm in ARMS)
