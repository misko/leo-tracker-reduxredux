#!/usr/bin/env python3
"""Bounded, reference-free 24-document resource measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import signal
import sys
import time
from pathlib import Path

import numpy as np

from tools import ds7_baseline_adapter as baseline

sys.modules.setdefault("ds7_baseline_adapter", baseline)
from tools import ds7_fast_baseline_adapter as fast  # noqa: E402
from tools.ds7_batched_objective import BatchedJointObjective  # noqa: E402


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_seal(value: dict) -> None:
    body = {key: item for key, item in value.items() if key != "content_sha256"}
    actual = "sha256:" + hashlib.sha256(canonical(body)).hexdigest()
    if value.get("content_sha256") != actual:
        raise ValueError("input contract seal mismatch")


def rss_kib() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise RuntimeError("VmRSS unavailable")


def retained_array_bytes(documents: list[dict]) -> int:
    seen = set()
    total = 0
    for document in documents:
        for track in document["tracks"]:
            for value in track.values():
                if isinstance(value, np.ndarray) and id(value) not in seen:
                    seen.add(id(value))
                    total += value.nbytes
    return total


def timeout(_signum, _frame) -> None:
    raise TimeoutError("120-second resource measurement deadline exceeded")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--arm", type=Path, required=True)
    parser.add_argument("--closeout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    started = time.monotonic()
    started_cpu = time.process_time()
    inputs = json.loads(args.inputs.read_text())
    validate_seal(inputs)
    arm = json.loads(args.arm.read_text())
    ready = [row for row in inputs["captures"] if row["state"] == "ready"]
    if len(ready) != 24:
        raise ValueError(f"expected exactly 24 ready captures, found {len(ready)}")

    validation_wall_start, validation_cpu_start = time.monotonic(), time.process_time()
    artifacts = []
    for row in ready:
        for artifact in row["artifacts"]:
            path = Path(artifact["path"])
            actual = sha256(path)
            if actual != artifact["sha256"]:
                raise ValueError(f"artifact digest mismatch: {path}")
            artifacts.append(
                {
                    "session_id": row["session_id"],
                    "kind": artifact["kind"],
                    "path": str(path),
                    "declared_sha256": artifact["sha256"],
                    "actual_sha256": actual,
                    "byte_count": path.stat().st_size,
                }
            )
    validation_wall = time.monotonic() - validation_wall_start
    validation_cpu = time.process_time() - validation_cpu_start

    rss_before_load = rss_kib()
    load_wall_start, load_cpu_start = time.monotonic(), time.process_time()
    documents = fast.load_documents({"inputs": ready, "config": arm["config"]})
    load_wall = time.monotonic() - load_wall_start
    load_cpu = time.process_time() - load_cpu_start
    rss_after_load = rss_kib()
    peak_after_load = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    tracks = sum(len(document["tracks"]) for document in documents)
    candidates = sum(
        track["candidate_position_km"].shape[0]
        for document in documents
        for track in document["tracks"]
    )
    training_observations = sum(
        int(track["mask"].sum())
        for document in documents
        for track in document["tracks"]
    )
    retained = retained_array_bytes(documents)
    objective = BatchedJointObjective(documents, arm["config"], max_group_rows=1024)
    point = np.zeros(len(documents) + 2, dtype=float)
    objective_wall_start, objective_cpu_start = time.monotonic(), time.process_time()
    value, gradient = objective.value_gradient(point)
    objective_wall = time.monotonic() - objective_wall_start
    objective_cpu = time.process_time() - objective_cpu_start
    rss_after_objective = rss_kib()
    peak_after_objective = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if not math.isfinite(value) or not np.isfinite(gradient).all():
        raise RuntimeError("objective returned nonfinite output")

    tool_paths = [
        Path(__file__),
        Path(fast.__file__),
        Path(__file__).resolve().parents[3] / "tools/ds7_batched_objective.py",
        Path(__file__).resolve().parents[3] / "tools/ds7_baseline_adapter.py",
    ]
    receipt = {
        "schema": "ds7-resource-readiness-24/v1",
        "status": "completed",
        "reference_audit": "reference_pose_scores_iq_excluded",
        "bindings": {
            "inputs": {"path": str(args.inputs), "sha256": sha256(args.inputs)},
            "arm": {"path": str(args.arm), "sha256": sha256(args.arm)},
            "wave4_closeout": {
                "path": str(args.closeout),
                "sha256": sha256(args.closeout),
            },
            "sources": {str(path): sha256(path) for path in tool_paths},
            "artifacts": artifacts,
        },
        "limits": {
            "wall_seconds": 120,
            "address_space_bytes": 4 * 1024**3,
            "cpu_threads": int(os.environ.get("OMP_NUM_THREADS", "1")),
            "blas_threads": int(os.environ.get("OPENBLAS_NUM_THREADS", "1")),
            "nice": os.nice(0),
            "objective_calls": 1,
        },
        "counts": {
            "documents": len(documents),
            "tracks": tracks,
            "candidate_rows": candidates,
            "training_observations": training_observations,
            "retained_array_bytes": retained,
        },
        "timing_seconds": {
            "artifact_validation_wall": validation_wall,
            "artifact_validation_cpu": validation_cpu,
            "document_load_wall": load_wall,
            "document_load_cpu": load_cpu,
            "objective_wall": objective_wall,
            "objective_cpu": objective_cpu,
            "total_wall": time.monotonic() - started,
            "total_cpu": time.process_time() - started_cpu,
        },
        "memory_kib": {
            "rss_before_load": rss_before_load,
            "rss_after_load": rss_after_load,
            "peak_after_load": peak_after_load,
            "rss_after_objective": rss_after_objective,
            "peak_after_objective": peak_after_objective,
        },
        "objective": {"value": value, "gradient_norm": float(np.linalg.norm(gradient))},
    }
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    signal.alarm(0)


if __name__ == "__main__":
    main()
