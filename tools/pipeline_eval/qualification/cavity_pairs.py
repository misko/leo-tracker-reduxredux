"""Repeat compact projection and its control at the same v5 cavity boundary."""

import argparse
import gzip
import hashlib
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

from ..__main__ import DEFAULT_OUT, encoded, local_output, public_cases, references, run_one, write
from ..scoring import ARMS, NUMERICAL_TOLERANCE_KM, distance_km, validate_result
from .duty_results import REPORT, measurements
from .prefix_figures import csv_file

CASES = {"DS26-0036": "ds26-common127", "DS29-0082": "roof16"}
METHODS = ("v5_core", "orbit_projector")
REPEATS = 5
WORK = ("tracks", "observations", "initial_branches", "initial_arm_fits", "cavity_offered")


def run_order(case_index, repeat):
    return METHODS if (case_index + repeat) % 2 == 1 else METHODS[::-1]


def receipt_path(directory, case, repeat, method):
    return directory / f"{case}-{repeat}-{method}.json"


def benchmark(directory, cpus):
    if (
        len(cpus) != len(CASES)
        or len(set(cpus)) != len(CASES)
        or not set(cpus) <= os.sched_getaffinity(0)
    ):
        raise ValueError("choose two different permitted CPUs for the repeated cavity pairs")
    directory = local_output(directory)
    directory.mkdir(parents=True, exist_ok=True)
    inputs = []
    for case, panel in CASES.items():
        source, refs = references(panel, [case])
        (document,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
        inputs.append(document)

    def series(case_index, document, cpu):
        case = document["id"]
        digest = hashlib.sha256(encoded(document)).hexdigest()
        for repeat in range(1, REPEATS + 1):
            for index, method in enumerate(run_order(case_index, repeat)):
                path = receipt_path(directory, case, repeat, method)
                binding = dict(
                    id=case,
                    method=method,
                    repeat=repeat,
                    cpu=cpu,
                    execution_order=index,
                    input_sha256=digest,
                )
                if path.exists():
                    previous = json.loads(path.read_bytes())
                    if any(previous.get(key) != value for key, value in binding.items()):
                        raise ValueError(f"existing receipt has a different binding: {path.name}")
                    continue
                result = run_one(method, document, directory, 720, cpu)
                row = binding | result
                write(path, encoded(row) + b"\n")
                if result.get("input_sha256") != digest:
                    raise ValueError(f"{case} {method} used a different input")
                print(
                    case, repeat, method, row["result"]["status"], row["worker_wall_s"], flush=True
                )

    with ThreadPoolExecutor(max_workers=len(CASES)) as pool:
        jobs = [
            pool.submit(series, index, document, cpu)
            for index, (document, cpu) in enumerate(zip(inputs, cpus, strict=True))
        ]
        for job in jobs:
            job.result()


def read_journal(path, cpus, controls):
    if len(cpus) != len(CASES) or len(set(cpus)) != len(CASES):
        raise ValueError("the journal must use one different pinned CPU per recording")
    roster = {
        (case, repeat, method)
        for case in CASES
        for repeat in range(1, REPEATS + 1)
        for method in METHODS
    }
    if path.is_dir():
        receipts = {key: json.loads(receipt_path(path, *key).read_bytes()) for key in roster}
    else:
        with gzip.open(path, "rt") as stream:
            archive = list(map(json.loads, stream))
        receipts = {(r["id"], r["repeat"], r["method"]): r for r in archive}
        if len(receipts) != len(archive) or receipts.keys() != roster:
            raise ValueError("cavity archive must contain every recording, repeat and worker once")
    raw, timing = [], []
    for case_index, (case, cpu) in enumerate(zip(CASES, cpus, strict=True)):
        expected_input = controls[case, "v5_core"]["input_sha256"]
        for repeat in range(1, REPEATS + 1):
            order = run_order(case_index, repeat)
            pair = {}
            for index, method in enumerate(order):
                row = receipts[case, repeat, method]
                label = f"{case} repeat {repeat} {method}"
                binding = (case, method, repeat, cpu, index, expected_input)
                fields = ("id", "method", "repeat", "cpu", "execution_order", "input_sha256")
                if tuple(row.get(key) for key in fields) != binding:
                    raise ValueError(f"{label} has the wrong recording, input, CPU or order")
                validate_result(row["result"])
                ref = controls[case, method]
                wall = row.get("worker_wall_s")
                if type(wall) not in (float, int) or not math.isfinite(wall) or wall <= 0:
                    raise ValueError(f"{label} has invalid worker timing")
                if row["result"]["status"] == "ok":
                    if row.get("implementation_sha256") != ref["implementation_sha256"]:
                        raise ValueError(f"{label} changed the worker implementation")
                    metrics = row["result"]["metrics"]
                    if metrics.get("kernel_sha256") != ref["result"]["metrics"].get(
                        "kernel_sha256"
                    ):
                        raise ValueError(f"{label} changed the native kernel source")
                    if method == "v5_core":
                        for arm in ARMS:
                            separation = distance_km(
                                row["result"]["arms"][arm]["latlon"],
                                ref["result"]["arms"][arm]["latlon"],
                            )
                            if separation is None or separation > 1e-6:
                                raise ValueError(f"{label} moved the frozen {arm} control")
                pair[method] = row
                raw.append(row)
            timing.append(pair_timing(case, repeat, cpu, order[0], pair))
    return raw, timing


def pair_timing(case, repeat, cpu, first, pair):
    core, projector = (pair[method] for method in METHODS)
    a, b = (r["result"] for r in (core, projector))
    both_ok = a["status"] == b["status"] == "ok"
    differences = {
        arm: distance_km(
            a.get("arms", {}).get(arm, {}).get("latlon"),
            b.get("arms", {}).get(arm, {}).get("latlon"),
        )
        for arm in ARMS
    }
    matches_position = all(
        difference is not None and difference <= NUMERICAL_TOLERANCE_KM
        for difference in differences.values()
    )
    pairs = {field: (a["metrics"].get(field), b["metrics"].get(field)) for field in WORK}
    matches_work = all(control is not None and control == new for control, new in pairs.values())
    same_work_timing = both_ok and matches_position and matches_work
    return dict(
        recording=case,
        repeat=repeat,
        cpu=cpu,
        first_worker=first,
        input_sha256=core["input_sha256"],
        v5_core_implementation_sha256=core.get("implementation_sha256"),
        orbit_projector_implementation_sha256=projector.get("implementation_sha256"),
        kernel_source_sha256=b["metrics"].get("kernel_sha256"),
        v5_core_status=a["status"],
        orbit_projector_status=b["status"],
        v5_core_wall_s=core["worker_wall_s"],
        orbit_projector_wall_s=projector["worker_wall_s"],
        speedup=core["worker_wall_s"] / projector["worker_wall_s"] if same_work_timing else None,
        c0_coordinate_delta_km=differences["c0"],
        fitted_c_coordinate_delta_km=differences["fitted_c"],
        matches_work=matches_work,
        v5_core_initial_s=a["metrics"].get("stage_s", {}).get("initial"),
        orbit_projector_initial_s=b["metrics"].get("stage_s", {}).get("initial"),
        compact_projections=b["metrics"].get("compact_projections"),
        **{
            f"{method}_{field}": value
            for field, counts in pairs.items()
            for method, value in zip(METHODS, counts, strict=True)
        },
    )


def package(journal, output, cpus, controls):
    raw, timing = read_journal(journal, cpus, controls)
    records = b"".join(encoded(row) + b"\n" for row in raw)
    write(output / "cavity-repeats.jsonl.gz", gzip.compress(records, mtime=0))
    csv_file(output / "cavity-projection-timing.csv", timing)
    for case in CASES:
        rows = [r for r in timing if r["recording"] == case]
        speeds = [r["speedup"] for r in rows if r["speedup"] is not None]
        summary = "no qualified pairs"
        if speeds:
            summary = f"median {median(speeds):.3f}×, range {min(speeds):.3f} to {max(speeds):.3f}×"
        print(f"{case} {len(speeds)}/{len(rows)} qualified pairs, {summary}")
    return timing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, required=True, help="worker receipt folder or packaged journal to score"
    )
    parser.add_argument("--cpus", type=int, nargs=2, required=True)
    parser.add_argument("--report", type=Path, help="package a completed journal in this folder")
    parser.add_argument("--controls", type=Path, default=REPORT, help="prior timing report folder")
    args = parser.parse_args()
    if args.report:
        package(args.out, args.report, args.cpus, measurements(args.controls))
    else:
        benchmark(args.out, args.cpus)


if __name__ == "__main__":
    main()
