"""Bounded paired full-response latency experiment on persistent processes."""

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "src"), str(HERE)]

import numpy as np
import leo.scanner.detector as detector
import leo.analysis.starlink.acquisition as acquisition
import leo.analysis.starlink.pilot_methods as pilot_methods
from leo.scanner.models import ScannerConfiguration, current_low_band_targets
from parallel_scanner import ParallelScanner

DATASET = HERE.parent / "new_data"
CASE_IDS = (
    "newdev-r2500000-scan-fw-40ebc07665464c7d-v001077",
    "newdev-r5000000-scan-fw-e76c229e9dc498b3-v001077",
)
MODES = ("serial", "workers8", "workers22")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    paths = [HERE / "design.json", Path(__file__), HERE / "parallel_scanner.py",
             DATASET / "cases.json", Path(detector.__file__), Path(acquisition.__file__),
             Path(pilot_methods.__file__), Path(acquisition._native_acquisition.__file__),
             ROOT / "src/leo/scanner/models.py", ROOT / "src/leo/analysis/starlink/templates.py"]
    return {str(path): digest(path) for path in paths}


def science(result):
    return json.dumps(dataclasses.asdict(result), default=lambda obj: obj.model_dump(mode="json"),
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def worker_ticks(pool):
    if pool is None:
        return 0
    ticks = 0
    for pid in pool.pool._processes:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        ticks += int(fields[11]) + int(fields[12])
    return ticks


def execute(raw, config, edge, pool):
    before = worker_ticks(pool)
    cpu_start, wall_start = time.process_time_ns(), time.perf_counter_ns()
    samples = np.empty(raw.shape[:2], dtype=np.complex64)
    samples.real, samples.imag = raw[:, :, 0], raw[:, :, 1]
    samples.flags.writeable = False
    if pool is None:
        result = detector.analyze_glrt64_dwell(samples, config, edge=edge)
        worker_dsp_cpu = 0.0
    else:
        result, worker_dsp_cpu = pool.run(samples, config, edge=edge)
    wall = (time.perf_counter_ns() - wall_start) / 1e6
    parent_cpu = (time.process_time_ns() - cpu_start) / 1e6
    child_cpu = (worker_ticks(pool) - before) * 1000 / os.sysconf("SC_CLK_TCK")
    return science(result), {"wall_ms": wall, "parent_cpu_ms": parent_cpu,
                            "worker_cpu_ms_proc_ticks": child_cpu,
                            "aggregate_cpu_ms": parent_cpu + child_cpu,
                            "worker_detector_cpu_ms": worker_dsp_cpu}


def main():
    lock_path = HERE / "source_lock.json"
    if sys.argv[1:] == ["--freeze"]:
        with lock_path.open("x") as stream:
            json.dump(sources(), stream, indent=2)
        return
    lock = json.loads(lock_path.read_text())
    if sources() != lock:
        raise ValueError("parallel sources changed")
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(f"{name} must equal one before importing numerical libraries")
    result_path = HERE / "results.json"
    if result_path.exists():
        raise ValueError("preserve existing result")
    affinity = os.sched_getaffinity(0)
    if not set(range(22)) <= affinity:
        raise ValueError("declared cores unavailable")
    cases = {item["case_id"]: item for item in json.loads((DATASET / "cases.json").read_text())["cases"]}
    pools = {}
    rows = []
    start = time.perf_counter()
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("120 second bound")))
    signal.alarm(120)
    status = "complete"
    error = None
    try:
        os.sched_setaffinity(0, {0})
        pools = {"serial": None, "workers8": ParallelScanner(range(8)), "workers22": ParallelScanner(range(22))}
        for case_id in CASE_IDS:
            case = cases[case_id]
            path = (DATASET / case["raw_npy"]["path"]).resolve()
            if not path.is_relative_to(DATASET.resolve()) or "sha256:" + digest(path) != case["raw_npy"]["sha256"]:
                raise ValueError("input hash mismatch")
            raw = np.load(path, mmap_mode="r", allow_pickle=False)
            if raw.dtype != np.dtype("<i2") or raw.shape != (case["rate_hz"] * 120 // 1000, 2, 2):
                raise ValueError("input geometry mismatch")
            target = next(item for item in current_low_band_targets()
                          if item.channel == case["channel"] and item.edge.value == case["edge"])
            config = ScannerConfiguration(sample_rate_hz=case["rate_hz"], bandwidth_hz=case["rate_hz"],
                                          targets=(target,), maximum_acquisition_candidates=10)
            expected = None
            for mode in MODES:
                output, _ = execute(raw, config, case["edge"], pools[mode])
                if expected is None:
                    expected = output
                if output != expected:
                    raise ValueError(f"{mode} warm full response mismatch")
            measurements = []
            for repeat in range(3):
                for mode in MODES[repeat:] + MODES[:repeat]:
                    output, measurement = execute(raw, config, case["edge"], pools[mode])
                    if output != expected:
                        raise ValueError(f"{mode} measured full response mismatch")
                    measurements.append({"repeat": repeat, "mode": mode, **measurement})
            summary = {mode: {key: statistics.median(row[key] for row in measurements if row["mode"] == mode)
                              for key in ("wall_ms", "aggregate_cpu_ms", "worker_detector_cpu_ms")}
                       for mode in MODES}
            for mode in MODES:
                summary[mode]["wall_speedup"] = summary["serial"]["wall_ms"] / summary[mode]["wall_ms"]
            if "sha256:" + digest(path) != case["raw_npy"]["sha256"]:
                raise ValueError("input changed")
            rows.append({"case_id": case_id, "rate_hz": case["rate_hz"], "exact_full_response": True,
                         "input_immutable": True, "response_sha256": hashlib.sha256(expected.encode()).hexdigest(),
                         "measurements": measurements, "summary": summary})
            print(json.dumps({"case": case_id, "summary": summary}), flush=True)
    except TimeoutError as caught:
        status = "timed_out_partial"
        error = str(caught)
    except Exception as caught:
        status = "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        for pool in pools.values():
            if pool is not None:
                pool.close()
        os.sched_setaffinity(0, affinity)
    payload = {"status": status, "error": error, "source_lock": lock, "elapsed_seconds_including_pool_lifecycle": time.perf_counter()-start,
               "cpu_accounting": "parent process CPU plus per-worker proc stat tick deltas; worker resolution milliseconds="
               + str(1000/os.sysconf("SC_CLK_TCK")), "rows": rows}
    with result_path.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
    print(json.dumps({"status": status, "result": str(result_path)}), flush=True)


if __name__ == "__main__":
    main()
