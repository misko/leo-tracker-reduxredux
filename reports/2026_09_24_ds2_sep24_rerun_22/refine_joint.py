#!/usr/bin/env python3
"""Run sealed, reference-free local and fine refinement for successor joints.

This runner intentionally starts only after the complete portable parent is
sealed.  It derives the joint task prefix from that parent rather than
borrowing DS2-20 task names, and it writes every proposal, result, and index
beneath the supplied successor output root.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STAGE_ONE_RADII_KM = (4.6875, 9.375, 18.75)
STAGE_ONE_LEVELS_KM = (1.5625, 0.78125, 0.390625)
FINE_RADII_KM = (0.5859375, 1.171875, 2.34375)
FINE_LEVELS_KM = (0.1953125, 0.09765625)
MAX_WORKERS = 3


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> bool:
    if not path.is_file():
        return False
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return any(
        sidecar.is_file() and sidecar.read_text().strip().removeprefix("sha256:") == actual
        for sidecar in (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_or_verify_sealed(path: Path, value: Any) -> None:
    """Create an immutable artifact, or verify the exact prior proposal."""
    content = canonical(value)
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        if not sealed(path) or path.read_text() != content:
            raise ValueError(f"existing sealed artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


def require_relative(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"artifact escapes successor output root: {path}") from error
    return resolved


def require_inference_document(path: Path) -> dict[str, Any]:
    if not sealed(path):
        raise ValueError(f"inference artifact is not sealed: {path}")
    document = load_json(path)
    if not isinstance(document.get("task_id"), str):
        raise ValueError(f"inference lacks its task ID: {path}")
    if document.get("reference_coordinate_present") is not False:
        raise ValueError(f"inference crossed the reference boundary: {path}")
    if "estimated_position" not in document:
        raise ValueError(f"inference lacks an estimated position: {path}")
    return document


def require_inference(path: Path, task_id: str) -> dict[str, Any]:
    document = require_inference_document(path)
    if document["task_id"] != task_id:
        raise ValueError(f"inference task ID mismatch: {path}")
    return document


@dataclass(frozen=True)
class Parent:
    output_root: Path
    cache_root: Path
    adapter: Path
    joint_prefix: str
    tasks: tuple[dict[str, Any], ...]


def parent_context(output_root: Path, cache_root: Path) -> Parent:
    """Validate the completed portable parent and derive its dynamic joints."""
    output_root = output_root.resolve()
    plan_path = output_root / "portable" / "plan.json"
    execution_path = output_root / "portable" / "execution.json"
    if not sealed(plan_path) or not sealed(execution_path):
        raise ValueError("joint refinement requires sealed portable plan and complete execution")
    plan = load_json(plan_path)
    execution = load_json(execution_path)
    if (
        plan.get("schema") != "ds2-successor-portable-plan/v1"
        or plan.get("reference_coordinate_present") is not False
        or execution.get("schema") != "ds2-successor-portable-execution/v1"
        or execution.get("complete") is not True
        or execution.get("reference_coordinate_present") is not False
    ):
        raise ValueError("portable parent does not attest the reference-free completion boundary")
    prefix = plan.get("joint_task_prefix")
    sessions = plan.get("sessions")
    if not isinstance(prefix, str) or not isinstance(sessions, list):
        raise ValueError("portable parent lacks a dynamic joint prefix")
    if prefix != f"joint-all{len(sessions)}":
        raise ValueError("joint prefix is inconsistent with the sealed session count")
    planned = plan.get("tasks")
    rows = execution.get("rows")
    if not isinstance(planned, list) or not isinstance(rows, list):
        raise ValueError("portable parent task receipt is malformed")
    ids = [row.get("task_id") for row in planned]
    if [row.get("task_id") for row in rows] != ids:
        raise ValueError("portable execution receipt does not cover the sealed plan")
    receipt_by_id = {row["task_id"]: row for row in rows}
    joints = []
    for task in planned:
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id.startswith(prefix + "__"):
            continue
        output = require_relative(Path(task["output_path"]), output_root)
        require_inference(output, task_id)
        if receipt_by_id[task_id].get("sha256") != digest(output):
            raise ValueError(f"portable receipt digest disagrees with task: {task_id}")
        joints.append(task)
    if not joints:
        raise ValueError("sealed portable parent has no joint tasks")
    adapter_text = plan.get("adapters", {}).get("portable_evaluation")
    adapter = Path(adapter_text) if isinstance(adapter_text, str) else None
    if adapter is None or not adapter.is_file():
        raise ValueError("sealed portable parent lacks its portable adapter")
    return Parent(
        output_root=output_root,
        cache_root=cache_root.resolve(),
        adapter=adapter.resolve(),
        joint_prefix=prefix,
        tasks=tuple(joints),
    )


def levels_for_radius(radius_km: float, final_levels_km: tuple[float, ...]) -> tuple[float, ...]:
    """Prepend reusable coarser steps until the fixed final ladder fits."""
    levels = []
    level = radius_km / 3.0
    while level > final_levels_km[0] + 1e-12:
        levels.append(level)
        level /= 2.0
    return (*levels, *final_levels_km)


def boundary_triggered(radial_km: float, radius_km: float, first_level_km: float) -> bool:
    """Keep one full first-level cell between the winner and a search edge."""
    return radial_km >= radius_km - first_level_km - 1e-9


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    earth_km = 6371.0088
    lat1, lat2 = map(math.radians, (left[0], right[0]))
    dlat = lat2 - lat1
    dlon = math.radians(right[1] - left[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth_km * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def winner_radial_offset_km(document: dict[str, Any], centre: dict[str, Any]) -> float:
    if "selected" in document:
        return math.hypot(
            float(document["selected"]["east_km"]), float(document["selected"]["north_km"])
        )
    estimate = document["estimated_position"]
    return haversine_km(
        (float(centre["latitude_deg"]), float(centre["longitude_deg"])),
        (float(estimate["latitude_deg"]), float(estimate["longitude_deg"])),
    )


def refinement_task(
    parent: Parent,
    coarse_task: dict[str, Any],
    centre_document: dict[str, Any],
    *,
    stage: str,
    attempt: int,
    radius_km: float,
    final_levels_km: tuple[float, ...],
    parent_artifact: Path,
) -> tuple[dict[str, Any], Path]:
    label = str(coarse_task["task_id"]).removeprefix(parent.joint_prefix + "__")
    task_id = f"{parent.joint_prefix}-{stage}__{label}__attempt-{attempt}"
    root = parent.output_root / "portable" / "refinement"
    stage_root = root / stage
    output = stage_root / "inference" / f"{task_id}.json"
    task_path = stage_root / "tasks" / f"{task_id}.json"
    point = centre_document["estimated_position"]
    search_levels = levels_for_radius(radius_km, final_levels_km)
    task = {
        **coarse_task,
        "task_id": task_id,
        "group_id": f"ds2-successor-{parent.joint_prefix}-{stage}-reference-free-refinement",
        "prior": {
            "name": f"sealed-{label}-{stage}-winner-symmetric-{radius_km:g}km",
            "lat": float(point["latitude_deg"]),
            "lon": float(point["longitude_deg"]),
            "radius_km": radius_km,
            "reference_used_for_selection": False,
        },
        "options": {
            **coarse_task["options"],
            "geographic_levels_km": list(search_levels),
            "search_levels_km": list(search_levels),
        },
        "output_path": str(output.resolve()),
        "refinement_parent_sha256": digest(parent_artifact),
        "reference_coordinate_present": False,
    }
    require_relative(output, parent.output_root)
    require_relative(task_path, parent.output_root)
    return task, task_path


def run_adapter(parent: Parent, task: dict[str, Any], task_path: Path) -> None:
    output = Path(task["output_path"])
    # The sealed proposal binds a resumed result to this exact parent digest,
    # search ladder, and reference-free prior before accepting its output.
    write_or_verify_sealed(task_path, task)
    if output.exists():
        require_inference(output, task["task_id"])
        return
    env = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(parent.adapter),
            "--task",
            str(task_path),
            "--cache-root",
            str(parent.cache_root),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"refinement task failed: {task['task_id']}: {result.stderr[-4000:]}")
    require_inference(output, task["task_id"])


def run_one(
    parent: Parent,
    coarse_task: dict[str, Any],
    *,
    stage: str,
    radii_km: tuple[float, ...],
    final_levels_km: tuple[float, ...],
    centre_artifact: Path,
) -> dict[str, Any]:
    """Refine one sealed parent with symmetric expansion if its winner is near an edge."""
    centre = require_inference_document(centre_artifact)
    label = str(coarse_task["task_id"]).removeprefix(parent.joint_prefix + "__")
    attempts = []
    final_path: Path | None = None
    exhausted = True
    started = time.monotonic()
    for attempt, radius_km in enumerate(radii_km, 1):
        task, task_path = refinement_task(
            parent,
            coarse_task,
            centre,
            stage=stage,
            attempt=attempt,
            radius_km=radius_km,
            final_levels_km=final_levels_km,
            parent_artifact=centre_artifact,
        )
        run_adapter(parent, task, task_path)
        output = Path(task["output_path"])
        document = require_inference(output, task["task_id"])
        radial = winner_radial_offset_km(document, centre["estimated_position"])
        boundary = boundary_triggered(radial, radius_km, final_levels_km[0])
        attempts.append(
            {
                "attempt": attempt,
                "radius_km": radius_km,
                "search_levels_km": list(levels_for_radius(radius_km, final_levels_km)),
                "winner_radial_offset_km": radial,
                "boundary_triggered": boundary,
                "artifact": str(output),
                "sha256": digest(output),
            }
        )
        final_path = output
        if not boundary:
            exhausted = False
            break
    assert final_path is not None
    return {
        "method": label,
        "stage": stage,
        "parent_artifact": str(centre_artifact),
        "parent_sha256": digest(centre_artifact),
        "centre_policy": "each method's own sealed winner; no reference coordinate",
        "levels_km": list(final_levels_km),
        "attempts": attempts,
        "edge_expansion_exhausted": exhausted,
        "final_artifact": str(final_path),
        "final_sha256": digest(final_path),
        "elapsed_s": time.monotonic() - started,
    }


def validate_index(
    path: Path,
    schema: str,
    parent: Parent,
    expected_methods: list[str],
    expected_parents: dict[str, Path],
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if not sealed(path):
        raise ValueError(f"existing refinement index is not sealed: {path}")
    document = load_json(path)
    if (
        document.get("schema") != schema
        or document.get("complete") is not True
        or document.get("reference_coordinate_present") is not False
        or document.get("joint_task_prefix") != parent.joint_prefix
    ):
        raise ValueError(f"existing refinement index is invalid: {path}")
    models = document.get("models")
    if not isinstance(models, list) or [row.get("method") for row in models] != expected_methods:
        raise ValueError(f"existing refinement index has the wrong model set: {path}")
    for row in models:
        expected_parent = expected_parents[parent.joint_prefix + "__" + row["method"]]
        if row.get("parent_artifact") != str(expected_parent):
            raise ValueError(f"existing refinement index has a different parent: {path}")
        if row.get("parent_sha256") != digest(expected_parent):
            raise ValueError(f"existing refinement index parent digest mismatch: {path}")
        final = require_relative(Path(row["final_artifact"]), parent.output_root)
        if row.get("final_sha256") != digest(final):
            raise ValueError(f"existing refinement index digest mismatch: {final}")
        if not sealed(final):
            raise ValueError(f"existing refinement output is not sealed: {final}")
        require_inference_document(final)
    return document


def run_stage(
    parent: Parent,
    *,
    stage: str,
    schema: str,
    radii_km: tuple[float, ...],
    final_levels_km: tuple[float, ...],
    parent_rows: dict[str, Path],
    workers: int,
) -> dict[str, Any]:
    root = parent.output_root / "portable" / "refinement" / stage
    index_path = root / "index.json"
    methods = [
        str(task["task_id"]).removeprefix(parent.joint_prefix + "__") for task in parent.tasks
    ]
    existing = validate_index(index_path, schema, parent, methods, parent_rows)
    if existing is not None:
        return existing
    arguments = [(task, parent_rows[task["task_id"]]) for task in parent.tasks]

    def execute(values: tuple[dict[str, Any], Path]) -> dict[str, Any]:
        task, centre = values
        return run_one(
            parent,
            task,
            stage=stage,
            radii_km=radii_km,
            final_levels_km=final_levels_km,
            centre_artifact=centre,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(execute, arguments))
    document = {
        "schema": schema,
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "joint_task_prefix": parent.joint_prefix,
        "symmetric_radii_km": list(radii_km),
        "levels_km": list(final_levels_km),
        "models": rows,
    }
    write_or_verify_sealed(index_path, document)
    return document


def run_refinement(output_root: Path, cache_root: Path, workers: int) -> dict[str, Any]:
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be in 1..{MAX_WORKERS}")
    parent = parent_context(output_root, cache_root)
    coarse_rows = {
        task["task_id"]: require_relative(Path(task["output_path"]), parent.output_root)
        for task in parent.tasks
    }
    stage_one = run_stage(
        parent,
        stage="stage-one",
        schema="ds2-successor-reference-free-local-refinement-index/v1",
        radii_km=STAGE_ONE_RADII_KM,
        final_levels_km=STAGE_ONE_LEVELS_KM,
        parent_rows=coarse_rows,
        workers=workers,
    )
    fine_parents = {
        parent.joint_prefix + "__" + row["method"]: Path(row["final_artifact"])
        for row in stage_one["models"]
    }
    fine = run_stage(
        parent,
        stage="fine",
        schema="ds2-successor-reference-free-fine-refinement-index/v1",
        radii_km=FINE_RADII_KM,
        final_levels_km=FINE_LEVELS_KM,
        parent_rows=fine_parents,
        workers=workers,
    )
    return {"stage_one": stage_one, "fine": fine}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()
    result = run_refinement(args.output_root, args.cache_root, args.workers)
    print(
        canonical(
            {
                "joint_models": len(result["stage_one"]["models"]),
                "complete": True,
                "reference_coordinate_present": False,
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
