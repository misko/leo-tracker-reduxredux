#!/usr/bin/env python3
"""Bounded P-core server concurrency benchmark for stateless blind evaluation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pickle
import queue
import signal
import statistics
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DATASET = REPORT / "new_data"
NATIVE = REPORT / "native"
BASELINE = NATIVE / "libblind_strided_v4.so"
CANDIDATE = REPORT / "fft32" / "libfft32_fftw.so"
RUNTIME_FFTW = Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3.6.10")
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
PCORES = tuple(range(8))
sys.path[:0] = [str(REPORT), str(NATIVE), str(DEPLOY), str(DEPLOY / "src")]

from blind_strided_v4 import NativeStridedBlindV4  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import Observation, reference_match  # noqa: E402


def load_acquisition():
    path = REPORT / "acquisition" / "run_acquisition.py"
    spec = importlib.util.spec_from_file_location("server_parallel_acquisition", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen acquisition helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ACQUISITION = load_acquisition()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def host_metadata() -> dict[str, str]:
    return dict(
        zip(
            ("sysname", "nodename", "release", "version", "machine"),
            os.uname(),
            strict=True,
        )
    )


def verify_source_lock() -> dict:
    lock = load_json(HERE / "source_lock.json")
    paths = {
        "design": HERE / "design.json",
        "runner": Path(__file__),
        "dataset": DATASET / "cases.json",
        "baseline_library": BASELINE,
        "baseline_receipt": BASELINE.with_name(BASELINE.name + ".build.json"),
        "candidate_library": CANDIDATE,
        "candidate_receipt": CANDIDATE.with_name(CANDIDATE.name + ".build.json"),
        "runtime_fftw": RUNTIME_FFTW,
        "native_wrapper": NATIVE / "blind_strided_v4.py",
        "native_c": NATIVE / "blind_strided_v4.c",
        "native_header": NATIVE / "blind_strided_v4.h",
        "native_profile": NATIVE / "profile.json",
        "tracking": REPORT / "tracking.py",
        "acquisition_helper": REPORT / "acquisition" / "run_acquisition.py",
    }
    actual = {name: digest(path) for name, path in paths.items()}
    if lock.get("files") != actual:
        raise ValueError("server-parallel frozen input changed")
    return lock


def select_cases(payload: dict) -> list[dict]:
    cases = sorted(
        (case for case in payload["cases"] if case["split"] == "dev"),
        key=lambda case: (case["rate_hz"], case["session_id"], case["visit_index"]),
    )
    if len(cases) != 128 or {case["rate_hz"] for case in cases} != {2_500_000, 5_000_000}:
        raise ValueError("expected 128 physical visits at both native rates")
    return cases


def preload(cases: list[dict]) -> tuple[list[np.ndarray], list[dict]]:
    arrays, receipts = [], []
    for case in cases:
        path = (DATASET / case["raw_npy"]["path"]).resolve()
        if not path.is_relative_to(DATASET.resolve()):
            raise ValueError("IQ path escapes dataset")
        file_hash = digest(path)
        if file_hash != case["raw_npy"]["sha256"]:
            raise ValueError(f"IQ hash mismatch: {case['case_id']}")
        values = np.load(path, mmap_mode="r", allow_pickle=False)
        expected = (case["rate_hz"] * 120 // 1000, 2, 2)
        if values.dtype != np.dtype("<i2") or values.shape != expected:
            raise ValueError(f"IQ geometry mismatch: {case['case_id']}")
        memory_hash = "sha256:" + hashlib.sha256(values).hexdigest()
        arrays.append(values)
        receipts.append(
            {
                "case_id": case["case_id"],
                "file_sha256": file_hash,
                "memory_sha256": memory_hash,
            }
        )
    return arrays, receipts


def science_record(result) -> dict:
    signature = ACQUISITION.scientific_signature(result)
    signature_sha256 = "sha256:" + hashlib.sha256(
        pickle.dumps(signature, protocol=5)
    ).hexdigest()
    compact = ACQUISITION.compact_result(result)
    for field in (
        "native_total_cpu_ms",
        "native_total_wall_ms",
        "rank_cpu_ms",
        "confirmation_cpu_ms",
    ):
        compact.pop(field)
    return {"signature_sha256": signature_sha256, "science": compact}


def timed_task(engine, values: np.ndarray, rx: int) -> dict:
    thread_started = time.thread_time_ns()
    wall_started = time.perf_counter_ns()
    receiver_view = values[:, rx, :]
    result = engine.run(receiver_view, maximum=1, seeded=False)
    record = science_record(result)
    record["task_thread_cpu_ms"] = (time.thread_time_ns() - thread_started) / 1e6
    record["task_wall_ms"] = (time.perf_counter_ns() - wall_started) / 1e6
    return record


class EngineSet:
    def __init__(self, factory, assignments: list[set[tuple[int, str]]]):
        self.engines: list[dict[tuple[int, str], object]] = []
        for geometries in assignments:
            self.engines.append({geometry: factory(*geometry) for geometry in sorted(geometries)})

    def prewarm(self, cases: list[dict], arrays: list[np.ndarray]) -> None:
        samples = {}
        for index, case in enumerate(cases):
            samples.setdefault((case["rate_hz"], case["edge"]), arrays[index][:, 0, :])
        for worker in self.engines:
            for geometry, engine in worker.items():
                engine.run(samples[geometry], maximum=1, seeded=False)

    def close(self) -> None:
        for worker in self.engines:
            for engine in worker.values():
                engine.close()


class DedicatedPool:
    def __init__(
        self,
        name: str,
        engine_set: EngineSet,
        cases: list[dict],
        arrays: list[np.ndarray],
        cpus: list[int],
    ):
        self.name = name
        self.engine_set = engine_set
        self.cases = cases
        self.arrays = arrays
        self.queues = [queue.Queue() for _ in cpus]
        self.results: queue.Queue = queue.Queue()
        self.threads = []
        for worker, cpu in enumerate(cpus):
            thread = threading.Thread(
                target=self._worker, args=(worker, cpu), name=f"{name}-{worker}", daemon=False
            )
            thread.start()
            self.threads.append(thread)
        ready = [self.results.get() for _ in cpus]
        if any(item[0] != "ready" for item in ready):
            raise RuntimeError("parallel worker failed during startup")
        self.affinity = {
            int(item[1]): {"assigned_cpu": int(item[2]), "observed": item[3]}
            for item in ready
        }

    def _worker(self, worker: int, cpu: int) -> None:
        os.sched_setaffinity(0, {cpu})
        self.results.put(("ready", worker, cpu, sorted(os.sched_getaffinity(0))))
        while True:
            command = self.queues[worker].get()
            if command is None:
                return
            sequence, case_index, rx = command
            try:
                case = self.cases[case_index]
                geometry = (case["rate_hz"], case["edge"])
                record = timed_task(
                    self.engine_set.engines[worker][geometry], self.arrays[case_index], rx
                )
                self.results.put(("result", sequence, case_index, rx, worker, record))
            except BaseException as error:  # propagate to the main benchmark thread
                self.results.put(("error", sequence, case_index, rx, worker, repr(error)))

    def dispatch(self, assignments: list[tuple[int, int, int]]) -> list[dict]:
        process_started = time.process_time_ns()
        wall_started = time.perf_counter_ns()
        for sequence, (worker, case_index, rx) in enumerate(assignments):
            self.queues[worker].put((sequence, case_index, rx))
        output = []
        for _ in assignments:
            item = self.results.get()
            if item[0] == "error":
                raise RuntimeError(f"worker task failed: {item}")
            _, sequence, case_index, rx, worker, record = item
            output.append(
                {"sequence": sequence, "case_index": case_index, "rx": rx, "worker": worker, **record}
            )
        wall_ms = (time.perf_counter_ns() - wall_started) / 1e6
        process_cpu_ms = (time.process_time_ns() - process_started) / 1e6
        output.sort(key=lambda item: item["sequence"])
        return output, wall_ms, process_cpu_ms

    def close_threads(self) -> None:
        for work_queue in self.queues:
            work_queue.put(None)
        for thread in self.threads:
            thread.join()
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError("parallel worker did not stop")


def geometry_assignments(cases: list[dict], workers: int) -> list[set[tuple[int, str]]]:
    geometries = sorted({(case["rate_hz"], case["edge"]) for case in cases})
    assignments = [set() for _ in range(workers)]
    if workers <= 4:
        for index, geometry in enumerate(geometries):
            assignments[index % workers].add(geometry)
    else:
        if workers != 8:
            raise ValueError("unsupported worker count")
        for index, geometry in enumerate(geometries):
            assignments[2 * index].add(geometry)
            assignments[2 * index + 1].add(geometry)
    return assignments


def batch_owner(cases: list[dict], workers: int, case_index: int, rx: int) -> int:
    geometries = sorted({(case["rate_hz"], case["edge"]) for case in cases})
    geometry_index = geometries.index((cases[case_index]["rate_hz"], cases[case_index]["edge"]))
    if workers <= 4:
        return geometry_index % workers
    return 2 * geometry_index + ((case_index + rx) % 2)


def task_order(case_order: list[int]) -> list[tuple[int, int]]:
    return [(case_index, rx) for case_index in case_order for rx in (0, 1)]


def run_direct(
    engines: EngineSet,
    cases: list[dict],
    arrays: list[np.ndarray],
    case_order: list[int],
) -> dict:
    records, pair_wall, pair_cpu = [], [], []
    process_started = time.process_time_ns()
    wall_started = time.perf_counter_ns()
    for case_index in case_order:
        pair_process_started = time.process_time_ns()
        pair_wall_started = time.perf_counter_ns()
        geometry = (cases[case_index]["rate_hz"], cases[case_index]["edge"])
        for rx in (0, 1):
            records.append(
                {
                    "case_index": case_index,
                    "rx": rx,
                    "worker": None,
                    **timed_task(engines.engines[0][geometry], arrays[case_index], rx),
                }
            )
        pair_wall.append((time.perf_counter_ns() - pair_wall_started) / 1e6)
        pair_cpu.append((time.process_time_ns() - pair_process_started) / 1e6)
    return {
        "records": records,
        "batch_wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
        "aggregate_process_cpu_ms": (time.process_time_ns() - process_started) / 1e6,
        "pair_wall_ms": pair_wall,
        "pair_process_cpu_ms": pair_cpu,
    }


def run_pair_pool(pool: DedicatedPool, case_order: list[int]) -> dict:
    records, pair_wall, pair_cpu = [], [], []
    process_started = time.process_time_ns()
    wall_started = time.perf_counter_ns()
    for case_index in case_order:
        pair_process_started = time.process_time_ns()
        pair_wall_started = time.perf_counter_ns()
        output, _, _ = pool.dispatch([(0, case_index, 0), (1, case_index, 1)])
        records.extend(output)
        pair_wall.append((time.perf_counter_ns() - pair_wall_started) / 1e6)
        pair_cpu.append((time.process_time_ns() - pair_process_started) / 1e6)
    return {
        "records": records,
        "batch_wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
        "aggregate_process_cpu_ms": (time.process_time_ns() - process_started) / 1e6,
        "pair_wall_ms": pair_wall,
        "pair_process_cpu_ms": pair_cpu,
    }


def run_batch_pool(
    pool: DedicatedPool, cases: list[dict], workers: int, case_order: list[int]
) -> dict:
    assignments = [
        (batch_owner(cases, workers, case_index, rx), case_index, rx)
        for case_index, rx in task_order(case_order)
    ]
    records, wall_ms, process_cpu_ms = pool.dispatch(assignments)
    return {
        "records": records,
        "batch_wall_ms": wall_ms,
        "aggregate_process_cpu_ms": process_cpu_ms,
        "pair_wall_ms": [],
        "pair_process_cpu_ms": [],
    }


def finish_measurement(value: dict) -> dict:
    records = value.pop("records")
    value["summed_task_thread_cpu_ms"] = sum(
        record["task_thread_cpu_ms"] for record in records
    )
    value["summed_task_wall_ms"] = sum(record["task_wall_ms"] for record in records)
    value["receiver_visits_per_second"] = 256 / (value["batch_wall_ms"] / 1000)
    value["science_batch_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            sorted(
                (record["case_index"], record["rx"], record["signature_sha256"])
                for record in records
            ),
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return value, records


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values), q, method="linear"))


def summarize_mode(measurements: list[dict], baseline_wall_ms: float, baseline_cpu_ms: float) -> dict:
    wall = [value["batch_wall_ms"] for value in measurements]
    cpu = [value["aggregate_process_cpu_ms"] for value in measurements]
    task_cpu = [value["summed_task_thread_cpu_ms"] for value in measurements]
    latencies = [
        item for value in measurements for item in value["task_latency_ms"]
    ]
    pair_wall = [item for value in measurements for item in value["pair_wall_ms"]]
    pair_cpu = [
        item for value in measurements for item in value["pair_process_cpu_ms"]
    ]
    median_wall = statistics.median(wall)
    median_cpu = statistics.median(cpu)
    result = {
        "repetitions": len(measurements),
        "batch_wall_ms": {"values": wall, "median": median_wall},
        "aggregate_process_cpu_ms": {"values": cpu, "median": median_cpu},
        "summed_task_thread_cpu_ms": {
            "values": task_cpu,
            "median": statistics.median(task_cpu),
        },
        "receiver_visits_per_second": 256 / (median_wall / 1000),
        "batch_wall_speedup_vs_packed_fp64_serial": baseline_wall_ms / median_wall,
        "aggregate_cpu_ratio_vs_packed_fp64_serial": median_cpu / baseline_cpu_ms,
        "task_latency_ms": {
            "median": statistics.median(latencies),
            "p95": percentile(latencies, 95),
        },
        "science_batch_sha256": [value["science_batch_sha256"] for value in measurements],
    }
    if pair_wall:
        result["physical_visit_pair_wall_ms"] = {
            "samples": len(pair_wall),
            "median": statistics.median(pair_wall),
            "p95": percentile(pair_wall, 95),
        }
        result["physical_visit_pair_process_cpu_ms"] = {
            "samples": len(pair_cpu),
            "median": statistics.median(pair_cpu),
            "p95": percentile(pair_cpu, 95),
        }
    return result


def observation(compact: dict) -> Observation | None:
    value = compact["observation"]
    return Observation(**value) if value is not None else None


def reference_summary(reference: dict, candidate: dict, cases: list[dict]) -> dict:
    rows = []
    for case_index, case in enumerate(cases):
        for rx in (0, 1):
            key = (case_index, rx)
            ref = reference[key]["science"]
            cand = candidate[key]["science"]
            ref_observation = observation(ref)
            cand_observation = observation(cand)
            matched = bool(
                ref_observation
                and cand_observation
                and reference_match(ref_observation, cand_observation, case["rate_hz"])
            )
            rows.append(
                {
                    "case_id": case["case_id"],
                    "rx": rx,
                    "rate_hz": case["rate_hz"],
                    "reference_positive": ref["positive"],
                    "candidate_positive": cand["positive"],
                    "matched_reference": matched,
                    "selected_window_changed": ref["selected_window"] != cand["selected_window"],
                    "rank_order_changed": ref["rank_order"] != cand["rank_order"],
                    "projected_epochs_changed": (
                        ref["projected_epoch_samples"] != cand["projected_epoch_samples"]
                    ),
                }
            )
    positives = [row for row in rows if row["reference_positive"]]
    extras = [row for row in rows if row["candidate_positive"] and not row["matched_reference"]]
    lost = [row for row in positives if not row["matched_reference"]]
    return {
        "receiver_visits": len(rows),
        "reference_positive": len(positives),
        "candidate_positive": sum(row["candidate_positive"] for row in rows),
        "matched_reference_positive": sum(row["matched_reference"] for row in rows),
        "lost_reference_positive": len(lost),
        "additional_candidate_positive": len(extras),
        "selected_window_changes": sum(row["selected_window_changed"] for row in rows),
        "rank_order_changes": sum(row["rank_order_changed"] for row in rows),
        "projected_epoch_array_changes": sum(
            row["projected_epochs_changed"] for row in rows
        ),
        "gate_pass": not lost and not extras,
    }


def run() -> dict:
    signal.alarm(120)
    lock = verify_source_lock()
    cases = select_cases(load_json(DATASET / "cases.json"))
    arrays, preload_receipts = preload(cases)
    original_affinity = sorted(os.sched_getaffinity(0))
    if not set(PCORES).issubset(original_affinity):
        raise ValueError("required P-core affinity is unavailable")
    os.sched_setaffinity(0, {0})

    geometries = {geometry for geometry in ((c["rate_hz"], c["edge"]) for c in cases)}
    direct_assignment = [set(geometries)]
    pair_assignment = [set(geometries), set(geometries)]
    pools: dict[str, DedicatedPool] = {}
    engine_sets: list[EngineSet] = []
    try:
        baseline_engines = EngineSet(
            lambda rate, edge: NativeDwell(BASELINE, rate, edge, 512), direct_assignment
        )
        fp32_serial_engines = EngineSet(
            lambda rate, edge: NativeStridedBlindV4(rate, edge, library=CANDIDATE, bins=512),
            direct_assignment,
        )
        pair_engines = EngineSet(
            lambda rate, edge: NativeStridedBlindV4(rate, edge, library=CANDIDATE, bins=512),
            pair_assignment,
        )
        engine_sets.extend((baseline_engines, fp32_serial_engines, pair_engines))
        batch_engine_sets = {}
        for workers in (1, 2, 4, 8):
            engines = EngineSet(
                lambda rate, edge: NativeStridedBlindV4(
                    rate, edge, library=CANDIDATE, bins=512
                ),
                geometry_assignments(cases, workers),
            )
            engine_sets.append(engines)
            batch_engine_sets[workers] = engines

        # All possible lazy planning is forced serially on the main thread.
        for engines in engine_sets:
            engines.prewarm(cases, arrays)

        pools["fp32_parallel_pair"] = DedicatedPool(
            "fp32-pair", pair_engines, cases, arrays, [0, 1]
        )
        for workers, engines in batch_engine_sets.items():
            pools[f"batch_{workers}"] = DedicatedPool(
                f"fp32-batch-{workers}", engines, cases, arrays, list(range(workers))
            )

        natural = list(range(len(cases)))
        # Exactly one full untimed warm batch for each measured mode.
        run_direct(baseline_engines, cases, arrays, natural)
        run_direct(fp32_serial_engines, cases, arrays, natural)
        run_pair_pool(pools["fp32_parallel_pair"], natural)
        for workers in (1, 2, 4, 8):
            run_batch_pool(pools[f"batch_{workers}"], cases, workers, natural)

        modes = [
            "fp64_serial_pair",
            "fp32_serial_pair",
            "fp32_parallel_pair",
            "batch_1",
            "batch_2",
            "batch_4",
            "batch_8",
        ]
        mode_schedules = [modes, list(reversed(modes)), modes[2:] + modes[:2]]
        case_orders = [
            natural,
            list(reversed(natural)),
            natural[len(natural) // 3 :] + natural[: len(natural) // 3],
        ]
        measurements = {mode: [] for mode in modes}
        canonical_reference = None
        canonical_candidate = None
        signature_mismatches = []
        timed_phase_started = time.perf_counter_ns()
        for repetition, schedule in enumerate(mode_schedules):
            case_order = case_orders[repetition]
            for mode in schedule:
                if mode == "fp64_serial_pair":
                    raw = run_direct(baseline_engines, cases, arrays, case_order)
                elif mode == "fp32_serial_pair":
                    raw = run_direct(fp32_serial_engines, cases, arrays, case_order)
                elif mode == "fp32_parallel_pair":
                    raw = run_pair_pool(pools[mode], case_order)
                else:
                    workers = int(mode.removeprefix("batch_"))
                    raw = run_batch_pool(pools[mode], cases, workers, case_order)
                value, records = finish_measurement(raw)
                value["repetition"] = repetition
                value["task_latency_ms"] = [record["task_wall_ms"] for record in records]
                measurements[mode].append(value)
                indexed = {(record["case_index"], record["rx"]): record for record in records}
                if mode == "fp64_serial_pair" and canonical_reference is None:
                    canonical_reference = indexed
                elif mode == "fp64_serial_pair":
                    for key, record in indexed.items():
                        if record["signature_sha256"] != canonical_reference[key]["signature_sha256"]:
                            signature_mismatches.append({"mode": mode, "repetition": repetition, "key": key})
                elif mode == "fp32_serial_pair" and canonical_candidate is None:
                    canonical_candidate = indexed
                elif canonical_candidate is not None:
                    for key, record in indexed.items():
                        if record["signature_sha256"] != canonical_candidate[key]["signature_sha256"]:
                            signature_mismatches.append({"mode": mode, "repetition": repetition, "key": key})

        timed_phase_seconds = (time.perf_counter_ns() - timed_phase_started) / 1e9
        if timed_phase_seconds > 60:
            raise TimeoutError("timed benchmark phase exceeded 60 seconds")
        if canonical_reference is None or canonical_candidate is None:
            raise RuntimeError("canonical serial schedules did not complete")
        if signature_mismatches:
            raise ValueError("parallel science signatures differ from serial backend")

        for pool in pools.values():
            pool.close_threads()
        pool_affinity = {name: pool.affinity for name, pool in pools.items()}
        pools.clear()

        baseline_wall = statistics.median(
            value["batch_wall_ms"] for value in measurements["fp64_serial_pair"]
        )
        baseline_cpu = statistics.median(
            value["aggregate_process_cpu_ms"]
            for value in measurements["fp64_serial_pair"]
        )
        summaries = {
            mode: summarize_mode(values, baseline_wall, baseline_cpu)
            for mode, values in measurements.items()
        }
        validation = reference_summary(canonical_reference, canonical_candidate, cases)
        return {
            "schema": "org.leo.research.server-parallel-result/v1",
            "scope": "server-only stateless component benchmark; no ARM or end-to-end claim",
            "status": "complete",
            "design_sha256": digest(HERE / "design.json"),
            "source_lock_sha256": digest(HERE / "source_lock.json"),
            "frozen_sources": lock["files"],
            "host": host_metadata(),
            "input": {
                "physical_visits": len(cases),
                "receiver_visits": 2 * len(cases),
                "preloaded_shared_readonly": True,
                "preload_receipts": preload_receipts,
            },
            "affinity": {
                "original_main_thread": original_affinity,
                "timed_main_thread": [0],
                "worker_threads": pool_affinity,
                "restoration_required": True,
            },
            "schedule": {
                "warmups_per_mode": 1,
                "timed_repetitions_per_mode": 3,
                "mode_schedules": mode_schedules,
                "case_orders": ["forward", "reverse", "rotate_by_42"],
                "timed_phase_seconds": timed_phase_seconds,
            },
            "validation": {
                **validation,
                "parallel_signature_mismatches": signature_mismatches,
                "all_candidate_runs_equal_serial_fp32": not signature_mismatches,
            },
            "summary": summaries,
            "measurements": measurements,
            "interpretation": [
                "Physical-visit pair latency is the relevant no-queue RX0/RX1 result.",
                "Batch wall throughput includes dispatch but is not single-visit latency or a real-time guarantee.",
                "Aggregate process CPU includes all workers and is separate from elapsed wall speedup.",
                "This stateless detector component result is not an end-to-end pipeline or ARM claim.",
            ],
        }
    finally:
        for pool in list(pools.values()):
            pool.close_threads()
        for engines in reversed(engine_sets):
            engines.close()
        os.sched_setaffinity(0, set(original_affinity))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("output must be a new file directly beneath server_parallel")
    result = run()
    result["affinity"]["restored_main_thread"] = sorted(os.sched_getaffinity(0))
    if result["affinity"]["restored_main_thread"] != result["affinity"]["original_main_thread"]:
        raise ValueError("main-thread affinity was not restored")
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    concise = {
        mode: {
            "wall_ms": values["batch_wall_ms"]["median"],
            "process_cpu_ms": values["aggregate_process_cpu_ms"]["median"],
            "visits_per_s": values["receiver_visits_per_second"],
            "wall_speedup": values["batch_wall_speedup_vs_packed_fp64_serial"],
            "pair_p95_ms": values.get("physical_visit_pair_wall_ms", {}).get("p95"),
        }
        for mode, values in result["summary"].items()
    }
    print(json.dumps({"validation": result["validation"], "summary": concise}, sort_keys=True))


if __name__ == "__main__":
    main()
