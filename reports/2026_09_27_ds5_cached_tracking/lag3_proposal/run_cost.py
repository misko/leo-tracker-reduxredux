#!/usr/bin/env python3
"""One frozen, proposal-only complete-ingress timing run on new development IQ."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lag3_proposal import Lag3Proposal, build_library, sha256  # noqa: E402

EXPECTED_DATASET_SHA256 = "b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845"


def _digest_array(raw: np.ndarray) -> str:
    return hashlib.sha256(raw.view(np.uint8)).hexdigest()


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]


def _scientific(result: dict) -> list[dict]:
    return result["candidates"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path,
                        default=HERE.parent / "new_data" / "cases.json")
    parser.add_argument("--output", type=Path, default=HERE / "cost_results.json")
    args = parser.parse_args()
    dataset_path = args.dataset.resolve()
    if sha256(dataset_path) != EXPECTED_DATASET_SHA256:
        raise ValueError("new-data manifest hash does not match the frozen design")
    manifest = json.loads(dataset_path.read_text())
    cases = manifest["cases"]
    if len(cases) != 128 or {int(row["rate_hz"]) for row in cases} != {2_500_000, 5_000_000}:
        raise ValueError("unexpected frozen development case set")

    binary = build_library()
    build_receipt_path = binary.with_name(binary.name + ".build.json")
    build_receipt = json.loads(build_receipt_path.read_text())
    workspaces = {
        (rate, edge): Lag3Proposal(rate, edge, binary)
        for rate in (2_500_000, 5_000_000) for edge in ("lower", "upper")
    }
    rows: list[dict] = []
    try:
        for case_index, case in enumerate(cases):
            rate = int(case["rate_hz"])
            raw_spec = case["raw_npy"]
            raw_path = dataset_path.parent / raw_spec["path"]
            expected_hash = raw_spec["sha256"].removeprefix("sha256:")
            if sha256(raw_path) != expected_hash:
                raise ValueError(f"IQ hash mismatch: {case['case_id']}")
            raw = np.load(raw_path, allow_pickle=False)
            if raw.dtype != np.dtype("<i2") or list(raw.shape) != raw_spec["shape"] or not raw.flags.c_contiguous:
                raise ValueError(f"IQ contract mismatch: {case['case_id']}")
            input_before = _digest_array(raw)
            proposal = workspaces[(rate, str(case["edge"]))]
            references: dict[int, list[dict]] = {}
            measurements: dict[int, list[dict]] = {0: [], 1: []}
            # One untimed warmup per receiver, with order counterbalanced by case.
            warm_order = (0, 1) if case_index % 2 == 0 else (1, 0)
            for receiver in warm_order:
                references[receiver] = _scientific(proposal.run(raw, receiver))
            # Three complete caller calls. Alternate receiver order by case+rep.
            for repetition in range(3):
                order = (0, 1) if (case_index + repetition) % 2 == 0 else (1, 0)
                for receiver in order:
                    started_cpu = time.thread_time_ns()
                    started_wall = time.perf_counter_ns()
                    result = proposal.run(raw, receiver)
                    wall_ms = (time.perf_counter_ns() - started_wall) / 1e6
                    cpu_ms = (time.thread_time_ns() - started_cpu) / 1e6
                    if _scientific(result) != references[receiver]:
                        raise RuntimeError(f"non-deterministic tuples: {case['case_id']} rx{receiver}")
                    measurements[receiver].append({
                        "repetition": repetition, "cpu_ms": cpu_ms, "wall_ms": wall_ms,
                        "native_timing_ms": result["native_timing_ms"],
                    })
            input_after = _digest_array(raw)
            if input_after != input_before:
                raise RuntimeError(f"caller IQ mutated: {case['case_id']}")
            for receiver in (0, 1):
                rows.append({
                    "case_id": case["case_id"], "case_index": case_index,
                    "rate_hz": rate, "edge": case["edge"], "receiver": receiver,
                    "input_sha256": input_before, "candidates": references[receiver],
                    "measurements": measurements[receiver],
                })
    finally:
        for workspace in workspaces.values():
            workspace.close()

    by_rate = {}
    passed = True
    for rate in (2_500_000, 5_000_000):
        selected = [m for row in rows if row["rate_hz"] == rate for m in row["measurements"]]
        cpu = [m["cpu_ms"] for m in selected]
        wall = [m["wall_ms"] for m in selected]
        native = [m["native_timing_ms"]["total_cpu"] for m in selected]
        gate = statistics.median(cpu) <= 0.080
        passed &= gate
        by_rate[str(rate)] = {
            "receiver_cases": sum(row["rate_hz"] == rate for row in rows),
            "timed_calls": len(cpu), "caller_thread_cpu_median_ms": statistics.median(cpu),
            "caller_thread_cpu_p95_ms": _percentile(cpu, 0.95),
            "caller_wall_median_ms": statistics.median(wall),
            "native_thread_cpu_median_ms": statistics.median(native),
            "gate_max_ms": 0.080, "gate_passed": gate,
        }
    sources = [HERE / name for name in (
        "design.json", "lag3_proposal.c", "lag3_proposal.h", "lag3_proposal.py",
        "run_cost.py", "test_lag3_proposal.py",
    )]
    output = {
        "schema": "org.leo.research.lag3-proposal-cost/v1",
        "created_unix_ns": time.time_ns(), "decision": "continue" if passed else "stop-cost-gate",
        "all_rate_cost_gates_passed": passed,
        "scope": "proposal-only; no detector replay, GLRT, holdout, RF, or ARM",
        "timing_contract": {
            "clock": "time.thread_time_ns around Lag3Proposal.run",
            "included": "shape/dtype/stride validation, ctypes boundary, native full-120ms proposal, result conversion",
            "excluded": "workspace/template setup, file IO, IQ/source hashing, post-call mutation hash",
            "warmups_per_receiver_case": 1, "repetitions_per_receiver_case": 3,
            "counterbalance": "receiver order alternates by case index and repetition",
        },
        "dataset": {"path": str(dataset_path), "sha256": sha256(dataset_path), "case_count": len(cases)},
        "build": {"binary": str(binary), "binary_sha256": sha256(binary),
                  "receipt": str(build_receipt_path), "receipt_sha256": sha256(build_receipt_path),
                  "receipt_payload": build_receipt},
        "sources_sha256": {str(path.resolve()): sha256(path) for path in sources},
        "summary_by_rate": by_rate, "rows": rows,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": output["decision"], "summary_by_rate": by_rate}, indent=2))


if __name__ == "__main__":
    main()
