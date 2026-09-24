#!/usr/bin/env python3
"""Run DS1 TRAIN task files concurrently through independently owned runners."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark import canonical_json, validate_result, validate_task

HERE = Path(__file__).resolve().parent


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text())
    if payload.get("schema") != "ds1-train-full-runner-registry/v1":
        raise ValueError("unexpected runner registry schema")
    methods = payload.get("methods")
    if not isinstance(methods, dict):
        raise ValueError("runner registry methods missing")
    result: dict[str, dict[str, Any]] = {}
    for name, entry in methods.items():
        command = entry.get("command") if isinstance(entry, dict) else None
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(x, str) for x in command)
        ):
            raise ValueError(f"invalid command for {name}")
        if "{task}" not in command:
            raise ValueError(f"runner command for {name} needs {{task}}")
        cap = entry.get("max_concurrency")
        if cap is not None and (not isinstance(cap, int) or cap < 1):
            raise ValueError(f"invalid max_concurrency for {name}")
        shards = entry.get("geographic_shards", 1)
        if not isinstance(shards, int) or shards < 1:
            raise ValueError(f"invalid geographic_shards for {name}")
        result[name] = {"command": command, "max_concurrency": cap, "geographic_shards": shards}
    return result


def sealed_artifact(path: Path, task: dict[str, Any]) -> bool:
    seal = path.with_suffix(".sha256")
    if not path.exists() or not seal.exists():
        return False
    if seal.read_text().strip() != hashlib.sha256(path.read_bytes()).hexdigest():
        return False
    try:
        validate_result(task, json.loads(path.read_text()))
    except (ValueError, json.JSONDecodeError):
        return False
    return True


def worker_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    return env


def run_one(
    task: dict[str, Any], registry: dict[str, dict[str, Any]], report_root: Path
) -> dict[str, Any]:
    validate_task(task, report_root)
    output = (report_root / task["output_path"]).resolve()
    if sealed_artifact(output, task):
        return {"task_id": task["task_id"], "status": "skipped"}
    entry = registry.get(task["method"])
    if entry is None:
        return {"task_id": task["task_id"], "status": "unconfigured", "method": task["method"]}
    command_template = entry["command"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{task['task_id']}-", dir=output.parent) as temporary:
        task_input, raw_output = Path(temporary) / "task.json", Path(temporary) / "result.json"
        runner_task = dict(task)
        runner_task["output_path"] = str(raw_output)
        task_input.write_text(canonical_json(runner_task))
        command = [
            piece.replace("{task}", str(task_input)).replace("{output}", str(raw_output))
            for piece in command_template
        ]
        env = worker_environment()
        # A runner that can divide geographic cells internally receives this
        # declared count. It still must emit the one sealed winner for the task.
        env["DS1_GEOGRAPHIC_SHARD_COUNT"] = str(entry["geographic_shards"])
        completed = subprocess.run(
            command, cwd=report_root, env=env, text=True, capture_output=True
        )
        if completed.returncode:
            return {
                "task_id": task["task_id"],
                "status": "failed",
                "returncode": completed.returncode,
                "stderr": completed.stderr[-2000:],
                "stdout": completed.stdout[-2000:],
            }
        try:
            result = json.loads(raw_output.read_text())
            validate_result(task, result)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"task_id": task["task_id"], "status": "invalid_output", "error": str(exc)}
        payload = canonical_json(result)
        staged, staged_seal = Path(temporary) / "sealed.json", Path(temporary) / "sealed.sha256"
        staged.write_text(payload)
        staged_seal.write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")
        staged.replace(output)
        staged_seal.replace(output.with_suffix(".sha256"))
    return {"task_id": task["task_id"], "status": "completed", "artifact": str(output)}


def selected_tasks(
    manifest: dict[str, Any], tiers: set[str], methods: set[str] | None
) -> list[dict[str, Any]]:
    selected = [task for task in manifest["tasks"] if task["tier"] in tiers]
    if methods is not None:
        selected = [task for task in selected if task["method"] in methods]
    return sorted(
        selected, key=lambda task: (task["estimated_cost"]["work_units"], task["task_id"])
    )


def run_queue(
    tasks: list[dict[str, Any]],
    registry: dict[str, dict[str, Any]],
    report_root: Path,
    workers: int,
) -> list[dict[str, Any]]:
    """Keep every core busy while respecting expensive-method memory caps."""
    pending = list(tasks)
    active: dict[concurrent.futures.Future[dict[str, Any]], str] = {}
    method_active: defaultdict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        while pending or active:
            while len(active) < workers:
                selected_index = None
                for index, task in enumerate(pending):
                    method = task["method"]
                    cap = registry.get(method, {}).get("max_concurrency")
                    if cap is None or method_active[method] < cap:
                        selected_index = index
                        break
                if selected_index is None:
                    break
                task = pending.pop(selected_index)
                method = task["method"]
                future = executor.submit(run_one, task, registry, report_root)
                active[future] = method
                method_active[method] += 1
            if not active:
                raise RuntimeError("no runnable task; check runner method caps")
            done, _ = concurrent.futures.wait(
                active, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                method = active.pop(future)
                method_active[method] -= 1
                rows.append(future.result())
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=HERE / "inference-manifest.json")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--tiers", default="core", help="comma-separated: core,extended,expansion")
    parser.add_argument("--methods", default=None, help="optional comma-separated method IDs")
    parser.add_argument("--workers", type=int, default=min(24, os.cpu_count() or 1))
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    manifest_bytes = args.manifest.read_bytes()
    seal = args.manifest.with_suffix(".sha256")
    expected_manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    recorded_manifest_digest = (
        seal.read_text().strip().removeprefix("sha256:") if seal.exists() else ""
    )
    if recorded_manifest_digest != expected_manifest_digest:
        raise ValueError("manifest seal is missing or invalid")
    manifest = json.loads(manifest_bytes)
    if manifest.get("partitions_permitted") != ["train"]:
        raise ValueError("manifest is not TRAIN-only")
    registry, tiers = load_registry(args.registry), set(args.tiers.split(","))
    if not tiers.issubset({"core", "extended", "expansion"}):
        raise ValueError("unknown tier")
    methods = set(args.methods.split(",")) if args.methods else None
    tasks = selected_tasks(manifest, tiers, methods)
    for task in tasks:
        validate_task(task, HERE)
    rows = run_queue(tasks, registry, HERE, args.workers)
    summary: dict[str, Any] = {
        "selected": len(rows),
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "unconfigured": 0,
        "invalid_output": 0,
    }
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    (HERE / "scheduler-summary.json").write_text(canonical_json({"summary": summary, "rows": rows}))
    print(json.dumps(summary, sort_keys=True))
    if summary["failed"] or summary["invalid_output"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
