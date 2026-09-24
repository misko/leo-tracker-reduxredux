#!/usr/bin/env python3
"""Cached, checkpointed, reference-free consistent-cap800 geographic runner."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import io
import json
import math
import multiprocessing
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import numpy as np
from scipy.optimize import minimize

SCHEMA = "consistent-cap800-frozen-run/v1"
CAP_HZ = 800.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUND_S_H = 0.25
ROBUST_SCALE_HZ = 250.0
MAX_ITERATIONS = 300


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, payload: bytes) -> None:
    """Durably replace one regular file without exposing partial bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def manifest_digest(document: dict[str, Any]) -> str:
    return sha256_bytes(canonical(document))


def validate_manifest(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text())
    if document.get("schema") != SCHEMA:
        raise ValueError(f"manifest schema must be {SCHEMA}")
    if document.get("reference_used_for_fit") is not False:
        raise ValueError("run manifest must explicitly exclude the geographic reference")
    dataset = document.get("dataset_manifest", {})
    dataset_path = Path(str(dataset.get("path", "")))
    if not dataset_path.is_absolute():
        dataset_path = (path.parent / dataset_path).resolve()
    if not dataset_path.is_file() or digest(dataset_path) != dataset.get("sha256"):
        raise ValueError("frozen dataset manifest is missing or has changed")
    frozen = json.loads(dataset_path.read_text())
    groups = document.get("groups")
    if not isinstance(groups, list) or len(groups) < 2:
        raise ValueError("at least two independent groups are required")
    identifiers = [str(group.get("group_id")) for group in groups]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("group identifiers must be unique")
    weights = [float(group.get("weight", 0.0)) for group in groups]
    if any(weight <= 0 for weight in weights) or not math.isclose(sum(weights), 1.0, abs_tol=1e-12):
        raise ValueError("positive group weights must sum to one")
    sessions = {
        str(scan["session_id"]): scan for scan in frozen.get("scans", []) if "session_id" in scan
    }
    seen_sessions: set[str] = set()
    for group in groups:
        task = group.get("task")
        if not isinstance(task, dict) or not task.get("session_ids"):
            raise ValueError("each group must embed one frozen full-observation task")
        for session_id in map(str, task["session_ids"]):
            if session_id in seen_sessions:
                raise ValueError("whole sessions cannot occur in more than one group")
            seen_sessions.add(session_id)
            if sessions:
                scan = sessions.get(session_id)
                if scan is None or scan.get("inclusion", {}).get("analysis_ready") is not True:
                    raise ValueError(
                        f"session is not analysis-ready in frozen inventory: {session_id}"
                    )
    taus = document.get("tau_grid_s")
    levels = document.get("levels_km")
    seeds = document.get("seeds")
    if (
        not isinstance(taus, list)
        or len(taus) < 2
        or sorted(map(float, taus)) != list(map(float, taus))
    ):
        raise ValueError("tau grid must contain at least two increasing values")
    if not isinstance(levels, list) or not levels or any(float(value) <= 0 for value in levels):
        raise ValueError("levels_km must be a nonempty positive list")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("a predeclared reference-free seed set is required")
    for key in ("top_basins", "top_taus_per_group", "exact_top_coordinates"):
        if int(document.get(key, 0)) <= 0:
            raise ValueError(f"{key} must be positive")
    for name in ("joint", "runner", "orbit"):
        module_path = Path(str(document.get("modules", {}).get(name, "")))
        if not module_path.is_absolute():
            module_path = (path.parent / module_path).resolve()
        if not module_path.is_file():
            raise ValueError(f"missing module path: {name}")
        document["modules"][name] = str(module_path)
    cache_root = Path(str(document.get("portable_cache_root", "")))
    if not cache_root.is_dir():
        raise ValueError("portable_cache_root must name an existing DS2 cache directory")
    document["portable_cache_root"] = str(cache_root.resolve())
    document["dataset_manifest"]["path"] = str(dataset_path)
    document["manifest_sha256"] = manifest_digest(
        {key: value for key, value in document.items() if key != "manifest_sha256"}
    )
    return document


def inventory_preflight(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text())
    scans = document.get("scans", [])
    ready = [
        str(scan["session_id"])
        for scan in scans
        if scan.get("inclusion", {}).get("analysis_ready") is True
    ]
    return {
        "schema": "consistent-cap800-inventory-preflight/v1",
        "inventory_path": str(path),
        "inventory_sha256": digest(path),
        "analysis_ready_session_count": len(ready),
        "analysis_ready_session_ids": ready,
        "launchable": len(ready) >= 2,
        "reason": None if len(ready) >= 2 else "fewer than two analysis-ready whole sessions",
    }


def coordinate_key(point: dict[str, Any]) -> tuple[float, float]:
    return round(float(point["latitude_deg"]), 10), round(float(point["longitude_deg"]), 10)


def cache_identity(
    config_digest: str, group_id: str, point: dict[str, Any], tau_s: float
) -> dict[str, Any]:
    return {
        "config_sha256": config_digest,
        "group_id": group_id,
        "latitude_deg": f"{float(point['latitude_deg']):.10f}",
        "longitude_deg": f"{float(point['longitude_deg']):.10f}",
        "tau_s": f"{float(tau_s):.9f}",
    }


class SupportStore:
    """Digest-bound atomic cache for one completed geographic/tau hard support."""

    def __init__(self, root: Path):
        self.root = root

    def paths(self, identity: dict[str, Any]) -> tuple[Path, Path]:
        name = hashlib.sha256(canonical(identity)).hexdigest()
        directory = self.root / "supports" / name[:2]
        return directory / f"{name}.npz", directory / f"{name}.json"

    def get(self, identity: dict[str, Any]) -> SimpleNamespace | None:
        data_path, receipt_path = self.paths(identity)
        if not data_path.is_file() or not receipt_path.is_file():
            return None
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("identity") != identity or receipt.get("data_sha256") != digest(data_path):
            raise ValueError("support cache receipt or payload disagrees")
        with np.load(data_path, allow_pickle=False) as arrays:
            return SimpleNamespace(
                measured=arrays["measured"],
                nominal=arrays["nominal"],
                sensitivity_hz_s=arrays["sensitivity_hz_s"],
                age_h=arrays["age_h"],
                source=arrays["source"].astype(str),
                track=arrays["track"].astype(str),
                weights={str(key): int(value) for key, value in receipt["weights"].items()},
                associations=list(receipt["associations"]),
            )

    def put(self, identity: dict[str, Any], support: Any) -> SimpleNamespace:
        existing = self.get(identity)
        if existing is not None:
            return existing
        data_path, receipt_path = self.paths(identity)
        payload = io.BytesIO()
        np.savez_compressed(
            payload,
            measured=np.asarray(support.measured),
            nominal=np.asarray(support.nominal),
            sensitivity_hz_s=np.asarray(support.sensitivity_hz_s),
            age_h=np.asarray(support.age_h),
            source=np.asarray(support.source, dtype=str),
            track=np.asarray(support.track, dtype=str),
        )
        data = payload.getvalue()
        atomic_write(data_path, data)
        receipt = {
            "schema": "consistent-cap800-support-cache/v1",
            "identity": identity,
            "data_sha256": sha256_bytes(data),
            "weights": {str(key): int(value) for key, value in support.weights.items()},
            "associations": list(support.associations),
        }
        atomic_write(receipt_path, canonical(receipt))
        loaded = self.get(identity)
        if loaded is None:
            raise RuntimeError("support cache write did not become readable")
        return loaded


class CheckpointStore:
    """Atomic immutable levels plus one replaceable, digest-bound pointer."""

    def __init__(self, root: Path, config_digest: str):
        self.root = root
        self.config_digest = config_digest

    def level_path(self, level: int) -> Path:
        return self.root / "levels" / f"level-{level:03d}.json"

    def write_level(self, level: int, document: dict[str, Any]) -> Path:
        payload = {
            "schema": "consistent-cap800-level/v1",
            "config_sha256": self.config_digest,
            "level": level,
            **document,
        }
        path = self.level_path(level)
        encoded = canonical(payload)
        if path.exists():
            if path.read_bytes() != encoded:
                raise ValueError("completed level cannot be overwritten with different bytes")
        else:
            atomic_write(path, encoded)
        pointer = {
            "schema": "consistent-cap800-checkpoint/v1",
            "config_sha256": self.config_digest,
            "last_complete_level": level,
            "level_path": str(path),
            "level_sha256": digest(path),
        }
        atomic_write(self.root / "checkpoint.json", canonical(pointer))
        return path

    def completed(self) -> list[dict[str, Any]]:
        pointer_path = self.root / "checkpoint.json"
        if not pointer_path.exists():
            return []
        pointer = json.loads(pointer_path.read_text())
        if pointer.get("config_sha256") != self.config_digest:
            raise ValueError("checkpoint belongs to a different frozen run")
        maximum = int(pointer["last_complete_level"])
        levels = []
        for level in range(maximum + 1):
            path = self.level_path(level)
            document = json.loads(path.read_text())
            if (
                document.get("config_sha256") != self.config_digest
                or document.get("level") != level
            ):
                raise ValueError("level checkpoint binding disagrees")
            levels.append(document)
        if digest(self.level_path(maximum)) != pointer.get("level_sha256"):
            raise ValueError("checkpoint pointer digest disagrees")
        return levels


def _labels(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.unique(values.astype(str), return_inverse=True)


def profile_cap800(support: Any, initial: dict[str, float] | None = None) -> dict[str, Any]:
    """Fit regularized nuisance rates; select only with the cap-800 loss."""
    sources, source_index = _labels(support.source)
    tracks, track_index = _labels(support.track)
    raw = support.measured - support.nominal
    feature = support.sensitivity_hz_s * support.age_h
    design = np.zeros((len(raw), len(sources)), dtype=float)
    design[np.arange(len(raw)), source_index] = feature
    centered_y, centered_x = raw.copy(), design.copy()
    for index in range(len(tracks)):
        rows = track_index == index
        centered_y[rows] -= np.mean(centered_y[rows])
        centered_x[rows] -= np.mean(centered_x[rows], axis=0)
    initial = initial or {}
    x0 = np.asarray([initial.get(str(source), 0.0) for source in sources], dtype=float)

    def objective(rate: np.ndarray) -> float:
        error = centered_y - centered_x @ rate
        z = error / ROBUST_SCALE_HZ
        return float(
            np.sum(np.sqrt(1.0 + z * z) - 1.0) + 0.5 * np.sum((rate / RATE_SIGMA_S_H) ** 2)
        )

    def gradient(rate: np.ndarray) -> np.ndarray:
        error = centered_y - centered_x @ rate
        derivative = error / (ROBUST_SCALE_HZ**2 * np.sqrt(1.0 + (error / ROBUST_SCALE_HZ) ** 2))
        return -centered_x.T @ derivative + rate / RATE_SIGMA_S_H**2

    optimized = minimize(
        objective,
        x0,
        jac=gradient,
        method="L-BFGS-B",
        bounds=[(-RATE_BOUND_S_H, RATE_BOUND_S_H)] * len(sources),
        options={"maxiter": MAX_ITERATIONS, "ftol": 1e-11, "gtol": 1e-7},
    )

    def evaluate(rate: np.ndarray) -> tuple[float, np.ndarray]:
        residual = raw - feature * rate[source_index]
        cfo = np.asarray([np.mean(residual[track_index == index]) for index in range(len(tracks))])
        error = residual - cfo[track_index]
        loss = sum(
            support.weights[str(name)]
            * min(
                (float(np.sqrt(np.mean(error[track_index == index] ** 2))) / CAP_HZ) ** 2,
                1.0,
            )
            for index, name in enumerate(tracks)
        ) / sum(support.weights.values())
        return float(loss), cfo

    rates = np.asarray(optimized.x, dtype=float)
    loss, cfo = evaluate(rates)
    null_loss, null_cfo = evaluate(np.zeros_like(rates))
    rejected = loss > null_loss + 1e-12
    if rejected:
        rates = np.zeros_like(rates)
        loss, cfo = null_loss, null_cfo
    return {
        "selection_objective": loss,
        "full_observation_capped_loss": loss,
        "full_observation_capped_rms_hz": CAP_HZ * math.sqrt(loss),
        "null_rate_full_observation_capped_loss": null_loss,
        "rate_fit_rejected_by_full_observation_loss": rejected,
        "converged": bool(optimized.success),
        "iterations": int(optimized.nit),
        "message": str(optimized.message),
        "initial_rate_count": len(initial),
        "rate_corrections_s_h": {
            str(name): float(value) for name, value in zip(sources, rates, strict=True)
        },
        "rate_boundary_count": int(np.sum(np.abs(rates) >= RATE_BOUND_S_H - 1e-8)),
        "track_cfo_hz": {str(name): float(value) for name, value in zip(tracks, cfo, strict=True)},
    }


def offset_coordinate(
    center: dict[str, float], east_km: float, north_km: float
) -> dict[str, float]:
    return {
        "latitude_deg": float(center["latitude_deg"]) + north_km / 111.32,
        "longitude_deg": float(center["longitude_deg"])
        + east_km / (111.32 * math.cos(math.radians(float(center["latitude_deg"])))),
    }


def local_offsets(point: dict[str, Any], origin: dict[str, float]) -> tuple[float, float]:
    east = (
        (float(point["longitude_deg"]) - float(origin["longitude_deg"]))
        * 111.32
        * math.cos(math.radians(float(origin["latitude_deg"])))
    )
    north = (float(point["latitude_deg"]) - float(origin["latitude_deg"])) * 111.32
    return east, north


def lattice(
    parents: list[dict[str, float]], spacing_km: float, origin: dict[str, float]
) -> list[dict[str, float]]:
    points = {}
    for parent in parents:
        for north in (-spacing_km, 0.0, spacing_km):
            for east in (-spacing_km, 0.0, spacing_km):
                point = offset_coordinate(parent, east, north)
                local_east, local_north = local_offsets(point, origin)
                point.update(
                    {"east_km_from_origin": local_east, "north_km_from_origin": local_north}
                )
                points[coordinate_key(point)] = point
    return list(points.values())


def group_by_id(config: dict[str, Any], group_id: str) -> dict[str, Any]:
    return next(group for group in config["groups"] if str(group["group_id"]) == group_id)


def _cache_json(root: Path, family: str, identity: dict[str, Any]) -> Path:
    name = hashlib.sha256(canonical(identity)).hexdigest()
    return root / family / name[:2] / f"{name}.json"


def _load_cached_json(path: Path, identity: dict[str, Any]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    document = json.loads(path.read_text())
    if document.get("identity") != identity:
        raise ValueError(f"cached artifact binding disagrees: {path}")
    return document["value"]


def _write_cached_json(path: Path, identity: dict[str, Any], value: dict[str, Any]) -> None:
    payload = {
        "schema": "consistent-cap800-cached-json/v1",
        "identity": identity,
        "value": value,
    }
    encoded = canonical(payload)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError(f"cached artifact is immutable: {path}")
        return
    atomic_write(path, encoded)


def scan_coordinate(
    task: tuple[str, str, str, dict[str, float], dict[str, dict[str, float]]],
) -> dict[str, Any]:
    manifest_path_text, work_root_text, group_id, point, parent_warm = task
    config = validate_manifest(Path(manifest_path_text))
    work_root = Path(work_root_text)
    group = group_by_id(config, group_id)
    joint = load_module(Path(config["modules"]["joint"]), f"cc8_joint_{os.getpid()}")
    existing = load_module(Path(config["modules"]["runner"]), f"cc8_runner_{os.getpid()}")
    # The reviewed full-observation engine normally knows only the two DS1
    # cache namespaces.  A frozen DS2 manifest binds a separate read-only
    # cache root, so expose it through the engine's narrow cache port before
    # validating the embedded task.
    existing.CACHE_ROOTS.clear()
    existing.CACHE_ROOTS["ds2"] = Path(config["portable_cache_root"])
    orbit = load_module(Path(config["modules"]["orbit"]), f"cc8_orbit_{os.getpid()}")
    normalized_task = dict(group["task"])
    normalized_task["output_path"] = str(work_root / "unused.json")
    engine = existing.FullObservationEngine(existing.validate_task(normalized_task))
    support_store = SupportStore(work_root)
    previous: dict[str, float] = {}
    rows = []
    begun = time.perf_counter()
    for tau in map(float, config["tau_grid_s"]):
        identity = cache_identity(config["manifest_sha256"], group_id, point, tau)
        support = support_store.get(identity)
        support_hit = support is not None
        if support is None:
            support = support_store.put(
                identity,
                joint.hard_support(
                    engine,
                    orbit,
                    float(point["latitude_deg"]),
                    float(point["longitude_deg"]),
                    tau,
                ),
            )
        warm = parent_warm.get(f"{tau:.9f}", previous)
        fit_identity = {
            "support": identity,
            "warm_start_sha256": sha256_bytes(canonical(warm)),
            "profile": "regularized-pseudohuber-rate-cap800-selection/v1",
        }
        fit_path = _cache_json(work_root, "fits", fit_identity)
        fit = _load_cached_json(fit_path, fit_identity)
        fit_hit = fit is not None
        if fit is None:
            fit = profile_cap800(support, warm)
            _write_cached_json(fit_path, fit_identity, fit)
        previous = dict(fit["rate_corrections_s_h"])
        rows.append(
            {
                "tau_s": tau,
                "fit": fit,
                "support_cache_hit": support_hit,
                "fit_cache_hit": fit_hit,
                "warm_start_kind": "parent_location"
                if parent_warm.get(f"{tau:.9f}")
                else ("adjacent_tau" if warm else "zero"),
            }
        )
    return {
        **point,
        "group_id": group_id,
        "rows": rows,
        "elapsed_s": time.perf_counter() - begun,
    }


def proposal_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["fit"]["selection_objective"]),
        abs(float(row["tau_s"])),
        float(row["tau_s"]),
    )


def combine(
    config: dict[str, Any], points: list[dict[str, float]], scans: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    top_taus = int(config["top_taus_per_group"])
    output = []
    for point in points:
        per_group = {}
        balanced = 0.0
        for group in config["groups"]:
            group_id = str(group["group_id"])
            scan = next(
                row
                for row in scans
                if row["group_id"] == group_id and coordinate_key(row) == coordinate_key(point)
            )
            eligible = sorted(
                (row for row in scan["rows"] if row["fit"]["converged"]), key=proposal_key
            )
            if len(eligible) < top_taus:
                raise ValueError(f"insufficient converged tau proposals: {group_id} {point}")
            per_group[group_id] = eligible[:top_taus]
            balanced += float(group["weight"]) * eligible[0]["fit"]["selection_objective"]
        output.append(
            {
                **point,
                "balanced_proposal_objective": balanced,
                "group_weighting": {
                    str(group["group_id"]): float(group["weight"]) for group in config["groups"]
                },
                "proposal_taus": per_group,
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["balanced_proposal_objective"],
            row["north_km_from_origin"],
            row["east_km_from_origin"],
        ),
    )


def nearest_parent_warm(
    point: dict[str, float], group_id: str, prior_level: dict[str, Any] | None
) -> dict[str, dict[str, float]]:
    if prior_level is None:
        return {}
    retained = prior_level["retained_basins"]
    parent = min(
        retained,
        key=lambda row: (
            (float(row["latitude_deg"]) - float(point["latitude_deg"])) ** 2
            + (float(row["longitude_deg"]) - float(point["longitude_deg"])) ** 2
        ),
    )
    scan = next(
        row
        for row in prior_level["proposal_scans"]
        if row["group_id"] == group_id and coordinate_key(row) == coordinate_key(parent)
    )
    return {
        f"{float(row['tau_s']):.9f}": dict(row["fit"]["rate_corrections_s_h"])
        for row in scan["rows"]
        if row["fit"]["converged"]
    }


def exact_audit(task: tuple[str, str, str, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    manifest_path_text, work_root_text, group_id, point, proposal = task
    config = validate_manifest(Path(manifest_path_text))
    work_root = Path(work_root_text)
    identity = {
        "config_sha256": config["manifest_sha256"],
        "group_id": group_id,
        "latitude_deg": f"{float(point['latitude_deg']):.10f}",
        "longitude_deg": f"{float(point['longitude_deg']):.10f}",
        "tau_s": f"{float(proposal['tau_s']):.9f}",
        "stage": "exact-sgp4",
    }
    path = _cache_json(work_root, "exact", identity)
    cached = _load_cached_json(path, identity)
    if cached is not None:
        cached["exact_cache_hit"] = True
        return cached
    group = group_by_id(config, group_id)
    joint = load_module(Path(config["modules"]["joint"]), f"cc8_exact_joint_{os.getpid()}")
    existing = load_module(Path(config["modules"]["runner"]), f"cc8_exact_runner_{os.getpid()}")
    existing.CACHE_ROOTS.clear()
    existing.CACHE_ROOTS["ds2"] = Path(config["portable_cache_root"])
    orbit = load_module(Path(config["modules"]["orbit"]), f"cc8_exact_orbit_{os.getpid()}")
    normalized_task = dict(group["task"])
    normalized_task["output_path"] = str(work_root / "unused.json")
    engine = existing.FullObservationEngine(existing.validate_task(normalized_task))
    screened = joint.screen_point(
        engine,
        orbit,
        float(point["latitude_deg"]),
        float(point["longitude_deg"]),
        float(proposal["tau_s"]),
        False,
    )
    result = {
        **{key: point[key] for key in point if key != "proposal_taus"},
        "group_id": group_id,
        "tau_s": proposal["tau_s"],
        "cap800_proposal_fit": proposal["fit"],
        "track_associations": screened["track_associations"],
        "exact_comparison": joint.exact_comparison(existing, orbit, engine, screened),
        "exact_cache_hit": False,
    }
    _write_cached_json(path, identity, result)
    return result


def select_exact(
    config: dict[str, Any], audits: list[dict[str, Any]], finalists: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for point in finalists:
        per_group = {}
        balanced = 0.0
        for group in config["groups"]:
            group_id = str(group["group_id"])
            options = [
                row
                for row in audits
                if row["group_id"] == group_id and coordinate_key(row) == coordinate_key(point)
            ]
            if len(options) != int(config["top_taus_per_group"]) or not all(
                row["exact_comparison"]["exact_sgp4_gate"]["passed"] for row in options
            ):
                raise ValueError("exact audit is incomplete or failed its replay gate")
            winner = min(
                options,
                key=lambda row: (
                    row["exact_comparison"]["exact_full_observation_capped_loss"],
                    abs(float(row["tau_s"])),
                    float(row["tau_s"]),
                ),
            )
            per_group[group_id] = winner
            balanced += (
                float(group["weight"])
                * winner["exact_comparison"]["exact_full_observation_capped_loss"]
            )
        rows.append(
            {
                **{
                    key: point[key]
                    for key in (
                        "latitude_deg",
                        "longitude_deg",
                        "east_km_from_origin",
                        "north_km_from_origin",
                        "balanced_proposal_objective",
                    )
                },
                "balanced_exact_capped_loss": balanced,
                "best_exact_by_group": per_group,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["balanced_exact_capped_loss"],
            row["north_km_from_origin"],
            row["east_km_from_origin"],
        ),
    )


def initialize_work_root(root: Path, config: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "frozen-run.json"
    payload = canonical(
        {
            "schema": "consistent-cap800-work-root/v1",
            "config_sha256": config["manifest_sha256"],
            "dataset_manifest": config["dataset_manifest"],
        }
    )
    if marker.exists() and marker.read_bytes() != payload:
        raise ValueError("work root is already bound to a different frozen run")
    if not marker.exists():
        atomic_write(marker, payload)


def execute(manifest_path: Path, work_root: Path, output: Path, workers: int) -> dict[str, Any]:
    if not 1 <= workers <= 16:
        raise ValueError("workers must be 1..16")
    config = validate_manifest(manifest_path)
    initialize_work_root(work_root, config)
    if output.exists():
        existing = json.loads(output.read_text())
        if (
            existing.get("complete") is True
            and existing.get("config_sha256") == config["manifest_sha256"]
        ):
            return existing
        raise ValueError("output exists but is not this completed frozen run")
    checkpoints = CheckpointStore(work_root, config["manifest_sha256"])
    levels = checkpoints.completed()
    origin = {
        "latitude_deg": float(config["origin"]["latitude_deg"]),
        "longitude_deg": float(config["origin"]["longitude_deg"]),
    }
    prior_level = levels[-1] if levels else None
    parents = (
        [
            {
                "latitude_deg": float(row["latitude_deg"]),
                "longitude_deg": float(row["longitude_deg"]),
            }
            for row in prior_level["retained_basins"]
        ]
        if prior_level
        else [origin]
    )
    begun = time.perf_counter()
    for level_index in range(len(levels), len(config["levels_km"])):
        spacing = float(config["levels_km"][level_index])
        points = lattice(parents, spacing, origin)
        if level_index == 0:
            by_key = {coordinate_key(point): point for point in points}
            for seed in config["seeds"]:
                seed_point = {
                    "latitude_deg": float(seed["latitude_deg"]),
                    "longitude_deg": float(seed["longitude_deg"]),
                }
                east, north = local_offsets(seed_point, origin)
                seed_point.update({"east_km_from_origin": east, "north_km_from_origin": north})
                by_key[coordinate_key(seed_point)] = seed_point
            points = list(by_key.values())
        tasks = [
            (
                str(manifest_path),
                str(work_root),
                str(group["group_id"]),
                point,
                nearest_parent_warm(point, str(group["group_id"]), prior_level),
            )
            for point in points
            for group in config["groups"]
        ]
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=workers, mp_context=multiprocessing.get_context("fork")
        ) as pool:
            scans = list(pool.map(scan_coordinate, tasks, chunksize=1))
        proposals = combine(config, points, scans)
        retained = proposals[: int(config["top_basins"])]
        level_document = {
            "spacing_km": spacing,
            "coordinate_count": len(points),
            "proposal_scans": scans,
            "proposals": proposals,
            "retained_basins": retained,
        }
        checkpoints.write_level(level_index, level_document)
        levels = checkpoints.completed()
        prior_level = levels[-1]
        parents = [
            {
                "latitude_deg": float(row["latitude_deg"]),
                "longitude_deg": float(row["longitude_deg"]),
            }
            for row in retained
        ]
    finalists = levels[-1]["proposals"][: int(config["exact_top_coordinates"])]
    exact_tasks = [
        (str(manifest_path), str(work_root), str(group["group_id"]), point, tau)
        for point in finalists
        for group in config["groups"]
        for tau in point["proposal_taus"][str(group["group_id"])]
    ]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        audits = list(pool.map(exact_audit, exact_tasks, chunksize=1))
    exact_rows = select_exact(config, audits, finalists)
    document = {
        "schema": "consistent-cap800-inference/v1",
        "complete": True,
        "partition": config.get("partition", "train"),
        "reference_used_for_fit": False,
        "config_sha256": config["manifest_sha256"],
        "dataset_manifest": config["dataset_manifest"],
        "objective": "equal-weight cap-800 all-qualified-observation capped loss",
        "warm_start_policy": (
            "nearest retained parent at the same tau, then adjacent tau; "
            "initialization only, objective unchanged"
        ),
        "levels": levels,
        "exact_audit_count": len(audits),
        "exact_finalists": exact_rows,
        "winner": exact_rows[0],
        "workers": workers,
        "elapsed_s_this_invocation": time.perf_counter() - begun,
        "bindings": {
            "manifest": digest(manifest_path),
            "dataset": digest(Path(config["dataset_manifest"]["path"])),
            **{name: digest(Path(module_path)) for name, module_path in config["modules"].items()},
        },
    }
    atomic_write(output, canonical(document))
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest", type=Path)
    mode.add_argument("--inventory-preflight", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.inventory_preflight:
        result = inventory_preflight(args.inventory_preflight)
        if args.output:
            atomic_write(args.output, canonical(result))
        print(json.dumps(result, sort_keys=True))
        return
    if args.manifest is None:
        raise ValueError("manifest is required")
    config = validate_manifest(args.manifest)
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "launchable": True,
                    "config_sha256": config["manifest_sha256"],
                    "group_count": len(config["groups"]),
                    "session_count": sum(
                        len(group["task"]["session_ids"]) for group in config["groups"]
                    ),
                },
                sort_keys=True,
            )
        )
        return
    if args.work_root is None or args.output is None:
        raise ValueError("work-root and output are required for execution")
    result = execute(args.manifest.resolve(), args.work_root.resolve(), args.output, args.workers)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "winner": result["winner"],
                "elapsed_s_this_invocation": result["elapsed_s_this_invocation"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
