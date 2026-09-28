"""Eight-process replay of the exact frozen original detector over the large DS7 cohort."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = REPO / "reports/2026_09_28_ds7_glrt_benchmark"
sys.path.insert(0, str(REFERENCE))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(plan: dict, inputs: dict, plan_path: Path) -> None:
    if plan["schema"] != "ds7-large-arm-plan/v1" or inputs["schema"] != "ds7-large-arm-inputs/v1":
        raise ValueError("schema")
    if not inputs["complete"] or inputs["plan_sha256"] != sha(plan_path):
        raise ValueError("input/plan binding")
    expected = [(c["session_id"], i, c["manifest_sha256"], c["sample_rate_hz"])
                for c in plan["captures"] for i in c["visit_indices"]]
    actual = [(r["session_id"], r["visit_index"], r["manifest_sha256"], r["rate_hz"])
              for r in inputs["rows"]]
    if expected != actual or len(set(actual)) != plan["expected_visits"]:
        raise ValueError("cohort membership/order")
    if plan["method"] != "original" or plan["repetitions"] != 1:
        raise ValueError("baseline workload")


_METHOD = None


def initialize_worker() -> None:
    global _METHOD
    identity = multiprocessing.current_process()._identity
    core = (identity[0] - 1) % 8 if identity else 0
    os.sched_setaffinity(0, {core})
    from methods import make_method
    _METHOD = make_method("original")


def analyze_one(task: tuple[str, dict]) -> dict:
    from pydantic import TypeAdapter
    import numpy as np
    from leo.scanner.models import ScannerConfiguration, ScanTarget

    input_root_string, context = task
    input_root = Path(input_root_string)
    path = input_root / context["file"]
    started_cpu = time.process_time()
    started_wall = time.perf_counter()
    try:
        if path.parent.resolve() != input_root.resolve() or sha(path) != context["sha256"]:
            raise ValueError("input payload binding")
        iq = np.load(path, allow_pickle=False)
        if list(iq.shape) != context["shape"] or str(iq.dtype) != context["dtype"]:
            raise ValueError("input geometry")
        rate = context["rate_hz"]
        duration = iq.shape[0] * 1000 / rate
        if duration != 120:
            raise ValueError("dwell geometry")
        config = ScannerConfiguration(
            sample_rate_hz=rate, bandwidth_hz=rate, dwell_ms=120,
            targets=(ScanTarget.model_validate(context["target"]),),
            maximum_acquisition_candidates=8,
        )
        samples = np.empty(iq.shape[:2], dtype=np.complex64)
        samples.real = iq[:, :, 0]
        samples.imag = iq[:, :, 1]
        got = _METHOD.analyze(samples, config, context["target"]["edge"], context)
        result = TypeAdapter(type(got.analysis)).dump_python(got.analysis, mode="json")
        return {"context": context, "method": "original", "repeat": 0, "status": "ok",
                "result": result, "diagnostics": got.diagnostics,
                "timing": {"cpu_s": time.process_time() - started_cpu,
                           "wall_s": time.perf_counter() - started_wall}}
    except Exception as error:
        return {"context": context, "method": "original", "repeat": 0, "status": "failed",
                "result": None, "diagnostics": {"error": repr(error)},
                "timing": {"cpu_s": time.process_time() - started_cpu,
                           "wall_s": time.perf_counter() - started_wall}}


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers != 8:
        raise ValueError("this audited arm requires exactly eight workers")
    plan = json.loads(args.plan.read_text())
    inputs_path = args.inputs / "inputs.json"
    inputs = json.loads(inputs_path.read_text())
    validate(plan, inputs, args.plan)
    args.output.mkdir(parents=True, exist_ok=False)
    dependencies = [Path(__file__), REFERENCE / "methods.py",
                    REPO / "src/leo/scanner/detector.py", REPO / "src/leo/scanner/models.py",
                    REPO / "src/leo/analysis/starlink/acquisition.py",
                    REPO / "src/leo/analysis/starlink/pilot_methods.py",
                    REPO / "reports/2026_09_27_server_scan_speed/pilot_methods_baseline.py",
                    REPO / "reports/2026_09_27_server_scan_speed/acquisition_peak/original/acquisition.py"]
    hashes = {str(path): sha(path) for path in dependencies}
    header = {
        "schema": "ds7-large-arm-baseline-run/v1", "plan_sha256": sha(args.plan),
        "input_manifest_sha256": sha(inputs_path), "dataset_sha256": plan["dataset_sha256"],
        "source_hashes": hashes, "method": "original", "repetitions": 1,
        "workers": 8, "worker_cores": list(range(8)), "numerical_threads_per_worker": 1,
        "probe_ms": 20, "probe_stride_ms": 10, "probe_windows_per_receiver": 11,
        "receiver_count": 2, "maximum_acquisition_candidates": 8,
        "python": sys.version, "platform": platform.platform(),
        "scope": "scientific result baseline; parallel scheduling is not an ARM timing comparison",
        "complete": False, "planned_calls": plan["expected_visits"], "calls": 0,
        "failed_calls": 0, "sources_unchanged": False,
    }
    (args.output / "run.json").write_text(json.dumps(header, indent=2) + "\n")
    started = time.monotonic()
    calls = failures = 0
    tasks = [(str(args.inputs), row) for row in inputs["rows"]]
    try:
        signal.alarm(plan["runner_wall_limit_s"])
        with ProcessPoolExecutor(max_workers=8, initializer=initialize_worker) as executor:
            with (args.output / "rows.jsonl").open("x") as stream:
                for row in executor.map(analyze_one, tasks, chunksize=1):
                    stream.write(json.dumps(row, allow_nan=False) + "\n")
                    stream.flush()
                    calls += 1
                    failures += row["status"] != "ok"
                    if calls % 8 == 0:
                        print(json.dumps({"calls": calls, "failures": failures}), flush=True)
    finally:
        signal.alarm(0)
        stable = all(sha(Path(path)) == digest for path, digest in hashes.items())
        header.update(calls=calls, failed_calls=failures, sources_unchanged=stable,
                      complete=calls == header["planned_calls"] and failures == 0 and stable,
                      wall_s=time.monotonic() - started,
                      parent_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      children_cpu_s=(resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime +
                                      resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime),
                      children_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        (args.output / "run.json").write_text(json.dumps(header, indent=2) + "\n")
    if not header["complete"]:
        raise RuntimeError("baseline run incomplete; retained rows and receipt")


if __name__ == "__main__":
    run()
