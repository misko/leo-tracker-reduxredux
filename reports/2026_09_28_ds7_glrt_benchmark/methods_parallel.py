"""Four-core complete-window parallel method for the DS7 benchmark."""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ADAPTER_ROOT = HERE.parent / "2026_09_27_ds5_cached_tracking" / "application_parallel"
ADAPTER_PATH = ADAPTER_ROOT / "parallel_scanner.py"
ADAPTER_SHA256 = "5ca243da1e11e8d5654272d8529242266072a5e37d99af3d5444255eb1f637ff"
CORES = (0, 1, 2, 3)
THREAD_ENVIRONMENT = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from methods import MethodRun  # noqa: E402


def _load_adapter():
    if hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest() != ADAPTER_SHA256:
        raise RuntimeError("frozen parallel scanner adapter changed")
    if str(ADAPTER_ROOT) not in sys.path:
        sys.path.insert(0, str(ADAPTER_ROOT))
    module = importlib.import_module("parallel_scanner")
    if Path(module.__file__).resolve() != ADAPTER_PATH.resolve():
        raise RuntimeError("parallel_scanner resolved outside the frozen adapter")
    return module


_adapter = _load_adapter()


class ParallelBenchmarkMethod:
    name = "parallel4"

    def __init__(self) -> None:
        available = os.sched_getaffinity(0)
        if not set(CORES) <= available:
            raise RuntimeError(
                f"parallel method requires cores {CORES}, available={sorted(available)}"
            )
        for name in THREAD_ENVIRONMENT:
            os.environ[name] = "1"
        wall_started = time.perf_counter_ns()
        cpu_started = time.process_time_ns()
        self._scanner = _adapter.ParallelScanner(CORES)
        # ProcessPoolExecutor starts lazily. Force all four persistent workers
        # into existence so pool creation remains outside every analyzed dwell.
        readiness_started = time.perf_counter_ns()
        futures = [self._scanner.pool.submit(time.sleep, 0.05) for _ in CORES]
        for future in futures:
            future.result(timeout=30)
        processes = tuple(self._scanner.pool._processes.values())
        if len(processes) != len(CORES):
            self._scanner.close()
            raise RuntimeError("parallel method did not create four persistent workers")
        affinity_deadline = time.monotonic() + 30.0
        while True:
            worker_affinities = {
                process.pid: tuple(sorted(os.sched_getaffinity(process.pid)))
                for process in processes
            }
            pinned_cores = sorted(
                value[0] for value in worker_affinities.values() if len(value) == 1
            )
            if pinned_cores == list(CORES):
                break
            if time.monotonic() >= affinity_deadline:
                self.abort()
                raise RuntimeError(f"parallel worker affinity mismatch: {worker_affinities}")
            time.sleep(0.01)
        self._closed = False
        self._processes = processes
        self.creation_diagnostics: dict[str, object] = {
            "pool_creation_wall_s": (time.perf_counter_ns() - wall_started) / 1e9,
            "pool_creation_parent_cpu_s": (time.process_time_ns() - cpu_started) / 1e9,
            "worker_readiness_wall_s": (time.perf_counter_ns() - readiness_started) / 1e9,
            "worker_pids": sorted(worker_affinities),
            "worker_affinities": {
                str(pid): list(affinity) for pid, affinity in worker_affinities.items()
            },
            "cores": list(CORES),
            "numerical_threads": 1,
        }

    def reset(self) -> None:
        return None

    def analyze(
        self,
        iq_complex: np.ndarray,
        configuration,
        edge: object,
        context: Mapping[str, object],
    ) -> MethodRun:
        if self._closed:
            raise RuntimeError("parallel method is closed")
        values = np.asarray(iq_complex)
        expected = (configuration.dwell_samples, len(configuration.receiver_ids))
        if values.ndim != 2 or values.shape != expected or not np.iscomplexobj(values):
            raise ValueError(f"iq_complex must be a complex scanner dwell with shape {expected}")
        required = ("session_id", "visit_index", "sample_start_counter", "rate_hz", "target_index")
        missing = [name for name in required if name not in context]
        if missing:
            raise ValueError(f"method context is missing: {', '.join(missing)}")
        if context["rate_hz"] != configuration.sample_rate_hz:
            raise ValueError("context rate_hz differs from scanner configuration")

        worker_ticks_before = self._worker_ticks()
        parent_cpu_started = time.process_time_ns()
        wall_started = time.perf_counter_ns()
        analysis, worker_detector_cpu_ms = self._scanner.run(
            values,
            configuration,
            edge=edge,
        )
        wall_s = (time.perf_counter_ns() - wall_started) / 1e9
        parent_cpu_s = (time.process_time_ns() - parent_cpu_started) / 1e9
        worker_ticks_after = self._worker_ticks()
        worker_cpu_s = (worker_ticks_after - worker_ticks_before) / os.sysconf("SC_CLK_TCK")
        diagnostics: dict[str, object] = {
            "method": self.name,
            "route": "complete_window_parallel",
            "approximate": False,
            "resource_cpu_count": len(CORES),
            "cores": list(CORES),
            "numerical_threads": 1,
            "wall_s": wall_s,
            "parent_cpu_s": parent_cpu_s,
            "worker_cpu_s": worker_cpu_s,
            "aggregate_cpu_s": parent_cpu_s + worker_cpu_s,
            "worker_detector_cpu_s": worker_detector_cpu_ms / 1_000.0,
            "worker_cpu_resolution_s": 1.0 / os.sysconf("SC_CLK_TCK"),
            "probe_response_count": len(analysis.probes),
            "candidate_response_count": sum(len(probe.candidates) for probe in analysis.probes),
            "decision_confirmed": analysis.first is not None,
            "session_id": context["session_id"],
            "visit_index": context["visit_index"],
            "sample_start_counter": context["sample_start_counter"],
            "rate_hz": context["rate_hz"],
            "target_index": context["target_index"],
        }
        return MethodRun(analysis=analysis, diagnostics=diagnostics)

    def _worker_ticks(self) -> int:
        ticks = 0
        for process in self._processes:
            fields = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()
            ticks += int(fields[11]) + int(fields[12])
        return ticks

    def abort(self) -> None:
        """Boundedly stop only this method's workers after a deadline or error."""

        if getattr(self, "_closed", False):
            return
        self._closed = True
        processes = tuple(getattr(self, "_processes", ()))
        for process in processes:
            if process.is_alive():
                process.terminate()
        join_deadline = time.monotonic() + 1.0
        for process in processes:
            process.join(timeout=max(0.0, join_deadline - time.monotonic()))
        for process in processes:
            if process.is_alive():
                process.kill()
        for process in processes:
            process.join(timeout=0.25)
        self._scanner.pool.shutdown(wait=False, cancel_futures=True)
        self._scanner.queue.cancel_join_thread()
        self._scanner.queue.close()

    def close(self) -> None:
        if not self._closed:
            self._scanner.close()
            self._closed = True

    def __enter__(self) -> ParallelBenchmarkMethod:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def make_parallel_method() -> ParallelBenchmarkMethod:
    return ParallelBenchmarkMethod()


__all__ = ["ParallelBenchmarkMethod", "make_parallel_method"]
