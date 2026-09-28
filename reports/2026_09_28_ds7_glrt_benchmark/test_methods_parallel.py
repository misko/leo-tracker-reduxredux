from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

from leo.scanner import ScannerConfiguration, current_low_band_targets
from leo.scanner.detector import DwellGlrt64Analysis, Glrt64ProbeResponse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location(
    "ds7_benchmark_methods_parallel",
    HERE / "methods_parallel.py",
)
assert SPEC is not None and SPEC.loader is not None
parallel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = parallel
SPEC.loader.exec_module(parallel)


class _Future:
    def result(self, timeout):
        assert timeout == 30


class _Pool:
    def __init__(self):
        self._processes = {
            10 + index: _Process(10 + index) for index in range(4)
        }
        self.shutdown_calls = []

    def submit(self, function, value):
        assert function is parallel.time.sleep
        assert value == 0.05
        return _Future()

    def shutdown(self, *, wait, cancel_futures):
        self.shutdown_calls.append((wait, cancel_futures))


class _Process:
    def __init__(self, pid):
        self.pid = pid
        self.alive = True
        self.terminated = False
        self.killed = False
        self.joins = []

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated = True
        self.alive = False

    def kill(self):
        self.killed = True
        self.alive = False

    def join(self, timeout):
        self.joins.append(timeout)


class _Queue:
    def __init__(self):
        self.cancelled = False
        self.closed = False

    def cancel_join_thread(self):
        self.cancelled = True

    def close(self):
        self.closed = True


class _Scanner:
    def __init__(self, cores):
        assert tuple(cores) == parallel.CORES
        self.pool = _Pool()
        self.queue = _Queue()
        self.closed = False
        self.runs = []

    def run(self, values, configuration, *, edge):
        self.runs.append((values, configuration, edge))
        responses = tuple(
            Glrt64ProbeResponse(receiver_id, index, index * 10, ())
            for index in range(configuration.scheduled_probe_count)
            for receiver_id in configuration.receiver_ids
        )
        return DwellGlrt64Analysis(None, None, None, "synthetic", responses), 123.0

    def close(self):
        self.closed = True


def test_four_worker_method_reports_separate_wall_and_cpu(monkeypatch) -> None:
    monkeypatch.setattr(parallel._adapter, "ParallelScanner", _Scanner)
    monkeypatch.setattr(
        parallel.os,
        "sched_getaffinity",
        lambda pid: {pid - 10} if pid else set(range(8)),
    )
    method = parallel.make_parallel_method()
    ticks = iter((1_000, 1_040))
    monkeypatch.setattr(method, "_worker_ticks", lambda: next(ticks))
    configuration = ScannerConfiguration(
        dwell_ms=20,
        receiver_ids=(0, 1),
        targets=current_low_band_targets()[:1],
    )
    iq = np.zeros((configuration.dwell_samples, 2), dtype=np.complex64)
    context = {
        "session_id": "s",
        "visit_index": 2,
        "sample_start_counter": 100,
        "rate_hz": configuration.sample_rate_hz,
        "target_index": 0,
    }

    result = method.analyze(iq, configuration, "lower", context)

    assert result.analysis.reason == "synthetic"
    assert result.diagnostics["resource_cpu_count"] == 4
    assert result.diagnostics["cores"] == [0, 1, 2, 3]
    assert result.diagnostics["worker_cpu_s"] == 0.4
    assert result.diagnostics["worker_detector_cpu_s"] == 0.123
    assert result.diagnostics["aggregate_cpu_s"] >= 0.4
    assert result.diagnostics["probe_response_count"] == 2
    assert method.creation_diagnostics["worker_affinities"] == {
        "10": [0],
        "11": [1],
        "12": [2],
        "13": [3],
    }
    assert all(__import__("os").environ[name] == "1" for name in parallel.THREAD_ENVIRONMENT)

    method.close()
    method.close()
    assert method._scanner.closed is True


def test_frozen_adapter_hash_and_closed_method_guard(monkeypatch) -> None:
    digest = parallel.hashlib.sha256(parallel.ADAPTER_PATH.read_bytes()).hexdigest()
    assert digest == parallel.ADAPTER_SHA256
    monkeypatch.setattr(parallel._adapter, "ParallelScanner", _Scanner)
    monkeypatch.setattr(
        parallel.os,
        "sched_getaffinity",
        lambda pid: {pid - 10} if pid else set(range(8)),
    )
    method = parallel.make_parallel_method()
    method.close()
    configuration = ScannerConfiguration(
        dwell_ms=20,
        receiver_ids=(0,),
        targets=current_low_band_targets()[:1],
    )
    iq = np.zeros((configuration.dwell_samples, 1), dtype=np.complex64)
    context = {
        "session_id": "s",
        "visit_index": 0,
        "sample_start_counter": 0,
        "rate_hz": configuration.sample_rate_hz,
        "target_index": 0,
    }
    try:
        method.analyze(iq, configuration, "lower", context)
    except RuntimeError as error:
        assert "closed" in str(error)
    else:
        raise AssertionError("closed method accepted analysis")


def test_abort_terminates_only_owned_workers_and_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(parallel._adapter, "ParallelScanner", _Scanner)
    monkeypatch.setattr(
        parallel.os,
        "sched_getaffinity",
        lambda pid: {pid - 10} if pid else set(range(8)),
    )
    method = parallel.make_parallel_method()
    owned = method._processes

    method.abort()
    method.abort()

    assert all(process.terminated for process in owned)
    assert all(not process.killed for process in owned)
    assert method._scanner.pool.shutdown_calls == [(False, True)]
    assert method._scanner.queue.cancelled is True
    assert method._scanner.queue.closed is True
