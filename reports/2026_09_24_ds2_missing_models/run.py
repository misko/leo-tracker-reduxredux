#!/usr/bin/env python3
"""Run the repaired DS2 session-scale and fixed-finalist residual arms."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PORTABLE_RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT_RUNNER = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SCALE_RUNNER = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"
CACHE_ROOT = Path("/var/tmp/leo-ds2-portable-cache")

SCALE_LO_HZ = 5.0
SCALE_HI_HZ = 2000.0
SCALE_NOMINAL_HZ = 250.0
SCALE_LOG_PRIOR_WIDTH = 1.5
AR1_RHO = 0.65
CORRELATION_TIME_S = 1.0
STUDENT_DF = 4.0
IRLS_ITERATIONS = 12

_ENGINE: Any = None
_ORBIT: Any = None
_SCALE: Any = None
_PLAN: dict[str, Any] | None = None


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def offset_coordinate(latitude: float, longitude: float, east_km: float, north_km: float) -> dict:
    return {
        "latitude_deg": latitude + north_km / 111.32,
        "longitude_deg": longitude
        + east_km / (111.32 * math.cos(math.radians(latitude))),
        "east_km": east_km,
        "north_km": north_km,
    }


def initialize(plan_path: str, cache_root: str) -> None:
    global _ENGINE, _ORBIT, _SCALE, _PLAN
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    _PLAN = json.loads(Path(plan_path).read_text())
    runner = load(PORTABLE_RUNNER, f"ds2_missing_orbit_{os.getpid()}")
    _ORBIT = load(ORBIT_RUNNER, f"ds2_missing_exact_{os.getpid()}")
    _SCALE = load(SCALE_RUNNER, f"ds2_missing_scale_{os.getpid()}")
    # The reviewed helper reads the immutable archive through a privileged
    # subprocess.  Cache those digest-verified bytes inside each worker: both
    # causal_ages and exact_phase_nodes otherwise repeat the same read once per
    # session because dict.setdefault evaluates its default eagerly.
    archive_payload = _ORBIT.archive_payload
    archive_cache: dict[str, bytes] = {}

    def cached_archive(snapshot_digest: str) -> bytes:
        if snapshot_digest not in archive_cache:
            archive_cache[snapshot_digest] = archive_payload(snapshot_digest)
        return archive_cache[snapshot_digest]

    _ORBIT.archive_payload = cached_archive
    runner.CACHE_ROOTS.clear()
    runner.CACHE_ROOTS["ds2"] = Path(cache_root)
    task = {
        "task_id": "ds2-missing-models",
        "group_id": "ds2-sept24-all",
        "session_ids": _PLAN["session_ids"],
        "session_groups": {sid: "ds2" for sid in _PLAN["session_ids"]},
        "prior": _PLAN["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {"cache_root": cache_root},
    }
    _ENGINE = runner.FullObservationEngine(runner.validate_task(task))
    # Match the portable all-session objective: every whole capture has one vote.
    for session in _ENGINE.sessions:
        denominator = sum(track.weight for track in session.tracks)
        for track in session.tracks:
            track.weight = float(track.weight) / denominator


def prepared(latitude: float, longitude: float, tau_s: float, associations=None) -> Any:
    if _ENGINE is None or _ORBIT is None:
        raise RuntimeError("worker was not initialized")
    runner = load(PORTABLE_RUNNER, f"ds2_missing_prepare_{os.getpid()}")
    return runner._make_exact_prepared(
        _ENGINE, _ORBIT, latitude, longitude, tau_s, associations
    )


def gate(data: Any, model: Any, fit: dict[str, Any], tau_s: float) -> dict[str, Any]:
    return _ORBIT.exact_replay_gate(
        data,
        model.receiver,
        model.search,
        tau_s,
        fit["rates_s_h"],
        tolerance_hz=0.2,
    )


def sequence_rows(model: Any, fit: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rates = np.asarray([fit["rates_s_h"][str(name)] for name in model.source_names])
    zero_scale = np.zeros(1 + len(model.session_names))
    _centered, prediction, raw = model.residual(rates, zero_scale)
    # model.residual returns base prediction and measured-minus-prediction before CFO.
    del prediction
    rows = []
    for index, name in enumerate(model.track_names):
        selected = np.flatnonzero(model.track_index == index)
        order = selected[np.argsort(model.data.time_s[selected], kind="stable")]
        values = raw[order]
        times = model.data.time_s[order]
        alpha = AR1_RHO ** (np.maximum(np.diff(times), 0.0) / CORRELATION_TIME_S)
        white_raw = np.empty(len(values))
        white_one = np.empty(len(values))
        white_raw[0], white_one[0] = values[0], 1.0
        if len(values) > 1:
            denominator = np.sqrt(np.maximum(1 - alpha * alpha, 1e-12))
            white_raw[1:] = (values[1:] - alpha * values[:-1]) / denominator
            white_one[1:] = (1 - alpha) / denominator
        rows.append(
            {
                "track": str(name),
                "weight_s": float(model.data.weights[str(name)]),
                "raw": values,
                "white_raw": white_raw,
                "white_one": white_one,
                "observations": len(values),
            }
        )
    return rows, {
        "track_sequence_count": len(rows),
        "observation_count": int(sum(row["observations"] for row in rows)),
        "transition_count": int(sum(max(0, row["observations"] - 1) for row in rows)),
        "equal_whole_session_weight": True,
    }


def weighted_mean(rows: list[dict[str, Any]], terms: list[np.ndarray]) -> float:
    denominator = sum(row["weight_s"] for row in rows)
    return sum(
        row["weight_s"] * float(np.mean(term))
        for row, term in zip(rows, terms, strict=True)
    ) / denominator


def gaussian_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    residuals = [row["raw"] - np.mean(row["raw"]) for row in rows]
    variance = weighted_mean(rows, [value * value for value in residuals])
    scale = float(np.clip(math.sqrt(max(variance, 0.0)), SCALE_LO_HZ, SCALE_HI_HZ))
    nll = weighted_mean(
        rows,
        [
            0.5 * (value / scale) ** 2
            + math.log(scale)
            + 0.5 * math.log(2 * math.pi)
            for value in residuals
        ],
    )
    return {"nll_per_weighted_innovation": float(nll), "scale_hz": scale}


def robust_offset(raw: np.ndarray, one: np.ndarray, scale: float) -> float:
    value = float(np.dot(one, raw) / np.dot(one, one))
    for _ in range(IRLS_ITERATIONS):
        innovation = raw - one * value
        weights = (STUDENT_DF + 1) / (STUDENT_DF + (innovation / scale) ** 2)
        updated = float(np.dot(weights * one, raw) / np.dot(weights * one, one))
        if abs(updated - value) <= 1e-7 * max(1.0, abs(value)):
            return updated
        value = updated
    return value


def robust_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from scipy.optimize import minimize_scalar

    cache: dict[float, float] = {}

    def objective(log_scale: float) -> float:
        key = round(float(log_scale), 12)
        if key in cache:
            return cache[key]
        scale = math.exp(log_scale)
        terms = []
        for row in rows:
            offset = robust_offset(row["white_raw"], row["white_one"], scale)
            z = (row["white_raw"] - row["white_one"] * offset) / scale
            terms.append(
                math.log(scale) + 0.5 * (STUDENT_DF + 1) * np.log1p(z * z / STUDENT_DF)
            )
        prior = 0.5 * (math.log(scale / SCALE_NOMINAL_HZ) / SCALE_LOG_PRIOR_WIDTH) ** 2
        cache[key] = float(weighted_mean(rows, terms) + prior)
        return cache[key]

    fit = minimize_scalar(
        objective,
        bounds=(math.log(SCALE_LO_HZ), math.log(SCALE_HI_HZ)),
        method="bounded",
        options={"xatol": 1e-6, "maxiter": 80},
    )
    return {
        "nll_per_weighted_innovation": float(objective(float(fit.x))),
        "scale_hz": float(math.exp(float(fit.x))),
        "converged": bool(fit.success),
        "iterations": int(fit.nit),
    }


def audit_scale(point: dict[str, Any]) -> dict[str, Any]:
    source = _PLAN["session_scale"]
    document = json.loads(Path(source["source_artifact"]).read_text())
    started = time.monotonic()
    data = prepared(
        point["latitude_deg"], point["longitude_deg"], source["centre"]["tau_s"],
        document["track_associations"],
    )
    receiver, _up = _ENGINE.search.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
    model = _SCALE.ExactModel.build(data, receiver, _ENGINE.search, _ORBIT)
    baseline = _SCALE.fit(model, scales_enabled=False)
    hierarchy = _SCALE.fit(model, scales_enabled=True)
    return {
        **point,
        "tau_s": float(source["centre"]["tau_s"]),
        "association_count": len(data.assignments),
        "sample_count": len(data.y),
        "session_count": len(model.session_names),
        "source_count": len(model.source_names),
        "matched_rate_only": baseline,
        "common_plus_session_scale": hierarchy,
        "matched_rate_exact_gate": gate(data, model, baseline, source["centre"]["tau_s"]),
        "hierarchy_exact_gate": gate(data, model, hierarchy, source["centre"]["tau_s"]),
        "elapsed_s": time.monotonic() - started,
    }


def audit_residual(finalist: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    # Reacquire once under the original all-observation hard model, then freeze.
    _loss, associations = _ENGINE.hard_association(
        finalist["latitude_deg"], finalist["longitude_deg"], finalist["tau_s"]
    )
    data = prepared(
        finalist["latitude_deg"], finalist["longitude_deg"], finalist["tau_s"], associations
    )
    receiver, _up = _ENGINE.search.receiver_ecef(
        finalist["latitude_deg"], finalist["longitude_deg"]
    )
    model = _SCALE.ExactModel.build(data, receiver, _ENGINE.search, _ORBIT)
    rate_fit = _SCALE.fit(model, scales_enabled=False)
    rows, accounting = sequence_rows(model, rate_fit)
    return {
        **finalist,
        "association_count": len(data.assignments),
        "rate_only": rate_fit,
        "exact_gate": gate(data, model, rate_fit, finalist["tau_s"]),
        "gaussian": gaussian_profile(rows),
        "ar1_student_t": robust_profile(rows),
        "sequence_accounting": accounting,
        "elapsed_s": time.monotonic() - started,
    }


def audit_scale_start(task: tuple[dict[str, Any], float]) -> dict[str, Any]:
    point, start = task
    source = _PLAN["session_scale"]
    document = json.loads(Path(source["source_artifact"]).read_text())
    data = prepared(
        point["latitude_deg"],
        point["longitude_deg"],
        source["centre"]["tau_s"],
        document["track_associations"],
    )
    receiver, _up = _ENGINE.search.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
    model = _SCALE.ExactModel.build(data, receiver, _ENGINE.search, _ORBIT)
    initial = np.full(1 + len(model.session_names), start)
    fit = _SCALE.fit(model, scales_enabled=True, initial_scale=initial)
    return {"initial_scale": start, "fit": fit}


def rank(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (row[key]["nll_per_weighted_innovation"], row["finalist_id"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--cache-root", type=Path, default=CACHE_ROOT)
    parser.add_argument("--output", type=Path, default=HERE / "inference.json")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise ValueError("output exists or workers must be 1..4")
    plan = json.loads(args.plan.read_text())
    if plan.get("reference_coordinate_present") is not False or len(plan["session_ids"]) != 20:
        raise ValueError("plan violates the frozen DS2 inference boundary")
    centre = plan["session_scale"]["centre"]
    spacing = float(plan["session_scale"]["spacing_km"])
    scale_points = [
        offset_coordinate(centre["latitude_deg"], centre["longitude_deg"], east, north)
        for north in (-spacing, 0.0, spacing)
        for east in (-spacing, 0.0, spacing)
    ]
    started = time.monotonic()
    context = multiprocessing.get_context("fork")
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers,
        mp_context=context,
        initializer=initialize,
        initargs=(str(args.plan), str(args.cache_root)),
    ) as pool:
        scale_rows = list(pool.map(audit_scale, scale_points, chunksize=1))
        residual_rows = list(
            pool.map(audit_residual, plan["residual_likelihood"]["finalists"], chunksize=1)
        )
        scale_rows.sort(
            key=lambda row: (
                row["common_plus_session_scale"]["selection_objective"],
                row["north_km"],
                row["east_km"],
            )
        )
        scale_winner = scale_rows[0]
        sensitivity = list(
            pool.map(
                audit_scale_start,
                [(scale_winner, -4e-4), (scale_winner, 4e-4)],
                chunksize=1,
            )
        )
    baseline_rows = sorted(
        scale_rows,
        key=lambda row: (
            row["matched_rate_only"]["selection_objective"],
            row["north_km"],
            row["east_km"],
        ),
    )
    baseline_winner = baseline_rows[0]
    gaussian = rank(residual_rows, "gaussian")
    robust = rank(residual_rows, "ar1_student_t")
    result = {
        "schema": "ds2-missing-models-inference/v1",
        "complete": True,
        "partition": "development",
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "truth_used_for_fit": False,
        "session_count": 20,
        "session_ids": plan["session_ids"],
        "prior": plan["prior"],
        "plan": {"path": str(args.plan.resolve()), "sha256": digest(args.plan)},
        "common_plus_session_scale": {
            "status": "complete",
            "coordinate_policy": "symmetric 3x3 exact local lattice around sealed fine rate winner",
            "association_policy": plan["session_scale"]["association_policy"],
            "equal_whole_session_weight": True,
            "rows": scale_rows,
            "matched_rate_only_winner": {
                "latitude_deg": baseline_winner["latitude_deg"],
                "longitude_deg": baseline_winner["longitude_deg"],
                "east_km": baseline_winner["east_km"],
                "north_km": baseline_winner["north_km"],
                "selection_objective": baseline_winner["matched_rate_only"]["selection_objective"],
            },
            "winner": {
                "latitude_deg": scale_winner["latitude_deg"],
                "longitude_deg": scale_winner["longitude_deg"],
                "east_km": scale_winner["east_km"],
                "north_km": scale_winner["north_km"],
                "selection_objective": scale_winner["common_plus_session_scale"][
                    "selection_objective"
                ],
            },
            "initialization_sensitivity": sensitivity,
            "opposite_start_objective_difference": abs(
                sensitivity[0]["fit"]["selection_objective"]
                - sensitivity[1]["fit"]["selection_objective"]
            ),
            "winner_on_lattice_boundary": bool(
                abs(scale_winner["east_km"]) >= spacing - 1e-12
                or abs(scale_winner["north_km"]) >= spacing - 1e-12
            ),
            "qualified": bool(
                scale_winner["common_plus_session_scale"]["converged"]
                and not scale_winner["common_plus_session_scale"]["scale_reaches_guard"]
                and scale_winner["hierarchy_exact_gate"]["passed"]
                and abs(scale_winner["east_km"]) < spacing - 1e-12
                and abs(scale_winner["north_km"]) < spacing - 1e-12
                and abs(
                    sensitivity[0]["fit"]["selection_objective"]
                    - sensitivity[1]["fit"]["selection_objective"]
                )
                <= 1e-6
            ),
        },
        "robust_residual_likelihood": {
            "status": "complete",
            "candidate_policy": plan["residual_likelihood"]["candidate_policy"],
            "association_policy": plan["residual_likelihood"]["association_policy"],
            "hyperparameters": {
                "ar1_rho": AR1_RHO,
                "correlation_time_s": CORRELATION_TIME_S,
                "student_df": STUDENT_DF,
                "scale_bounds_hz": [SCALE_LO_HZ, SCALE_HI_HZ],
                "scale_nominal_hz": SCALE_NOMINAL_HZ,
                "scale_log_prior_width": SCALE_LOG_PRIOR_WIDTH,
                "irls_iterations": IRLS_ITERATIONS,
            },
            "rows": residual_rows,
            "gaussian_ranking": [row["finalist_id"] for row in gaussian],
            "ar1_student_t_ranking": [row["finalist_id"] for row in robust],
            "gaussian_winner": {
                key: gaussian[0][key]
                for key in ("finalist_id", "latitude_deg", "longitude_deg", "tau_s")
            },
            "ar1_student_t_winner": {
                key: robust[0][key]
                for key in ("finalist_id", "latitude_deg", "longitude_deg", "tau_s")
            },
            "qualified": bool(
                all(row["exact_gate"]["passed"] for row in residual_rows)
                and all(row["ar1_student_t"]["converged"] for row in residual_rows)
            ),
        },
        "elapsed_s": time.monotonic() - started,
        "workers": args.workers,
        "bindings": {
            "driver": digest(Path(__file__)),
            "portable_runner": digest(PORTABLE_RUNNER),
            "exact_orbit": digest(ORBIT_RUNNER),
            "repaired_scale_model": digest(SCALE_RUNNER),
        },
    }
    content = canonical(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(
        canonical(
            {
                "elapsed_s": result["elapsed_s"],
                "session_scale_qualified": result["common_plus_session_scale"]["qualified"],
                "residual_qualified": result["robust_residual_likelihood"]["qualified"],
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
