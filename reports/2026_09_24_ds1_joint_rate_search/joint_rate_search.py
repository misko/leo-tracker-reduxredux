#!/usr/bin/env python3
"""Cache-only joint per-NORAD phase-rate geographic-screening prototype.

The production DS1 full-observation runner deliberately ranks locations with
nominal cached Doppler and sends only a small finalist set to the exact SGP4
rate fitter.  This experiment makes rate relevant during geographic screening
without changing that runner.  For a hard-associated candidate, its Doppler
sensitivity to phase seconds is the central difference of its receipt-bound
cache predictions at ``tau-1`` and ``tau+1``.  The cache advances Earth
rotation as well as orbit time, so this is a screening surrogate only.  Every
reported finalist receives the existing exact SGP4 rate fit separately.

There is no reference coordinate, observation mask, or truth input.  Sealed
TRAIN-only finalist artifacts supply only an RF-selected location, tau, and
session list for a bounded local-basin comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNNER_PATH = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT_PATH = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
CAP_HZ = 800.0
SENSITIVITY_DELTA_S = 1.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUND_S_H = 0.25
ROBUST_SCALE_HZ = 250.0
# This coefficient is predeclared before inspecting the sealed finalists.  It
# converts the dimensionless Normal(0, sigma) negative log-prior into the
# capped-loss scale used to select screening points.
PRIOR_SELECTION_WEIGHT = 0.001
SCREENING_MAX_ITERATIONS = 30
_EPOCHS_BY_SNAPSHOT: dict[str, dict[str, int]] = {}


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


@dataclass(frozen=True)
class Support:
    """One RF-only hard support, flattened over all qualified observations."""

    measured: np.ndarray
    nominal: np.ndarray
    sensitivity_hz_s: np.ndarray
    age_h: np.ndarray
    source: np.ndarray
    track: np.ndarray
    weights: dict[str, int]
    associations: list[dict[str, Any]]


def _labels(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.unique(values.astype(str), return_inverse=True)


def _capped_loss(
    error: np.ndarray, track_index: np.ndarray, weights: dict[str, int], tracks: np.ndarray
) -> float:
    denominator = sum(weights.values())
    return float(
        sum(
            weights[str(name)]
            * min((float(np.sqrt(np.mean(error[track_index == n] ** 2))) / CAP_HZ) ** 2, 1.0)
            for n, name in enumerate(tracks)
        )
        / denominator
    )


def fit_rate_support(support: Support) -> dict[str, Any]:
    """Profile constant CFO per track and one bounded, regularized rate/NORAD."""
    sources, source_index = _labels(support.source)
    tracks, track_index = _labels(support.track)
    feature = support.sensitivity_hz_s * support.age_h
    observed_minus_nominal = support.measured - support.nominal
    # Profiling a track CFO is equivalent to centering both response and each
    # rate feature within that track.  Keeping this matrix makes the robust
    # score differentiable without the costly finite-difference loop that is
    # unsuitable for a geographic screen with tens of NORADs.
    design = np.zeros((len(feature), len(sources)), dtype=float)
    design[np.arange(len(feature)), source_index] = feature
    centered_response = observed_minus_nominal.copy()
    centered_design = design.copy()
    for index in range(len(tracks)):
        rows = track_index == index
        centered_response[rows] -= np.mean(centered_response[rows])
        centered_design[rows] -= np.mean(centered_design[rows], axis=0)

    def evaluate(rates: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
        residual = observed_minus_nominal - feature * rates[source_index]
        cfo = np.asarray(
            [np.mean(residual[track_index == n]) for n in range(len(tracks))], dtype=float
        )
        return (
            _capped_loss(residual - cfo[track_index], track_index, support.weights, tracks),
            cfo,
            residual - cfo[track_index],
        )

    def robust_objective(rates: np.ndarray) -> float:
        error = centered_response - centered_design @ rates
        z = error / ROBUST_SCALE_HZ
        return float(
            np.sum(np.sqrt(1.0 + z * z) - 1.0) + 0.5 * np.sum((rates / RATE_SIGMA_S_H) ** 2)
        )

    def robust_gradient(rates: np.ndarray) -> np.ndarray:
        error = centered_response - centered_design @ rates
        derivative = error / (ROBUST_SCALE_HZ**2 * np.sqrt(1.0 + (error / ROBUST_SCALE_HZ) ** 2))
        return -centered_design.T @ derivative + rates / RATE_SIGMA_S_H**2

    optimized = minimize(
        robust_objective,
        np.zeros(len(sources)),
        jac=robust_gradient,
        method="L-BFGS-B",
        bounds=[(-RATE_BOUND_S_H, RATE_BOUND_S_H)] * len(sources),
        options={"maxiter": SCREENING_MAX_ITERATIONS, "ftol": 1e-11, "gtol": 1e-7},
    )
    rates = np.asarray(optimized.x, dtype=float)
    loss, cfo, _error = evaluate(rates)
    null_loss, null_cfo, _null_error = evaluate(np.zeros_like(rates))
    prior_penalty = float(PRIOR_SELECTION_WEIGHT * 0.5 * np.sum((rates / RATE_SIGMA_S_H) ** 2))
    objective = loss + prior_penalty
    # The null rate has zero prior penalty.  This guard prevents a location
    # from being promoted merely because the robust optimizer found a rate
    # that lowers its internal criterion but raises the published screen score.
    rejected = objective > null_loss + 1e-12
    if rejected:
        rates = np.zeros_like(rates)
        loss, cfo, _error = null_loss, null_cfo, _null_error
        prior_penalty, objective = 0.0, null_loss
    return {
        "selection_objective": float(objective),
        "full_observation_capped_loss": float(loss),
        "null_rate_full_observation_capped_loss": float(null_loss),
        "prior_penalty": float(prior_penalty),
        "rate_fit_rejected_by_screening_objective": bool(rejected),
        "converged": bool(optimized.success),
        "iterations": int(optimized.nit),
        "rate_corrections_s_h": {
            str(key): float(value) for key, value in zip(sources, rates, strict=True)
        },
        "track_cfo_hz": {str(key): float(value) for key, value in zip(tracks, cfo, strict=True)},
        "rate_boundary_count": int(np.sum(np.abs(rates) >= RATE_BOUND_S_H - 1e-8)),
        "maximum_phase_s": float(np.max(np.abs(support.age_h * rates[source_index]))),
    }


def _receipt_ages(
    engine: Any, orbit: Any, associations: list[dict[str, Any]]
) -> dict[tuple[str, str], float]:
    """Get causal TLE ages only for hard-selected NORADs and sessions."""
    selected: dict[str, set[str]] = {}
    for row in associations:
        if row["candidate_id"] is not None:
            selected.setdefault(str(row["session_id"]), set()).add(str(row["candidate_id"]))
    source_info = {}
    for session in engine.sessions:
        norads = selected.get(session.session_id, set())
        if not norads:
            continue
        receipt = json.loads((session.cache_path / "cache_receipt.json").read_text())
        evidence = receipt["prepared_evidence"]
        source_info[session.session_id] = {
            "snapshot_digest": evidence["snapshot_digest"],
            "capture_start_utc_ns": int(evidence["start_utc_ns"]),
            "norads": sorted(norads),
        }
    # Archive receipt binding is still verified by ``archive_payload``.  Cache
    # the immutable snapshot's epoch map so nine nearby screen points do not
    # repeatedly spawn a full TLE archive parse for the same causal snapshot.
    from leo.sky.propagation import parse_element_sets

    epochs: dict[tuple[str, str], int] = {}
    for sid, info in source_info.items():
        snapshot = str(info["snapshot_digest"])
        if snapshot not in _EPOCHS_BY_SNAPSHOT:
            catalogue = parse_element_sets(orbit.archive_payload(snapshot).decode("ascii"))
            _EPOCHS_BY_SNAPSHOT[snapshot] = dict(
                zip(
                    map(str, catalogue.satellite_numbers),
                    catalogue.element_epoch_utc_ns(),
                    strict=True,
                )
            )
        available = _EPOCHS_BY_SNAPSHOT[snapshot]
        for norad in info["norads"]:
            if norad not in available:
                raise ValueError(f"selected NORAD {norad} absent from causal snapshot")
            epochs[(sid, norad)] = available[norad]
    return {
        (sid, norad): (info["capture_start_utc_ns"] - epochs[(sid, norad)]) / 3.6e12
        for sid, info in source_info.items()
        for norad in info["norads"]
    }


def _candidate_predictions(
    engine: Any, session: Any, track: Any, lat: float, lon: float, tau: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nominal, visible = engine.predictions(session, track, lat, lon, tau)
    plus, _ = engine.predictions(session, track, lat, lon, tau + SENSITIVITY_DELTA_S)
    minus, _ = engine.predictions(session, track, lat, lon, tau - SENSITIVITY_DELTA_S)
    return nominal, visible, (plus - minus) / (2.0 * SENSITIVITY_DELTA_S)


def hard_support(
    engine: Any,
    orbit: Any,
    lat: float,
    lon: float,
    tau: float,
    rates: dict[str, float] | None = None,
    known_ages_h: dict[tuple[str, str], float] | None = None,
) -> Support:
    """Reacquire every track, then expose its cached phase-rate derivative."""
    rates, known_ages_h = rates or {}, known_ages_h or {}
    selected_rows: list[dict[str, Any]] = []
    fields: dict[str, list[np.ndarray]] = {
        key: [] for key in ("measured", "nominal", "sensitivity", "age", "source", "track")
    }
    weights: dict[str, int] = {}
    provisional: list[tuple[Any, Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for session in engine.sessions:
        for track in session.tracks:
            nominal, visible, sensitivity = _candidate_predictions(
                engine, session, track, lat, lon, tau
            )
            correction = np.asarray(
                [
                    sensitivity[n]
                    * known_ages_h.get((session.session_id, str(candidate)), 0.0)
                    * rates.get(str(candidate), 0.0)
                    for n, candidate in enumerate(session.candidate_id)
                ]
            )
            residual = track.measured[None, :] - nominal - correction
            cfo = np.mean(residual, axis=1)
            rms = np.sqrt(np.mean((residual - cfo[:, None]) ** 2, axis=1))
            rms = np.where(visible, rms, np.inf)
            winner = int(np.argmin(rms))
            candidate = str(session.candidate_id[winner]) if np.isfinite(rms[winner]) else None
            selected_rows.append(
                {
                    "session_id": session.session_id,
                    "track_id": track.track_id,
                    "candidate_id": candidate,
                }
            )
            provisional.append((session, track, nominal, sensitivity, rms, np.asarray([winner])))
    ages = _receipt_ages(engine, orbit, selected_rows)
    for (session, track, nominal, sensitivity, _rms, winner_array), selected in zip(
        provisional, selected_rows, strict=True
    ):
        if selected["candidate_id"] is None:
            continue
        winner = int(winner_array[0])
        name = f"{session.session_id}:{track.track_id}"
        fields["measured"].append(track.measured)
        fields["nominal"].append(nominal[winner])
        fields["sensitivity"].append(sensitivity[winner])
        fields["age"].append(
            np.full(
                len(track.times), ages[(session.session_id, selected["candidate_id"])], dtype=float
            )
        )
        # ``dtype=str`` without a width silently creates one-character arrays
        # on NumPy; object preserves NORAD and digest-bearing track labels.
        fields["source"].append(np.full(len(track.times), selected["candidate_id"], dtype=object))
        fields["track"].append(np.full(len(track.times), name, dtype=object))
        weights[name] = track.weight
    if not fields["measured"]:
        raise ValueError("no visible hard-associated tracks")
    return Support(
        measured=np.concatenate(fields["measured"]),
        nominal=np.concatenate(fields["nominal"]),
        sensitivity_hz_s=np.concatenate(fields["sensitivity"]),
        age_h=np.concatenate(fields["age"]),
        source=np.concatenate(fields["source"]),
        track=np.concatenate(fields["track"]),
        weights=weights,
        associations=selected_rows,
    )


def screen_point(
    engine: Any, orbit: Any, lat: float, lon: float, tau: float, reassign_once: bool
) -> dict[str, Any]:
    initial = hard_support(engine, orbit, lat, lon, tau)
    fit = fit_rate_support(initial)
    reassigned = False
    if reassign_once:
        ages = _receipt_ages(engine, orbit, initial.associations)
        refined = hard_support(engine, orbit, lat, lon, tau, fit["rate_corrections_s_h"], ages)
        fit = fit_rate_support(refined)
        initial = refined
        reassigned = True
    return {
        "latitude_deg": float(lat),
        "longitude_deg": float(lon),
        "tau_s": float(tau),
        "selection_uses_reference": False,
        "hard_reassignment_after_rate_fit": reassigned,
        "track_associations": initial.associations,
        "fit": fit,
    }


def task_from_finalist(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text())
    forbidden = {"reference", "truth", "reference_coordinate"} & document.keys()
    if forbidden or document.get("reference_used_for_fit") is not False:
        raise ValueError(f"finalist must be a reference-free sealed inference: {path}")
    return {
        "task_id": "joint-rate-" + str(document["task_id"]),
        "group_id": str(document["group_id"]),
        "session_ids": list(map(str, document["session_ids"])),
        "session_groups": dict(document["session_groups"]),
        "prior": dict(document["prior"]),
        "method": "causal_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def exact_comparison(existing: Any, orbit: Any, engine: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Use exact SGP4 only to audit the surrogate-selected support/location."""
    begun = time.perf_counter()
    prepared = existing._make_exact_prepared(
        engine,
        orbit,
        row["latitude_deg"],
        row["longitude_deg"],
        row["tau_s"],
        row["track_associations"],
    )
    receiver, _up = engine.search.receiver_ecef(row["latitude_deg"], row["longitude_deg"])
    fit = existing._rate_fit_full(prepared, receiver, engine.search, orbit)
    exact_s = time.perf_counter() - begun
    surrogate = row["fit"]
    return {
        "exact_elapsed_s": exact_s,
        "exact_full_observation_capped_loss": fit["full_observation_capped_loss"],
        "surrogate_full_observation_capped_loss": surrogate["full_observation_capped_loss"],
        "absolute_capped_loss_error": abs(
            fit["full_observation_capped_loss"] - surrogate["full_observation_capped_loss"]
        ),
        "exact_rate_corrections_s_h": fit["rate_corrections_s_h"],
        "surrogate_rate_corrections_s_h": surrogate["rate_corrections_s_h"],
        "exact_sgp4_gate": orbit.exact_replay_gate(
            prepared, receiver, engine.search, row["tau_s"], fit["rate_corrections_s_h"]
        ),
    }


def run_finalist(path: Path, spacing_km: float, reassign_once: bool) -> dict[str, Any]:
    existing = load(RUNNER_PATH, "ds1_joint_existing_runner")
    orbit = load(ORBIT_PATH, "ds1_joint_exact_orbit")
    task = task_from_finalist(path)
    engine = existing.FullObservationEngine(existing.validate_task(task))
    sealed = json.loads(path.read_text())
    centre = sealed["estimated_position"]
    started = time.perf_counter()
    rows = []
    # A 3x3 local basin is deliberately bounded.  Each entry uses all tracks
    # and a fresh hard association; no row can read a prior row's identity.
    for east in (-spacing_km, 0.0, spacing_km):
        for north in (-spacing_km, 0.0, spacing_km):
            lat, lon = engine.search.offset_coordinate(
                (centre["latitude_deg"], centre["longitude_deg"]), east, north
            )
            row = screen_point(engine, orbit, lat, lon, sealed["global_tau_s"], reassign_once)
            row["east_from_sealed_finalist_km"] = east
            row["north_from_sealed_finalist_km"] = north
            rows.append(row)
    surrogate_s = time.perf_counter() - started
    winner = min(
        rows,
        key=lambda row: (
            row["fit"]["selection_objective"],
            abs(row["east_from_sealed_finalist_km"]) + abs(row["north_from_sealed_finalist_km"]),
            row["east_from_sealed_finalist_km"],
            row["north_from_sealed_finalist_km"],
        ),
    )
    comparison = exact_comparison(existing, orbit, engine, winner)
    comparison["surrogate_total_elapsed_s"] = surrogate_s
    comparison["surrogate_mean_elapsed_s_per_point"] = surrogate_s / len(rows)
    comparison["exact_to_surrogate_per_point_speed_ratio"] = (
        comparison["exact_elapsed_s"] / comparison["surrogate_mean_elapsed_s_per_point"]
    )
    return {
        "sealed_finalist": str(path),
        "sealed_finalist_sha256": digest(path),
        "reference_used_for_fit": False,
        "all_qualified_observations_used": True,
        "local_basin_spacing_km": spacing_km,
        "rows": rows,
        "winner": winner,
        "exact_comparison": comparison,
        "cache_bindings": engine.bindings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed-finalist", action="append", type=Path, required=True)
    parser.add_argument("--spacing-km", type=float, default=2.0)
    parser.add_argument("--reassign-once", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.spacing_km <= 0:
        raise ValueError("spacing must be positive")
    if args.output.exists():
        raise FileExistsError(args.output)
    result = {
        "schema": "ds1-joint-rate-cache-screening-prototype/v1",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "rate_definition": "per-NORAD phase_s=causal_TLE_age_h*rate_s_h",
        "surrogate": {
            "doppler_sensitivity": "central cached prediction difference at tau +/- 1 second",
            "sensitivity_delta_s": SENSITIVITY_DELTA_S,
            "earth_rotation_caveat": (
                "cache time displacement advances Earth rotation; exact SGP4 audit fixes Earth "
                "at receive+tau"
            ),
            "rate_sigma_s_h": RATE_SIGMA_S_H,
            "rate_bound_s_h": RATE_BOUND_S_H,
            "prior_selection_weight": PRIOR_SELECTION_WEIGHT,
            "screening_max_iterations": SCREENING_MAX_ITERATIONS,
            "reassign_once": bool(args.reassign_once),
        },
        "results": [
            run_finalist(path, args.spacing_km, args.reassign_once) for path in args.sealed_finalist
        ],
        "bindings": {
            "prototype": digest(Path(__file__)),
            "existing_runner": digest(RUNNER_PATH),
            "exact_orbit": digest(ORBIT_PATH),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(result["results"])}, sort_keys=True))


if __name__ == "__main__":
    main()
