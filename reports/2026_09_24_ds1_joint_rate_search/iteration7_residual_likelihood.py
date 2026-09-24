#!/usr/bin/env python3
"""Iteration-7 refit-free exact-residual likelihood ablation for DS1.

The iteration-6 coordinates, associations, and exact per-NORAD rates are
frozen inputs.  This script reconstructs exact-SGP4 residual sequences but
never changes an orbit rate or association.  It compares an independent
Gaussian learned-scale likelihood with a bounded AR(1)+Student-t likelihood.
"""

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
from scipy.optimize import minimize_scalar

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITER6 = HERE / "iteration6-results.json"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
GROUPS = ("20260921_00", "20260921_16")
SCALE_LO_HZ, SCALE_HI_HZ, SCALE_NOMINAL_HZ, SCALE_LOG_PRIOR_WIDTH = 5.0, 2000.0, 250.0, 1.5
AR1_RHO, CORRELATION_TIME_S, STUDENT_DF = 0.65, 1.0, 4.0
IRLS_ITERATIONS = 12

_REPLAY: Any = None
_CATALOGUES: dict[str, Any] = {}


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


def source_path(group: str) -> Path:
    return SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--reno--global_time.json"


def source_task(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "iteration7-" + str(source["task_id"]),
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def load_iteration6(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("complete") is not True or value.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-6 reference-free contract is invalid")
    for group in GROUPS:
        result = next((row for row in value.get("results", []) if row["group_id"] == group), None)
        if result is None or result.get("exact_candidate_count") != 28:
            raise ValueError(f"unexpected iteration-6 candidate set: {group}")
        if not all(
            row["exact_comparison"]["exact_sgp4_gate"]["passed"] for row in result["candidates"]
        ):
            raise ValueError(f"unqualified exact candidate: {group}")
    return value


def exact_prediction(
    data: Any, receiver: np.ndarray, search: Any, orbit: Any, tau_s: float, rates: dict[str, float]
) -> np.ndarray:
    """Replay the exact fixed-Earth SGP4 state used by the qualified gate."""
    global _REPLAY
    if _REPLAY is None:
        _REPLAY = load(ROOT / "tools/replay_regional_doppler.py", f"i7_replay_{os.getpid()}")
    from leo.sky.propagation import parse_element_sets

    predicted = np.empty(len(data.y))
    seen = np.zeros(len(data.y), dtype=bool)
    for session_id, info in data.sources.items():
        snapshot = str(info["snapshot_digest"])
        catalogue = _CATALOGUES.get(snapshot)
        if catalogue is None:
            catalogue = parse_element_sets(orbit.archive_payload(snapshot).decode("ascii"))
            _CATALOGUES[snapshot] = catalogue
        index = {str(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        session_rows = data.session == session_id
        for norad in info["norads"]:
            rows = np.flatnonzero(session_rows & (data.source == norad))
            if not len(rows):
                continue
            rate = float(rates[str(norad)])
            phase_s = float(data.age_h[rows[0]] * rate)
            p, v, valid = _REPLAY.state_arrays(
                catalogue,
                [index[str(norad)]],
                info["capture_start_utc_ns"],
                data.time_s[rows],
                orbit_time_s=phase_s,
                clock_s=float(tau_s),
            )
            if len(valid) != 1:
                raise ValueError("exact residual replay failed")
            predicted[rows] = orbit.doppler(receiver, p[0], v[0], search)
            seen[rows] = True
    if not np.all(seen):
        raise ValueError("exact residual replay missed selected observations")
    return predicted


def sequences(data: Any, raw: np.ndarray) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = []
    for label in np.unique(data.track):
        rows = np.flatnonzero(data.track == label)
        rows = rows[np.argsort(data.time_s[rows], kind="stable")]
        values, times = raw[rows], data.time_s[rows]
        if not len(values):
            continue
        alpha = AR1_RHO ** (np.maximum(np.diff(times), 0.0) / CORRELATION_TIME_S)
        white_raw = np.empty(len(values))
        white_one = np.empty(len(values))
        white_raw[0], white_one[0] = values[0], 1.0
        if len(values) > 1:
            denom = np.sqrt(np.maximum(1 - alpha * alpha, 1e-12))
            white_raw[1:] = (values[1:] - alpha * values[:-1]) / denom
            white_one[1:] = (1 - alpha) / denom
        out.append(
            {
                "track": str(label),
                "weight_s": float(data.weights[str(label)]),
                "raw": values,
                "white_raw": white_raw,
                "white_one": white_one,
                "observations": int(len(values)),
                "transitions": int(max(0, len(values) - 1)),
                "mean_alpha": float(np.mean(alpha)) if len(alpha) else None,
            }
        )
    accounting = {
        "track_sequence_count": len(out),
        "observation_count": int(sum(row["observations"] for row in out)),
        "conditional_innovation_count": int(sum(row["observations"] for row in out)),
        "transition_count": int(sum(row["transitions"] for row in out)),
        "occupied_second_weight": float(sum(row["weight_s"] for row in out)),
        "first_observation_per_sequence": "one unconditional innovation",
        "subsequent_observations": "one AR(1)-standardized conditional innovation; no thinning",
    }
    return out, accounting


def weighted_mean(seqs: list[dict[str, Any]], values: list[np.ndarray]) -> float:
    numerator = sum(
        row["weight_s"] * float(np.mean(value)) for row, value in zip(seqs, values, strict=True)
    )
    return numerator / sum(row["weight_s"] for row in seqs)


def gaussian_profile(seqs: list[dict[str, Any]]) -> dict[str, Any]:
    residuals, offsets = [], {}
    for row in seqs:
        offset = float(np.mean(row["raw"]))
        offsets[row["track"]] = offset
        residuals.append(row["raw"] - offset)
    variance = weighted_mean(seqs, [value * value for value in residuals])
    scale = float(np.clip(math.sqrt(max(variance, 0.0)), SCALE_LO_HZ, SCALE_HI_HZ))
    nll = weighted_mean(
        seqs,
        [
            0.5 * (value / scale) ** 2 + math.log(scale) + 0.5 * math.log(2 * math.pi)
            for value in residuals
        ],
    )
    return {
        "negative_log_likelihood_per_weighted_innovation": float(nll),
        "scale_hz": scale,
        "scale_at_bound": bool(scale in (SCALE_LO_HZ, SCALE_HI_HZ)),
        "track_cfo_hz": offsets,
    }


def robust_offset(raw: np.ndarray, one: np.ndarray, scale: float) -> float:
    """Bounded-iteration IRLS location profile for a Student-t innovation."""
    offset = float(np.dot(one, raw) / np.dot(one, one))
    for _ in range(IRLS_ITERATIONS):
        innovation = raw - one * offset
        weights = (STUDENT_DF + 1) / (STUDENT_DF + (innovation / scale) ** 2)
        updated = float(np.dot(weights * one, raw) / np.dot(weights * one, one))
        if abs(updated - offset) <= 1e-7 * max(1.0, abs(offset)):
            return updated
        offset = updated
    return offset


def robust_profile(seqs: list[dict[str, Any]]) -> dict[str, Any]:
    cache: dict[float, tuple[float, dict[str, float]]] = {}

    def objective(log_scale: float) -> float:
        key = round(float(log_scale), 12)
        if key in cache:
            return cache[key][0]
        scale = math.exp(log_scale)
        offsets: dict[str, float] = {}
        terms = []
        for row in seqs:
            offset = robust_offset(row["white_raw"], row["white_one"], scale)
            offsets[row["track"]] = offset
            z = (row["white_raw"] - row["white_one"] * offset) / scale
            terms.append(math.log(scale) + 0.5 * (STUDENT_DF + 1) * np.log1p(z * z / STUDENT_DF))
        prior = 0.5 * (math.log(scale / SCALE_NOMINAL_HZ) / SCALE_LOG_PRIOR_WIDTH) ** 2
        answer = weighted_mean(seqs, terms) + prior
        cache[key] = (float(answer), offsets)
        return float(answer)

    fit = minimize_scalar(
        objective,
        bounds=(math.log(SCALE_LO_HZ), math.log(SCALE_HI_HZ)),
        method="bounded",
        options={"xatol": 1e-6, "maxiter": 80},
    )
    scale = math.exp(float(fit.x))
    nll = objective(float(fit.x))
    _, offsets = cache[round(float(fit.x), 12)]
    return {
        "negative_log_likelihood_per_weighted_innovation": float(nll),
        "scale_hz": float(scale),
        "scale_log_prior": 0.5 * (math.log(scale / SCALE_NOMINAL_HZ) / SCALE_LOG_PRIOR_WIDTH) ** 2,
        "scale_at_bound": bool(abs(scale - SCALE_LO_HZ) < 1e-4 or abs(scale - SCALE_HI_HZ) < 1e-3),
        "converged": bool(fit.success),
        "iterations": int(fit.nit),
        "track_cfo_hz": offsets,
    }


def evaluate_candidate(task: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    group, candidate = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    existing = load(RUNNER, f"i7_existing_{os.getpid()}")
    orbit = load(ORBIT, f"i7_orbit_{os.getpid()}")
    source = json.loads(source_path(group).read_text())
    engine = existing.FullObservationEngine(existing.validate_task(source_task(source)))
    data = existing._make_exact_prepared(
        engine,
        orbit,
        candidate["latitude_deg"],
        candidate["longitude_deg"],
        candidate["tau_s"],
        candidate["track_associations"],
    )
    receiver, _up = engine.search.receiver_ecef(
        candidate["latitude_deg"], candidate["longitude_deg"]
    )
    begun = time.perf_counter()
    predicted = exact_prediction(
        data,
        receiver,
        engine.search,
        orbit,
        candidate["tau_s"],
        candidate["exact_comparison"]["exact_rate_corrections_s_h"],
    )
    seqs, accounting = sequences(data, data.y - predicted)
    gaussian, robust = gaussian_profile(seqs), robust_profile(seqs)
    return {
        "group_id": group,
        "latitude_deg": candidate["latitude_deg"],
        "longitude_deg": candidate["longitude_deg"],
        "tau_s": candidate["tau_s"],
        "iteration6_exact_capped_loss": candidate["exact_comparison"][
            "exact_full_observation_capped_loss"
        ],
        "exact_rate_replay_gate": candidate["exact_comparison"]["exact_sgp4_gate"],
        "residual_replay_elapsed_s": time.perf_counter() - begun,
        "sequence_accounting": accounting,
        "independent_gaussian": gaussian,
        "ar1_student_t": robust,
    }


def rank_key(model: str):
    return lambda row: (
        row[model]["negative_log_likelihood_per_weighted_innovation"],
        abs(row["tau_s"]),
        row["tau_s"],
        row["latitude_deg"],
        row["longitude_deg"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration6", type=Path, default=ITER6)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 8:
        raise ValueError("existing output or invalid workers")
    source = load_iteration6(args.iteration6)
    tasks = [
        (group, candidate)
        for group in GROUPS
        for result in source["results"]
        if result["group_id"] == group
        for candidate in result["candidates"]
    ]
    begun = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        rows = list(pool.map(evaluate_candidate, tasks, chunksize=1))
    results = []
    for group in GROUPS:
        candidates = [row for row in rows if row["group_id"] == group]
        for model in ("independent_gaussian", "ar1_student_t"):
            for rank, row in enumerate(sorted(candidates, key=rank_key(model)), start=1):
                row[model]["rank"] = rank
        results.append(
            {
                "group_id": group,
                "candidate_count": len(candidates),
                "selection": "model-specific reference-free residual likelihood only",
                "candidates": candidates,
                "independent_gaussian_winner": min(
                    candidates, key=rank_key("independent_gaussian")
                ),
                "ar1_student_t_winner": min(candidates, key=rank_key("ar1_student_t")),
            }
        )
    output = {
        "schema": "ds1-iteration7-fixed-exact-residual-likelihood/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "candidate_policy": "exactly the completed iteration-6 candidate union",
        "orbit_rate_policy": "reuse iteration-6 exact per-NORAD rates without refit",
        "association_policy": "reuse iteration-6 exact hard associations without reassignment",
        "track_accounting": (
            "per-track mean likelihood, occupied-second weighted; every sequence has one first "
            "plus AR(1) conditional innovations"
        ),
        "gaussian_model": {
            "scale_bounds_hz": [SCALE_LO_HZ, SCALE_HI_HZ],
            "profiled_nuisances": "per-track CFO and global scale",
        },
        "ar1_student_t_model": {
            "ar1_rho": AR1_RHO,
            "correlation_time_s": CORRELATION_TIME_S,
            "student_df": STUDENT_DF,
            "scale_bounds_hz": [SCALE_LO_HZ, SCALE_HI_HZ],
            "scale_log_prior_nominal_hz": SCALE_NOMINAL_HZ,
            "scale_log_prior_width": SCALE_LOG_PRIOR_WIDTH,
            "profiled_nuisances": "per-track robust CFO and global scale",
            "irls_iterations": IRLS_ITERATIONS,
        },
        "elapsed_s": time.perf_counter() - begun,
        "workers": args.workers,
        "iteration6_input": {"path": str(args.iteration6), "sha256": digest(args.iteration6)},
        "results": results,
        "bindings": {
            "driver": digest(Path(__file__)),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps({"output": str(args.output), "elapsed_s": output["elapsed_s"]}, sort_keys=True)
    )


if __name__ == "__main__":
    main()
