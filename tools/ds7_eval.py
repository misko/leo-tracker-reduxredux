#!/usr/bin/env python3
"""Research DS7 loading, bounded adapter execution and post-seal scoring.

Standard library only. Model adapters implement --request FILE --response FILE.
This orchestrator has no acquisition, database, or production analysis dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import shutil
import signal
import subprocess
import time
from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO / "reports/2026_09_27_ds7_post_ds6"
DS7_SHA256 = "sha256:47007b1c18e8182f6a005dfd05c237cb3edb9bf85ae6376c99ccf29d54434109"
CAPTURE_FIELDS = (
    "session_id",
    "manifest_sha256",
    "radio_id",
    "receiver_ids",
    "sample_rate_hz",
    "bandwidth_hz",
    "visits",
    "total_sample_count",
    "capture_start_utc_ns",
    "capture_start_earliest_utc_ns",
    "capture_start_latest_utc_ns",
    "capture_end_utc_ns",
    "chunk_inventory_sha256",
    "uncompressed_sha256",
)
STATES = {"ok", "abstained", "failed", "unavailable"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(), parse_constant=lambda x: invalid_number(x))


def invalid_number(value: str) -> None:
    raise ValueError(f"Nonfinite JSON number: {value}")


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    # Exclusive creation makes every published receipt write-once.
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def seal_object(obj: dict) -> dict:
    return {**obj, "content_sha256": digest(canonical(obj))}


def read_sealed(path: Path, schema: str) -> dict:
    obj = read_json(path)
    require(isinstance(obj, dict), f"Expected JSON object: {path}")
    require(obj.get("schema") == schema, f"Unexpected schema in {path}")
    body = {k: v for k, v in obj.items() if k != "content_sha256"}
    require(obj.get("content_sha256") == digest(canonical(body)), f"Invalid seal: {path}")
    return obj


def safe_relative(root: Path, name: str) -> Path:
    require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe artifact path")
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()), "Artifact escapes its root")
    require(not path.is_symlink(), "Symlink artifacts are not accepted")
    return path


def load_dataset(root: Path = DEFAULT_DATASET) -> tuple[dict, dict]:
    """Validate the actual minted DS7, including all pose and membership evidence."""
    require(file_digest(root / "manifest.json") == DS7_SHA256, "Not the frozen DS7 manifest")
    sealed = set()
    for line in (root / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        require(name not in sealed, "Duplicate dataset seal entry")
        require(file_digest(safe_relative(root, name)) == "sha256:" + expected, f"Changed: {name}")
        sealed.add(name)
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    require(actual == sealed | {"SHA256SUMS"}, "Dataset artifact inventory changed")
    m, units = read_json(root / "manifest.json"), read_json(root / "evaluation-units.json")
    rows = m["captures"]
    ids = [r["session_id"] for r in rows]
    require(len(ids) == len(set(ids)) == 88, "DS7 must contain exactly 88 unique recordings")
    require(m["status"] == "minted" and m["dataset_id"] == "DS7", "DS7 is not minted")
    require(digest(canonical(ids)) == m["session_inventory_sha256"], "Membership digest mismatch")
    require(units["full_dataset"] == ids, "Evaluation membership mismatch")
    require(units["single_scans"] == [[sid] for sid in ids], "Invalid singleton units")
    require(len(units["groups_of_8"]) == 11, "Expected eleven groups")
    require(all(len(g) == 8 for g in units["groups_of_8"]), "Invalid group size")
    require(
        [s for g in units["groups_of_8"] for s in g] == ids and not units["remainder"],
        "Invalid group coverage",
    )
    require(
        sorted(s for g in units["rate_strata"].values() for s in g) == sorted(ids),
        "Invalid rate coverage",
    )
    require(
        file_digest(root / "approved-proposal.json") == m["approved_proposal_sha256"],
        "Approval digest mismatch",
    )
    require(read_json(root / "approved-proposal.json")["captures"] == rows, "Approval changed")
    require(
        file_digest(root / "ds6-parent-manifest.json") == m["parent"]["manifest_sha256"],
        "DS6 digest mismatch",
    )
    authority = read_json(root / "pose-authority.json")
    require(
        file_digest(root / "pose-authority.json") == m["pose_authority_file_sha256"],
        "Pose authority changed",
    )
    for r in rows:
        pose_path = root / "pose" / (r["session_id"] + ".json")
        pose = read_json(pose_path)
        require(file_digest(pose_path) == r["pose_file_sha256"], "Pose bytes changed")
        require(
            pose["session_id"] == r["session_id"]
            and pose["manifest_sha256"] == r["manifest_sha256"],
            "Pose source mismatch",
        )
        require(
            pose["pose_authority"] == authority
            and digest(canonical(authority)) == r["pose_authority_digest"],
            "Pose authority mismatch",
        )
        require(
            digest(canonical({k: v for k, v in pose.items() if k != "binding_digest"}))
            == pose["binding_digest"]
            == r["pose_binding_digest"],
            "Pose binding mismatch",
        )
    return m, units


def load_recording(capture: dict, reader: Any) -> Any:
    """Narrow public reader port: callers inject AdaptiveHopIqStore(read_only=True).

    No constructed storage paths or raw-IQ reads here. Consumers use the public
    reader's API to read payloads and retain its integrity checks.
    """
    recording = reader.inspect(capture["session_id"])
    require(recording.manifest_sha256 == capture["manifest_sha256"], "Source manifest changed")
    return recording


def make_plan(m: dict, units: dict, suite: str) -> dict:
    selected = []

    def add(unit_id: str, kind: str, ids: list[str]) -> None:
        selected.append({"unit_id": unit_id, "kind": kind, "session_ids": ids})

    if suite == "smoke":
        add("single-001", "single", units["single_scans"][0])
    else:
        for i, ids in enumerate(units["single_scans"], 1):
            add(f"single-{i:03}", "single", ids)
        for i, ids in enumerate(units["groups_of_8"], 1):
            add(f"group8-{i:02}", "group8", ids)
            if suite == "budgets":
                for count in (2, 4):
                    add(f"prefix{count}-{i:02}", f"prefix{count}", ids[:count])
        add("full88", "full", units["full_dataset"])
    return seal_object(
        {
            "schema": "ds7-plan/v1",
            "dataset_id": "DS7",
            "dataset_sha256": DS7_SHA256,
            "suite": suite,
            "captures": [{k: r[k] for k in CAPTURE_FIELDS} for r in m["captures"]],
            "units": selected,
            "exposure_status": m["prior_exposure_status"],
            "reference_policy": (
                "reference excluded from requests; shared filesystem is not a sandbox"
            ),
        }
    )


def read_plan(path: Path, dataset: Path = DEFAULT_DATASET) -> dict:
    plan = read_sealed(path, "ds7-plan/v1")
    require(plan["dataset_sha256"] == DS7_SHA256, "Wrong dataset binding")
    require(plan["suite"] in ("smoke", "standard", "budgets"), "Unknown suite")
    # Compare against the minted authority, not only a self-supplied hash.
    m, units = load_dataset(dataset)
    require(plan == make_plan(m, units, plan["suite"]), "Plan differs from frozen unit policy")
    return plan


def prepare(dataset: Path, output: Path, suite: str) -> dict:
    m, units = load_dataset(dataset)
    plan = make_plan(m, units, suite)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "plan.json", plan)
    write_json(
        output / "inputs.template.json",
        {
            "schema": "ds7-input-index/v1",
            "dataset_sha256": DS7_SHA256,
            "reference_audit": "PENDING",
            "captures": [
                {
                    "session_id": r["session_id"],
                    "manifest_sha256": r["manifest_sha256"],
                    "state": "unavailable",
                    "reason": "No frozen observation export yet",
                    "artifacts": [],
                }
                for r in plan["captures"]
            ],
        },
    )
    return {"plan": str(output / "plan.json"), "units": len(plan["units"])}


def reject_reference_fields(obj: Any) -> None:
    """Catch accidental named truth/pose fields; this is not semantic data auditing."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            words = key.lower().replace("-", "_").split("_")
            require(
                not {"truth", "reference", "pose", "groundtruth"}.intersection(words),
                f"Reference-bearing field forbidden in worker input: {key}",
            )
            reject_reference_fields(value)
    elif isinstance(obj, list):
        for value in obj:
            reject_reference_fields(value)


def freeze_inputs(
    plan_path: Path, index_path: Path, output: Path, dataset: Path = DEFAULT_DATASET
) -> dict:
    plan, index = read_plan(plan_path, dataset), read_json(index_path)
    require(index.get("schema") == "ds7-input-index/v1", "Invalid input index schema")
    require(index.get("dataset_sha256") == DS7_SHA256, "Wrong input dataset")
    require(index.get("reference_audit") == "reference_excluded", "Input reference audit required")
    expected = {r["session_id"]: r["manifest_sha256"] for r in plan["captures"]}
    rows = index["captures"]
    require(
        len(rows) == len(expected) and {r["session_id"] for r in rows} == set(expected),
        "Input index must account for all 88 recordings, including unavailable inputs",
    )
    frozen = []
    for row in rows:
        require(row["manifest_sha256"] == expected[row["session_id"]], "Wrong source manifest")
        require(row["state"] in ("ready", "unavailable"), "Unknown input state")
        artifacts = []
        for item in row["artifacts"]:
            path = Path(item["path"])
            path = (
                (index_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
            )
            require(
                not path.is_relative_to(dataset.resolve()),
                "Dataset/pose artifacts cannot be model inputs",
            )
            require(
                item["kind"]
                in (
                    "observations",
                    "orbits",
                    "candidates",
                    "calibration",
                    "scan_estimate",
                    "reader_config",
                ),
                "Unknown artifact kind",
            )
            actual = file_digest(path)
            # JSON export metadata is inspectable. Binary arrays require the declared audit.
            if path.suffix == ".json":
                reject_reference_fields(read_json(path))
            if "sha256" in item:
                require(actual == item["sha256"], "Input changed before freezing")
            artifacts.append({"path": str(path), "sha256": actual, "kind": item["kind"]})
        require(row["state"] != "ready" or bool(artifacts), "Ready inputs require artifacts")
        require(row["state"] != "unavailable" or bool(row.get("reason")), "Missing reason")
        frozen.append(
            {
                "session_id": row["session_id"],
                "manifest_sha256": row["manifest_sha256"],
                "state": row["state"],
                "reason": row.get("reason"),
                "artifacts": artifacts,
            }
        )
    obj = seal_object(
        {
            "schema": "ds7-inputs/v1",
            "dataset_sha256": DS7_SHA256,
            "reference_audit": "reference_excluded",
            "captures": frozen,
        }
    )
    write_json(output, obj)
    return {"inputs": str(output), "states": dict(Counter(r["state"] for r in frozen))}


def check_inputs(inputs: dict, plan: dict) -> None:
    require(inputs["dataset_sha256"] == plan["dataset_sha256"], "Input dataset mismatch")
    require(inputs["reference_audit"] == "reference_excluded", "Input audit missing")
    expected = {(r["session_id"], r["manifest_sha256"]) for r in plan["captures"]}
    require(
        len(inputs["captures"]) == len(expected)
        and {(r["session_id"], r["manifest_sha256"]) for r in inputs["captures"]} == expected,
        "Input coverage mismatch",
    )
    for row in inputs["captures"]:
        require(row["state"] in ("ready", "unavailable"), "Unknown input state")
        require(row["state"] != "ready" or bool(row["artifacts"]), "Empty ready input")
        for item in row["artifacts"]:
            require(file_digest(Path(item["path"])) == item["sha256"], "Frozen input changed")


def validate_response(obj: dict, unit_id: str) -> dict:
    require(isinstance(obj, dict), "Response must be a JSON object")
    require(
        obj.get("schema") == "ds7-response/v1" and obj.get("unit_id") == unit_id,
        "Invalid response identity",
    )
    require(obj.get("status") in STATES, "Invalid response status")
    if obj["status"] == "ok":
        estimate = obj["estimate"]
        lat, lon = estimate["latitude_deg"], estimate["longitude_deg"]
        require(
            type(lat) in (float, int)
            and type(lon) in (float, int)
            and math.isfinite(lat)
            and math.isfinite(lon)
            and -90 <= lat <= 90
            and -180 <= lon <= 180,
            "Invalid geographic estimate",
        )
        require(
            type(obj.get("converged")) is bool and type(obj.get("boundary_hit")) is bool,
            "Convergence and boundary flags are required",
        )
        radius = obj.get("horizontal_radius_95_m")
        require(
            radius is None
            or (type(radius) in (float, int) and math.isfinite(radius) and radius >= 0),
            "Invalid uncertainty radius",
        )
    else:
        require(bool(obj.get("reason")), "Non-ok response needs a reason")
        require(obj.get("estimate") is None, "Non-ok response must not return an estimate")
    canonical(obj)
    return obj


def stop_process_group(process: subprocess.Popen) -> None:
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def limit_file_size() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))


def execute(command: list[str], request: Path, response: Path, seconds: float, log: Path) -> None:
    validate_adapter_launch(command)
    env = {
        "PATH": os.defpath,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    with log.open("xb") as stream:
        process = subprocess.Popen(
            [*command, "--request", str(request), "--response", str(response)],
            cwd=request.parent,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            preexec_fn=limit_file_size,
        )
        try:
            code = process.wait(timeout=seconds)
            require(code == 0, f"Adapter exited {code}")
        finally:
            # Also terminate descendants left behind by a normally exited adapter.
            stop_process_group(process)


def validate_adapter_launch(command: list[str]) -> None:
    # A sudo child can change UID/session while leaving its unprivileged parent
    # unable to terminate it. Reject these launchers even behind env/timeout.
    # If the runtime needs elevated access, start the runner at that privilege
    # and invoke the interpreter directly, retaining one UID/process group.
    privilege_launchers = {"sudo", "su", "doas", "pkexec", "runuser", "setsid"}
    require(
        not any(Path(arg).name in privilege_launchers for arg in command),
        "Adapter must retain runner UID and process group; "
        "privilege/session launchers are forbidden",
    )


def seal_run(root: Path) -> None:
    files = {
        str(p.relative_to(root)): file_digest(p) for p in sorted(root.rglob("*")) if p.is_file()
    }
    write_json(root / "seal.json", seal_object({"schema": "ds7-run-seal/v1", "files": files}))


def run(
    plan_path: Path,
    inputs_path: Path,
    arm_path: Path,
    output: Path,
    max_seconds: float = 300,
    unit_seconds: float = 60,
    selected_units: list[str] | None = None,
    dataset: Path = DEFAULT_DATASET,
) -> dict:
    require(0 < unit_seconds <= max_seconds <= 1800, "Use 0 < unit <= total <= 1800 seconds")
    plan, inputs, arm = (
        read_plan(plan_path, dataset),
        read_sealed(inputs_path, "ds7-inputs/v1"),
        read_json(arm_path),
    )
    check_inputs(inputs, plan)
    require(arm.get("schema") == "ds7-arm/v1" and arm.get("status") == "ready", "Arm is not ready")
    command = arm["command"]
    require(
        isinstance(command, list) and command and all(isinstance(s, str) and s for s in command),
        "Arm command must be nonempty argv, not a shell string",
    )
    command = [s.replace("{repo}", str(REPO)) for s in command]
    executable = shutil.which(command[0])
    require(executable is not None, "Adapter executable is unavailable")
    # Preserve the venv entry-point path. Resolving its symlink to the base
    # interpreter silently discards that environment and its scientific packages.
    command[0] = os.path.abspath(executable)
    validate_adapter_launch(command)
    chosen = plan["units"]
    if selected_units is not None:
        require(
            bool(selected_units) and len(selected_units) == len(set(selected_units)),
            "Selected units must be nonempty and unique",
        )
        require(set(selected_units) <= {u["unit_id"] for u in chosen}, "Unknown selected unit")
        chosen = [u for u in chosen if u["unit_id"] in selected_units]
    require(isinstance(arm.get("config"), dict) and bool(arm.get("model_id")), "Missing arm config")
    reject_reference_fields(arm["config"])
    require(bool(arm.get("code_paths")), "Adapter source provenance is required")
    code = [{"path": command[0], "sha256": file_digest(Path(command[0]))}]
    if len(command) > 1 and command[1].endswith(".py"):
        require(
            Path(command[1]).is_absolute(), "Adapter script path must be absolute or use {repo}"
        )
        code.append({"path": command[1], "sha256": file_digest(Path(command[1]))})
    for name in arm["code_paths"]:
        path = Path(name.replace("{repo}", str(REPO)))
        path = (arm_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
        code.append({"path": str(path), "sha256": file_digest(path)})
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name, obj in (("plan.json", plan), ("inputs.json", inputs), ("arm.json", arm)):
        write_json(output / name, obj)
    started, deadline = time.monotonic(), time.monotonic() + max_seconds
    started_utc = datetime.now(UTC).isoformat()
    captures = {r["session_id"]: r for r in plan["captures"]}
    by_id = {r["session_id"]: r for r in inputs["captures"]}
    results = []
    for unit in chosen:
        before = time.monotonic()
        result = {"schema": "ds7-response/v1", "unit_id": unit["unit_id"], "status": "unavailable"}
        missing = [sid for sid in unit["session_ids"] if by_id[sid]["state"] != "ready"]
        evidence = {}
        if missing:
            result["reason"] = "unavailable_inputs"
            result["missing_session_ids"] = missing
        elif before >= deadline:
            result["status"], result["reason"] = "failed", "run_budget_exhausted"
        else:
            directory = output / unit["unit_id"]
            directory.mkdir()
            request = {
                "schema": "ds7-request/v1",
                "dataset_sha256": DS7_SHA256,
                "plan_sha256": plan["content_sha256"],
                "inputs_sha256": inputs["content_sha256"],
                "model_id": arm["model_id"],
                "config": arm["config"],
                "unit": unit,
                "captures": [captures[s] for s in unit["session_ids"]],
                "inputs": [by_id[s] for s in unit["session_ids"]],
            }
            write_json(directory / "request.json", request)
            evidence["request_sha256"] = file_digest(directory / "request.json")
            evidence["response_validated"] = False
            try:
                execute(
                    command,
                    directory / "request.json",
                    directory / "response.json",
                    min(unit_seconds, deadline - before),
                    directory / "adapter.log",
                )
                require(
                    (directory / "response.json").stat().st_size <= 1024 * 1024,
                    "Response exceeds 1 MiB",
                )
                result = validate_response(read_json(directory / "response.json"), unit["unit_id"])
                evidence["response_validated"] = True
            except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
                result = {
                    "schema": "ds7-response/v1",
                    "unit_id": unit["unit_id"],
                    "status": "failed",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            require(
                file_digest(directory / "request.json") == evidence["request_sha256"],
                "Adapter modified its request; run cannot be sealed",
            )
            require(
                all(
                    p.name in {"request.json", "response.json", "adapter.log"}
                    and p.is_file()
                    and not p.is_symlink()
                    for p in directory.iterdir()
                ),
                "Unexpected adapter outputs",
            )
            evidence["files"] = {p.name: file_digest(p) for p in directory.iterdir()}
        results.append(
            {
                "unit": unit,
                "response": result,
                "evidence": evidence,
                "elapsed_seconds": time.monotonic() - before,
            }
        )
    # Detect in-place changes during execution before the run is eligible for scoring.
    check_inputs(inputs, plan)
    require(all(file_digest(Path(c["path"])) == c["sha256"] for c in code), "Adapter code changed")
    for trial in results:
        for name, expected in trial["evidence"].get("files", {}).items():
            require(
                file_digest(output / trial["unit"]["unit_id"] / name) == expected,
                "Previously recorded unit evidence changed",
            )
    receipt = {
        "schema": "ds7-run/v1",
        "dataset_sha256": DS7_SHA256,
        "plan_sha256": plan["content_sha256"],
        "inputs_sha256": inputs["content_sha256"],
        "arm_sha256": digest(canonical(arm)),
        "model_id": arm["model_id"],
        "resolved_command": command,
        "selected_unit_ids": [u["unit_id"] for u in chosen],
        "code": code,
        "python": platform.python_version(),
        "runner_sha256": file_digest(Path(__file__)),
        "started_utc": started_utc,
        "sealed_utc": datetime.now(UTC).isoformat(),
        "elapsed_seconds": time.monotonic() - started,
        "max_seconds": max_seconds,
        "unit_seconds": unit_seconds,
        "results": results,
    }
    write_json(output / "results.json", receipt)
    seal_run(output)
    return {"run": str(output), "states": dict(Counter(r["response"]["status"] for r in results))}


def horizontal_error_m(lat: float, lon: float, ref_lat: float, ref_lon: float) -> float:
    # Explicit common metric: mean-Earth-radius great-circle horizontal distance.
    a, b = math.radians(lat), math.radians(ref_lat)
    h = (
        math.sin((a - b) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(lon - ref_lon) / 2) ** 2
    )
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    at = (len(ordered) - 1) * fraction
    low = int(at)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (at - low)


def summarize(rows: list[dict]) -> dict:
    errors = [r["horizontal_error_m"] for r in rows if r["qualified"]]
    radii = [r for r in rows if r["qualified"] and r["inside_reported_95_radius"] is not None]
    return {
        "attempted": len(rows),
        "qualified": len(errors),
        "states": dict(Counter(r["status"] for r in rows)),
        "unconverged_count": sum(r["status"] == "ok" and not r["converged"] for r in rows),
        "boundary_count": sum(r["status"] == "ok" and r["boundary_hit"] for r in rows),
        "availability": len(errors) / len(rows),
        "fraction_below_1km_all_attempts": sum(e < 1000 for e in errors) / len(rows),
        "fraction_below_1km_qualified": sum(e < 1000 for e in errors) / len(errors)
        if errors
        else None,
        "median_m": quantile(errors, 0.5),
        "p90_m": quantile(errors, 0.9),
        "p95_m": quantile(errors, 0.95),
        "max_m": max(errors) if errors else None,
        "uncertainty_reported_count": len(radii),
        "reported_95_radius_coverage": sum(r["inside_reported_95_radius"] for r in radii)
        / len(radii)
        if radii
        else None,
    }


def evaluate(dataset: Path, run_root: Path, output: Path) -> dict:
    m, units = load_dataset(dataset)
    seal = read_sealed(run_root / "seal.json", "ds7-run-seal/v1")
    actual = {str(p.relative_to(run_root)) for p in run_root.rglob("*") if p.is_file()}
    require(actual == set(seal["files"]) | {"seal.json"}, "Run inventory changed")
    for name, expected in seal["files"].items():
        require(
            file_digest(safe_relative(run_root, name)) == expected, f"Run artifact changed: {name}"
        )
    receipt, plan = (
        read_json(run_root / "results.json"),
        read_sealed(run_root / "plan.json", "ds7-plan/v1"),
    )
    require(plan == make_plan(m, units, plan["suite"]), "Run plan differs from frozen policy")
    require(
        receipt["schema"] == "ds7-run/v1" and receipt["dataset_sha256"] == DS7_SHA256,
        "Wrong run dataset",
    )
    require(receipt["plan_sha256"] == plan["content_sha256"], "Run plan binding mismatch")
    require(
        receipt["inputs_sha256"]
        == read_sealed(run_root / "inputs.json", "ds7-inputs/v1")["content_sha256"],
        "Run input binding mismatch",
    )
    require(
        receipt["arm_sha256"] == digest(canonical(read_json(run_root / "arm.json"))),
        "Run arm mismatch",
    )
    arm = read_json(run_root / "arm.json")
    frozen_inputs = read_sealed(run_root / "inputs.json", "ds7-inputs/v1")
    input_rows = {r["session_id"]: r for r in frozen_inputs["captures"]}
    plan_rows = {r["session_id"]: r for r in plan["captures"]}
    selected = receipt["selected_unit_ids"]
    require(
        bool(selected)
        and len(selected) == len(set(selected))
        and set(selected) <= {u["unit_id"] for u in plan["units"]},
        "Invalid selected units",
    )
    chosen = [u for u in plan["units"] if u["unit_id"] in selected]
    require([u["unit_id"] for u in chosen] == selected, "Selected units are out of order")
    require([r["unit"] for r in receipt["results"]] == chosen, "Missing or reordered trials")
    authority = read_json(dataset / "pose-authority.json")
    captures = {r["session_id"]: r for r in m["captures"]}
    scored = []
    for trial in receipt["results"]:
        unit = trial["unit"]
        evidence = trial["evidence"]
        if evidence:
            directory = run_root / unit["unit_id"]
            for name, expected in evidence["files"].items():
                require(
                    file_digest(safe_relative(directory, name)) == expected, "Unit evidence changed"
                )
            request = read_json(directory / "request.json")
            require(
                file_digest(directory / "request.json") == evidence["request_sha256"],
                "Request changed",
            )
            require(
                request["unit"] == unit
                and request["plan_sha256"] == plan["content_sha256"]
                and request["inputs_sha256"] == receipt["inputs_sha256"],
                "Request binding mismatch",
            )
            require(
                request["dataset_sha256"] == DS7_SHA256
                and request["model_id"] == arm["model_id"]
                and request["config"] == arm["config"]
                and request["captures"] == [plan_rows[s] for s in unit["session_ids"]]
                and request["inputs"] == [input_rows[s] for s in unit["session_ids"]],
                "Request differs from frozen model inputs",
            )
            if evidence["response_validated"]:
                require(
                    read_json(directory / "response.json") == trial["response"],
                    "Response differs from receipt",
                )
        r = validate_response(trial["response"], unit["unit_id"])
        qualified = r["status"] == "ok" and r["converged"] and not r["boundary_hit"]
        error = None
        if r["status"] == "ok":
            estimate = r["estimate"]
            error = horizontal_error_m(
                estimate["latitude_deg"],
                estimate["longitude_deg"],
                authority["latitude_deg"],
                authority["longitude_deg"],
            )
        start = min(captures[s]["capture_start_utc_ns"] for s in unit["session_ids"])
        end = max(captures[s]["capture_end_utc_ns"] for s in unit["session_ids"])
        radius = r.get("horizontal_radius_95_m")
        scored.append(
            {
                "unit_id": unit["unit_id"],
                "kind": unit["kind"],
                "status": r["status"],
                "qualified": qualified,
                "horizontal_error_m": error,
                "reason": r.get("reason"),
                "converged": r.get("converged"),
                "boundary_hit": r.get("boundary_hit"),
                "elapsed_seconds": trial["elapsed_seconds"],
                "capture_span_seconds": (end - start) / 1e9,
                "sample_rate_hz": captures[unit["session_ids"][0]]["sample_rate_hz"]
                if unit["kind"] == "single"
                else None,
                "inside_reported_95_radius": error <= radius
                if error is not None and radius is not None
                else None,
            }
        )
    report = {
        "schema": "ds7-score/v1",
        "dataset_sha256": DS7_SHA256,
        "run_seal_sha256": file_digest(run_root / "seal.json"),
        "plan_sha256": receipt["plan_sha256"],
        "inputs_sha256": receipt["inputs_sha256"],
        "arm_sha256": receipt["arm_sha256"],
        "evaluator_sha256": file_digest(Path(__file__)),
        "scored_utc": datetime.now(UTC).isoformat(),
        "pose_authority_sha256": m["pose_authority_file_sha256"],
        "model_id": receipt["model_id"],
        "selected_unit_ids": selected,
        "plan_unit_count": len(plan["units"]),
        "metric": "great_circle_horizontal_mean_earth_radius_6371008.8m",
        "reference_status": "operator supplied; unsurveyed; altitude and uncertainty unknown",
        "exposure_status": m["prior_exposure_status"],
        "grouping_warning": (
            "Overlapping budgets and single-site windows are not independent trials"
        ),
        "by_kind": {
            kind: summarize([r for r in scored if r["kind"] == kind])
            for kind in sorted({r["kind"] for r in scored})
        },
        "trials": scored,
        "singles_by_rate": {
            str(rate): summarize([r for r in scored if r["sample_rate_hz"] == rate])
            for rate in sorted({r["sample_rate_hz"] for r in scored if r["kind"] == "single"})
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "scores.json", seal_object(report))
    lines = [
        "# DS7 evaluation",
        "",
        f"Model: `{receipt['model_id']}`. Reference: operator supplied, unsurveyed.",
        "",
        "| Unit kind | Qualified / attempted | Median m | p90 m | <1 km / all attempts |",
        "|---|---:|---:|---:|---:|",
    ]
    for kind, s in report["by_kind"].items():
        lines.append(
            f"| {kind} | {s['qualified']} / {s['attempted']} | {s['median_m']} | "
            f"{s['p90_m']} | {s['fraction_below_1km_all_attempts']:.3f} |"
        )
    lines += [
        "",
        "Error summaries use converged interior estimates. "
        "Failures/abstentions remain in the all-attempt denominator.",
        "Unqualified returned positions remain visible in scores.json. "
        "No independent-site generalization claim.",
    ]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    seal_run(output)
    return {"scores": str(output / "scores.json"), "by_kind": report["by_kind"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    prep = sub.add_parser("prepare")
    prep.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--suite", choices=("smoke", "standard", "budgets"), default="standard")
    freeze = sub.add_parser("freeze-inputs")
    freeze.add_argument("--plan", type=Path, required=True)
    freeze.add_argument("--index", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    launch = sub.add_parser("run")
    for name in ("plan", "inputs", "arm", "output"):
        launch.add_argument("--" + name, type=Path, required=True)
    launch.add_argument("--max-seconds", type=float, default=300)
    launch.add_argument("--unit-seconds", type=float, default=60)
    launch.add_argument("--unit", action="append", help="Exact frozen unit ID; repeat for a panel")
    launch.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    score = sub.add_parser("evaluate")
    score.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    score.add_argument("--run", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            m, units = load_dataset(args.dataset)
            result = {
                "dataset_id": "DS7",
                "manifest_sha256": DS7_SHA256,
                "counts": m["counts"],
                "groups_of_8": len(units["groups_of_8"]),
                "source_verification": m["integrity_scope"],
            }
        elif args.action == "prepare":
            result = prepare(args.dataset, args.output, args.suite)
        elif args.action == "freeze-inputs":
            result = freeze_inputs(args.plan, args.index, args.output, args.dataset)
        elif args.action == "run":
            result = run(
                args.plan,
                args.inputs,
                args.arm,
                args.output,
                args.max_seconds,
                args.unit_seconds,
                args.unit,
                args.dataset,
            )
        else:
            result = evaluate(args.dataset, args.run, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"DS7 evaluation error: {exc}\n")


if __name__ == "__main__":
    main()
