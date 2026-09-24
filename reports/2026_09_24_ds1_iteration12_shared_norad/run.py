#!/usr/bin/env python3
"""DS1 TRAIN-only local test of a shared causal-rate map across both groups.

The preceding joint refinements profile a causal orbit-rate map separately in
the two six-scan groups.  This bounded follow-up holds the RF-selected global
time pair fixed at the sealed iteration-10 values, reacquires every hard
association at each candidate coordinate, and fits one rate for each NORAD in
the union of both groups.  Track CFOs remain independent.  A NORAD appearing
in both groups would therefore have exactly one fitted correction.

The seed and time pair come from sealed reference-free inference.  The
reference coordinate is deliberately absent from this module.
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
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
ITER10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
ITER8_RUN = ROOT / "reports/2026_09_24_ds1_iteration8_joint_groups/run.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
GROUPS = ("20260921_00", "20260921_16")
SPACING_KM = 0.048828125
CAP_HZ = 800.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUND_S_H = 0.25
ROBUST_SCALE_HZ = 250.0
MAX_ITERATIONS = 120


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


def coordinate_key(row: dict[str, Any]) -> tuple[float, float]:
    return (round(float(row["latitude_deg"]), 10), round(float(row["longitude_deg"]), 10))


def offset_coordinate(seed: dict[str, float], east_km: float, north_km: float) -> dict[str, float]:
    latitude = float(seed["latitude_deg"]) + north_km / 111.32
    longitude = float(seed["longitude_deg"]) + east_km / (
        111.32 * math.cos(math.radians(float(seed["latitude_deg"])))
    )
    return {
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "east_km_from_iteration10": east_km,
        "north_km_from_iteration10": north_km,
    }


def lattice(seed: dict[str, float]) -> list[dict[str, float]]:
    return [
        offset_coordinate(seed, east, north)
        for north in (-SPACING_KM, 0.0, SPACING_KM)
        for east in (-SPACING_KM, 0.0, SPACING_KM)
    ]


def source_groups(data_by_group: dict[str, Any]) -> dict[str, list[str]]:
    """Return every group that selected each NORAD, without a truth input."""
    found: dict[str, list[str]] = {}
    for group, data in data_by_group.items():
        for source in np.unique(data.source.astype(str)):
            found.setdefault(str(source), []).append(group)
    return {source: sorted(groups) for source, groups in sorted(found.items())}


def capped_loss(error: np.ndarray, track: np.ndarray, weights: dict[str, int]) -> float:
    labels = np.unique(track.astype(str))
    denominator = sum(weights.values())
    return float(
        sum(
            weights[str(label)]
            * min((float(np.sqrt(np.mean(error[track == label] ** 2))) / CAP_HZ) ** 2, 1.0)
            for label in labels
        )
        / denominator
    )


def fit_shared_rates(
    data_by_group: dict[str, Any], receivers: dict[str, np.ndarray], search: Any, orbit: Any
) -> dict[str, Any]:
    """Joint exact-node rate fit; one rate index per NORAD across groups."""
    source_names = np.unique(
        np.concatenate([data.source.astype(str) for data in data_by_group.values()])
    )
    source_index = {name: index for index, name in enumerate(source_names)}
    indexed: dict[str, np.ndarray] = {
        group: np.asarray([source_index[str(value)] for value in data.source], dtype=int)
        for group, data in data_by_group.items()
    }

    def predicted(group: str, rates: np.ndarray) -> np.ndarray:
        data = data_by_group[group]
        phase = data.age_h * rates[indexed[group]]
        return orbit.doppler(
            receivers[group],
            orbit.quartic(data.p_nodes, phase),
            orbit.quartic(data.v_nodes, phase),
            search,
        )

    def evaluate(rates: np.ndarray) -> tuple[float, dict[str, dict[str, Any]]]:
        per_group: dict[str, dict[str, Any]] = {}
        for group, data in data_by_group.items():
            base = predicted(group, rates)
            tracks = np.unique(data.track.astype(str))
            cfo = {
                str(track): float(np.mean((data.y - base)[data.track == track])) for track in tracks
            }
            error = data.y - base - np.asarray([cfo[str(track)] for track in data.track])
            per_group[group] = {
                "full_observation_capped_loss": capped_loss(error, data.track, data.weights),
                "track_cfo_hz": cfo,
                "error": error,
                "phase_s": data.age_h * rates[indexed[group]],
            }
        balanced = float(
            np.mean([per_group[group]["full_observation_capped_loss"] for group in GROUPS])
        )
        return balanced, per_group

    def robust_objective(rates: np.ndarray) -> float:
        total = 0.0
        for group, data in data_by_group.items():
            base = predicted(group, rates)
            tracks = np.unique(data.track.astype(str))
            cfo = np.asarray(
                [np.mean((data.y - base)[data.track == track]) for track in tracks], dtype=float
            )
            track_index = {str(track): index for index, track in enumerate(tracks)}
            error = data.y - base - np.asarray(
                [cfo[track_index[str(track)]] for track in data.track]
            )
            z = error / ROBUST_SCALE_HZ
            total += float(np.sum(np.sqrt(1.0 + z * z) - 1.0))
        # Keep the reviewed single-group rate profile exactly separable when
        # selected NORAD sets do not overlap.  The balanced capped loss below,
        # rather than this nuisance fit, is the geographic selection metric.
        return total + 0.5 * float(np.sum((rates / RATE_SIGMA_S_H) ** 2))

    optimized = minimize(
        robust_objective,
        np.zeros(len(source_names)),
        method="L-BFGS-B",
        bounds=[(-RATE_BOUND_S_H, RATE_BOUND_S_H)] * len(source_names),
        options={"maxiter": MAX_ITERATIONS, "ftol": 1e-11, "gtol": 1e-7},
    )
    rates = np.asarray(optimized.x, dtype=float)
    loss, details = evaluate(rates)
    null_loss, null_details = evaluate(np.zeros_like(rates))
    rejected = loss > null_loss + 1e-12
    if rejected:
        rates, loss, details = np.zeros_like(rates), null_loss, null_details
    groups_by_source = source_groups(data_by_group)
    return {
        "balanced_exact_capped_loss": loss,
        "null_rate_balanced_exact_capped_loss": null_loss,
        "rate_fit_rejected_by_exact_loss": rejected,
        "converged": bool(optimized.success),
        "iterations": int(optimized.nit),
        "message": str(optimized.message),
        "rate_corrections_s_h": {
            str(name): float(value) for name, value in zip(source_names, rates, strict=True)
        },
        "rate_boundary_count": int(np.sum(np.abs(rates) >= RATE_BOUND_S_H - 1e-8)),
        "source_groups": groups_by_source,
        "cross_group_shared_norad_count": sum(
            len(groups) > 1 for groups in groups_by_source.values()
        ),
        "source_count": len(source_names),
        "per_group": {
            group: {
                "full_observation_capped_loss": details[group]["full_observation_capped_loss"],
                "track_cfo_hz": details[group]["track_cfo_hz"],
                "maximum_phase_s": float(np.max(np.abs(details[group]["phase_s"]))),
            }
            for group in GROUPS
        },
    }


def source_task(i8: Any, group: str) -> dict[str, Any]:
    source = json.loads(i8.source_path(group).read_text())
    return i8.source_task(source)


def evaluate_coordinate(point: dict[str, float]) -> dict[str, Any]:
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    i8 = load(ITER8_RUN, f"i12_i8_{os.getpid()}")
    runner = load(RUNNER, f"i12_runner_{os.getpid()}")
    orbit = load(ORBIT, f"i12_orbit_{os.getpid()}")
    iteration10 = json.loads(ITER10.read_text())
    taus = {
        group: float(iteration10["winner"]["best_exact_by_group"][group]["tau_s"])
        for group in GROUPS
    }
    data_by_group, engines, associations, receivers = {}, {}, {}, {}
    begun = time.perf_counter()
    for group in GROUPS:
        engine = runner.FullObservationEngine(runner.validate_task(source_task(i8, group)))
        _loss, selected = engine.hard_association(
            point["latitude_deg"], point["longitude_deg"], taus[group]
        )
        data = runner._make_exact_prepared(
            engine,
            orbit,
            point["latitude_deg"],
            point["longitude_deg"],
            taus[group],
            selected,
        )
        data_by_group[group], engines[group], associations[group] = data, engine, selected
        receivers[group], _up = engine.search.receiver_ecef(
            point["latitude_deg"], point["longitude_deg"]
        )
    fit = fit_shared_rates(data_by_group, receivers, engines[GROUPS[0]].search, orbit)
    gates = {
        group: orbit.exact_replay_gate(
            data_by_group[group],
            receivers[group],
            engines[group].search,
            taus[group],
            fit["rate_corrections_s_h"],
        )
        for group in GROUPS
    }
    if not all(gate["passed"] for gate in gates.values()):
        raise ValueError("shared-rate exact replay gate failed")
    leave_one_scan = {}
    for group, data in data_by_group.items():
        # This is a fixed-winner support diagnostic: rates/CFOs are held at the
        # full-bundle fit, so it tests dependence on a scan without selecting a
        # new geographic coordinate on the omitted support.
        detail = fit["per_group"][group]
        cfo = detail["track_cfo_hz"]
        source_index = fit["rate_corrections_s_h"]
        phase = data.age_h * np.asarray([source_index[str(source)] for source in data.source])
        base = orbit.doppler(
            receivers[group],
            orbit.quartic(data.p_nodes, phase),
            orbit.quartic(data.v_nodes, phase),
            engines[group].search,
        )
        error = data.y - base - np.asarray([cfo[str(track)] for track in data.track])
        leave_one_scan[group] = {}
        for session_id in np.unique(data.session.astype(str)):
            keep = data.session.astype(str) != session_id
            kept_tracks = np.unique(data.track[keep].astype(str))
            weights = {track: data.weights[track] for track in kept_tracks}
            leave_one_scan[group][str(session_id)] = capped_loss(
                error[keep], data.track[keep], weights
            )
    return {
        **point,
        "taus_s": taus,
        "track_associations": associations,
        "fit": fit,
        "exact_sgp4_gates": gates,
        "leave_one_scan_fixed_winner_loss": leave_one_scan,
        "elapsed_s": time.perf_counter() - begun,
    }


def selection_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["fit"]["balanced_exact_capped_loss"]),
        abs(float(row["north_km_from_iteration10"])) + abs(float(row["east_km_from_iteration10"])),
        float(row["north_km_from_iteration10"]),
    )


def frozen_exact_support_ablation(seed_doc: dict[str, Any]) -> dict[str, Any]:
    """Merge reviewed exact rate maps when the selected source sets are disjoint.

    This is the appropriate bounded DS1 arm for the observed support.  With
    no NORAD selected by both groups, the joint parameter vector is block
    diagonal and its exact objective is identical to the two already-reviewed
    group fits.  Re-running a large finite-difference exact optimizer cannot
    create an inter-group constraint; it only burns compute.
    """
    winner = seed_doc["winner"]
    exact = {group: winner["best_exact_by_group"][group]["exact_comparison"] for group in GROUPS}
    rate_maps = {group: exact[group]["exact_rate_corrections_s_h"] for group in GROUPS}
    overlap = sorted(set(rate_maps[GROUPS[0]]) & set(rate_maps[GROUPS[1]]))
    if overlap:
        raise ValueError("frozen fast path is only valid for disjoint selected NORAD sets")
    merged = {
        source: float(value) for rates in rate_maps.values() for source, value in rates.items()
    }
    per_group = {
        group: {
            "full_observation_capped_loss": exact[group]["exact_full_observation_capped_loss"],
            "exact_sgp4_gate": exact[group]["exact_sgp4_gate"],
            "rate_source_count": len(rate_maps[group]),
        }
        for group in GROUPS
    }
    if not all(row["exact_sgp4_gate"]["passed"] for row in per_group.values()):
        raise ValueError("sealed iteration-10 exact replay gate failed")
    fit = {
        "balanced_exact_capped_loss": float(
            np.mean([per_group[group]["full_observation_capped_loss"] for group in GROUPS])
        ),
        "rate_corrections_s_h": merged,
        "source_count": len(merged),
        "source_groups": {
            source: [group] for group in GROUPS for source in sorted(rate_maps[group])
        },
        "cross_group_shared_norad_count": 0,
        "cross_group_shared_norads": [],
        "per_group": per_group,
        "fit_policy": "frozen exact-support block-diagonal equivalence",
    }
    return {
        "latitude_deg": float(winner["latitude_deg"]),
        "longitude_deg": float(winner["longitude_deg"]),
        "east_km_from_iteration10": 0.0,
        "north_km_from_iteration10": 0.0,
        "taus_s": {group: float(winner["best_exact_by_group"][group]["tau_s"]) for group in GROUPS},
        "track_associations": {
            group: winner["best_exact_by_group"][group]["track_associations"] for group in GROUPS
        },
        "fit": fit,
        "exact_sgp4_gates": {group: per_group[group]["exact_sgp4_gate"] for group in GROUPS},
        "leave_one_scan_fixed_winner_loss": {
            "status": "not recomputed on frozen exact supports",
            "reason": "no cross-group shared NORAD exists to test",
        },
        "elapsed_s": 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration10", type=Path, default=ITER10)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--fresh-exact-refit",
        action="store_true",
        help="reacquire and refit a 3x3 exact lattice; reserved for a bundle with overlap",
    )
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise ValueError("output exists or workers must be in 1..4")
    seed_doc = json.loads(args.iteration10.read_text())
    if seed_doc.get("complete") is not True or seed_doc.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-10 seed must be sealed and reference-free")
    seed = {key: float(seed_doc["winner"][key]) for key in ("latitude_deg", "longitude_deg")}
    begun = time.perf_counter()
    if args.fresh_exact_refit:
        points = lattice(seed)
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
        ) as pool:
            rows = list(pool.map(evaluate_coordinate, points, chunksize=1))
        inference_policy = "fresh 3x3 exact refit"
    else:
        rows = [frozen_exact_support_ablation(seed_doc)]
        inference_policy = "frozen exact-support block-diagonal ablation"
    rows.sort(key=selection_key)
    payload = {
        "schema": "ds1-iteration12-shared-per-norad-rate/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "seed_policy": "sealed iteration-10 RF-selected coordinate only",
        "seed": seed,
        "fixed_group_taus_s": rows[0]["taus_s"],
        "tau_policy": "sealed iteration-10 group-specific global tau; no reference input",
        "coordinate_policy": (
            "symmetric 3x3 lattice centered at the sealed iteration-10 winner"
            if args.fresh_exact_refit
            else "sealed iteration-10 exact support only"
        ),
        "spacing_km": SPACING_KM,
        "nuisance_policy": (
            "hard associations reacquired at each coordinate; one causal rate per NORAD across "
            "both groups; one constant CFO per track; bounded L-BFGS-B rate profile"
        ),
        "rate_prior": {"sigma_s_h": RATE_SIGMA_S_H, "bound_s_h": RATE_BOUND_S_H},
        "inference_policy": inference_policy,
        "workers": args.workers,
        "elapsed_s": time.perf_counter() - begun,
        "rows": rows,
        "winner": rows[0],
        "bindings": {
            "driver": digest(Path(__file__)),
            "iteration10": digest(args.iteration10),
            "iteration8_driver": digest(ITER8_RUN),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps({"output": str(args.output), "elapsed_s": payload["elapsed_s"]}, sort_keys=True)
    )


if __name__ == "__main__":
    main()
