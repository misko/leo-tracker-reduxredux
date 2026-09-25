#!/usr/bin/env python3
"""Audit predeclared widened TRAIN-only per-NORAD rate bounds for DS1."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
DATASET = ROOT / "reports/2026_09_24_ds1/dataset.json"
DS1_RUNNER = ROOT / "reports/2026_09_24_ds1/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
GROUPS = ("20260921_00", "20260921_16")
CASE_IDS = {group: f"train_{group}_6" for group in GROUPS}
SEEDS = {
    group: ROOT / f"reports/2026_09_24_ds1/inference/train_{group}_6__reno.json" for group in GROUPS
}
CAP_HZ = 800.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUNDS_S_H = (0.25, 0.50, 1.0)
RATE_XATOL_S_H = 2e-7
RATE_PROFILE_MAX_PHASE_STEP_S = 0.05
PROFILE_AMBIGUITY_RELATIVE_OBJECTIVE = 1e-6
ROBUST_SCALE_HZ = 250.0


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verified_json(path: Path, seal: Path | None = None) -> dict[str, Any]:
    if seal is None:
        seal = path.with_suffix(path.suffix + ".sha256")
    expected = seal.read_text().strip().split()[0]
    if digest(path).split(":", 1)[1] != expected:
        raise ValueError(f"seal mismatch: {path}")
    return json.loads(path.read_text())


def load_case(group: str) -> dict[str, Any]:
    dataset = json.loads(DATASET.read_text())
    case = next(row for row in dataset["cases"] if row["case_id"] == CASE_IDS[group])
    if (
        case["partition"] != "train"
        or case["group_id"] != group
        or case["scan_count"] != 6
        or len(case["session_ids"]) != 6
    ):
        raise ValueError("unexpected DS1 case contract")
    return case


def load_train_selected_point(group: str) -> dict[str, float]:
    source = verified_json(SEEDS[group], SEEDS[group].with_suffix(".sha256"))
    if (
        source.get("complete") is not True
        or source.get("held_used_for_fit") is not False
        or source.get("truth_used_for_fit") is not False
        or source.get("case_id") != CASE_IDS[group]
        or source.get("prior") != "reno"
    ):
        raise ValueError("seed is not a sealed TRAIN-only DS1 inference")
    winner = source["models"]["shared_time"]
    return {
        "latitude_deg": float(winner["latitude_deg"]),
        "longitude_deg": float(winner["longitude_deg"]),
        "tau_s": float(winner["tau_s"]),
    }


def unsupported_by_session(engine: Any, assignments: list[dict[str, Any]]) -> dict[str, Any]:
    selected = {(str(row["session_id"]), str(row["track_id"])) for row in assignments}
    sessions: dict[str, dict[str, float | int]] = {}
    for session in engine.sessions:
        sid = str(session["session_id"])
        missing = [
            track for track in session["tracks"] if (sid, str(track["track_id"])) not in selected
        ]
        sessions[sid] = {
            "track_count": len(missing),
            "occupied_second_weight": float(sum(track["weight"] for track in missing)),
        }
    return sessions


def score_rates(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    rates_by_source: dict[str, float],
    unsupported: dict[str, Any],
) -> dict[str, Any]:
    """Fit CFO on TRAIN only and score TRAIN/HELD without cross-mask leakage."""
    source_names, source_index = np.unique(data.source.astype(str), return_inverse=True)
    if set(rates_by_source) != set(source_names):
        raise ValueError("rate/source membership mismatch")
    rates = np.asarray([float(rates_by_source[name]) for name in source_names], float)
    phase = data.age_h * rates[source_index]
    prediction = orbit.doppler(
        receiver,
        orbit.quartic(data.p_nodes, phase),
        orbit.quartic(data.v_nodes, phase),
        search,
    )
    raw = data.y - prediction
    track_names, track_index = np.unique(data.track.astype(str), return_inverse=True)
    offsets = np.empty(len(track_names), float)
    session_rows: dict[str, dict[str, Any]] = {}
    track_rows = []
    for index, track in enumerate(track_names):
        rows = track_index == index
        train = rows & data.train
        held = rows & ~data.train
        if not np.any(train) or not np.any(held):
            raise ValueError(f"track lacks TRAIN or HELD rows: {track}")
        offsets[index] = float(np.mean(raw[train]))
        error = raw[rows] - offsets[index]
        local_train = data.train[rows]
        train_rms = float(np.sqrt(np.mean(error[local_train] ** 2)))
        held_rms = float(np.sqrt(np.mean(error[~local_train] ** 2)))
        sid = str(data.session[np.flatnonzero(rows)[0]])
        if not np.all(data.session[rows].astype(str) == sid):
            raise ValueError("track crosses recording sessions")
        weight = float(data.weights[str(track)])
        item = session_rows.setdefault(
            sid,
            {
                "session_id": sid,
                "supported_track_count": 0,
                "unsupported_track_count": int(unsupported[sid]["track_count"]),
                "supported_weight": 0.0,
                "unsupported_weight": float(unsupported[sid]["occupied_second_weight"]),
                "train_numerator": float(unsupported[sid]["occupied_second_weight"]),
                "held_numerator": float(unsupported[sid]["occupied_second_weight"]),
            },
        )
        item["supported_track_count"] += 1
        item["supported_weight"] += weight
        item["train_numerator"] += weight * min((train_rms / CAP_HZ) ** 2, 1.0)
        item["held_numerator"] += weight * min((held_rms / CAP_HZ) ** 2, 1.0)
        track_rows.append(
            {
                "track_id": str(track),
                "session_id": sid,
                "source": str(data.source[np.flatnonzero(rows)[0]]),
                "train_observations": int(train.sum()),
                "held_observations": int(held.sum()),
                "occupied_second_weight": weight,
                "training_cfo_hz": offsets[index],
                "training_rms_hz": train_rms,
                "held_rms_hz": held_rms,
            }
        )
    sessions = []
    for sid in sorted(unsupported):
        if sid not in session_rows:
            missing = unsupported[sid]
            if not missing["track_count"]:
                raise ValueError("session has no scored tracks")
            session_rows[sid] = {
                "session_id": sid,
                "supported_track_count": 0,
                "unsupported_track_count": int(missing["track_count"]),
                "supported_weight": 0.0,
                "unsupported_weight": float(missing["occupied_second_weight"]),
                "train_numerator": float(missing["occupied_second_weight"]),
                "held_numerator": float(missing["occupied_second_weight"]),
            }
        row = session_rows[sid]
        denominator = row["supported_weight"] + row["unsupported_weight"]
        if denominator <= 0:
            raise ValueError("session denominator is empty")
        sessions.append(
            {
                **{k: v for k, v in row.items() if not k.endswith("_numerator")},
                "occupied_second_weight": denominator,
                "training_capped_loss": row["train_numerator"] / denominator,
                "held_capped_loss": row["held_numerator"] / denominator,
            }
        )
    return {
        "equal_session_training_capped_loss": float(
            np.mean([row["training_capped_loss"] for row in sessions])
        ),
        "equal_session_held_capped_loss": float(
            np.mean([row["held_capped_loss"] for row in sessions])
        ),
        "session_scores": sessions,
        "track_scores": track_rows,
    }


def boundary_tolerance_s_h(bound_s_h: float) -> float:
    """Numerical guard wide enough for bounded minimizer termination."""
    return float(max(5.0 * RATE_XATOL_S_H, 32.0 * np.finfo(float).eps * max(1.0, bound_s_h)))


def rate_distribution(rates: list[float]) -> dict[str, Any]:
    values = np.asarray(rates, dtype=float)
    absolute = np.abs(values)
    return {
        "minimum_s_h": float(values.min()),
        "q05_s_h": float(np.quantile(values, 0.05)),
        "q25_s_h": float(np.quantile(values, 0.25)),
        "median_s_h": float(np.median(values)),
        "q75_s_h": float(np.quantile(values, 0.75)),
        "q95_s_h": float(np.quantile(values, 0.95)),
        "maximum_s_h": float(values.max()),
        "maximum_absolute_s_h": float(absolute.max()),
        "mean_s_h": float(values.mean()),
        "standard_deviation_s_h": float(values.std()),
        "negative_count": int((values < 0).sum()),
        "zero_count": int((values == 0).sum()),
        "positive_count": int((values > 0).sum()),
    }


def global_profile_minimize(
    objective: Any,
    bound_s_h: float,
    maximum_abs_age_h: float = 1.0,
    objective_many: Any | None = None,
) -> dict[str, Any]:
    """Deterministically profile a possibly non-unimodal scalar objective."""
    if maximum_abs_age_h < 0:
        raise ValueError("maximum absolute age must be nonnegative")
    grid_intervals = max(
        2,
        int(np.ceil(2.0 * bound_s_h * maximum_abs_age_h / RATE_PROFILE_MAX_PHASE_STEP_S)),
    )
    grid = np.linspace(-bound_s_h, bound_s_h, grid_intervals + 1)
    grid_step = float(grid[1] - grid[0])
    evaluations = 0

    def measured(rate: float) -> float:
        nonlocal evaluations
        evaluations += 1
        return float(objective(float(rate)))

    def measured_many(rates: np.ndarray) -> np.ndarray:
        nonlocal evaluations
        values = np.asarray(rates, dtype=float)
        evaluations += len(values)
        if objective_many is None:
            return np.asarray([objective(float(rate)) for rate in values], dtype=float)
        return np.asarray(objective_many(values), dtype=float)

    grid_objectives = measured_many(grid)
    half_grid = (grid[:-1] + grid[1:]) / 2.0
    half_objectives = measured_many(half_grid)
    verification_grid = np.empty(len(grid) + len(half_grid), dtype=float)
    verification_objectives = np.empty_like(verification_grid)
    verification_grid[0::2] = grid
    verification_grid[1::2] = half_grid
    verification_objectives[0::2] = grid_objectives
    verification_objectives[1::2] = half_objectives
    candidates = [
        {
            "kind": "negative_endpoint",
            "rate_s_h": float(grid[0]),
            "objective": float(grid_objectives[0]),
        },
        {
            "kind": "positive_endpoint",
            "rate_s_h": float(grid[-1]),
            "objective": float(grid_objectives[-1]),
        },
        {"kind": "zero", "rate_s_h": 0.0, "objective": measured(0.0)},
    ]
    refinements = []
    for index in range(1, len(verification_grid) - 1):
        center = verification_objectives[index]
        if (
            center <= verification_objectives[index - 1]
            and center <= verification_objectives[index + 1]
        ):
            result = minimize_scalar(
                measured,
                bounds=(
                    float(verification_grid[index - 1]),
                    float(verification_grid[index + 1]),
                ),
                method="bounded",
                options={"xatol": RATE_XATOL_S_H, "maxiter": 100},
            )
            refinement = {
                "grid_index": index,
                "bracket_s_h": [
                    float(verification_grid[index - 1]),
                    float(verification_grid[index + 1]),
                ],
                "rate_s_h": float(result.x),
                "objective": float(result.fun),
                "converged": bool(result.success),
                "function_evaluations": int(result.nfev),
                "message": str(result.message),
            }
            refinements.append(refinement)
            candidates.append({"kind": "refined_local_minimum", **refinement})
    winner = min(
        candidates,
        key=lambda row: (
            float(row["objective"]),
            abs(float(row["rate_s_h"])),
            float(row["rate_s_h"]),
        ),
    )
    legacy = minimize_scalar(
        measured,
        bounds=(-bound_s_h, bound_s_h),
        method="bounded",
        options={"xatol": RATE_XATOL_S_H, "maxiter": 100},
    )
    distinct = []
    for candidate in sorted(candidates, key=lambda row: float(row["objective"])):
        if all(
            abs(float(candidate["rate_s_h"]) - float(existing["rate_s_h"]))
            > boundary_tolerance_s_h(bound_s_h)
            for existing in distinct
        ):
            distinct.append(candidate)
    second = distinct[1] if len(distinct) > 1 else None
    gap = float(second["objective"] - winner["objective"]) if second is not None else None
    ambiguity_tolerance = float(
        PROFILE_AMBIGUITY_RELATIVE_OBJECTIVE * max(1.0, abs(float(winner["objective"])))
    )
    verification_tolerance = float(
        64.0 * np.finfo(float).eps * max(1.0, abs(float(winner["objective"])))
    )
    return {
        "rate_s_h": float(winner["rate_s_h"]),
        "training_objective": float(winner["objective"]),
        "winner_kind": winner["kind"],
        "converged": all(row["converged"] for row in refinements),
        "local_minimum_count": len(refinements),
        "distinct_candidate_count": len(distinct),
        "best_vs_second": {
            "second_rate_s_h": None if second is None else float(second["rate_s_h"]),
            "second_training_objective": None if second is None else float(second["objective"]),
            "rate_separation_s_h": None
            if second is None
            else abs(float(second["rate_s_h"]) - float(winner["rate_s_h"])),
            "objective_gap": gap,
            "ambiguity_tolerance": ambiguity_tolerance,
            "ambiguous": bool(gap is not None and gap <= ambiguity_tolerance),
        },
        "refinements": refinements,
        "grid": {
            "phase_step_limit_s": RATE_PROFILE_MAX_PHASE_STEP_S,
            "maximum_abs_age_h": maximum_abs_age_h,
            "coarse_step_s_h": grid_step,
            "coarse_maximum_phase_step_s": maximum_abs_age_h * grid_step,
            "point_count": len(grid),
            "half_step_verification_point_count": len(half_grid),
            "half_step_s_h": grid_step / 2.0,
            "minimum_s_h": float(grid[0]),
            "maximum_s_h": float(grid[-1]),
            "half_step_verification": {
                "best_sample_rate_s_h": float(
                    verification_grid[int(np.argmin(verification_objectives))]
                ),
                "best_sample_objective": float(np.min(verification_objectives)),
                "selected_minus_best_sample_objective": float(
                    winner["objective"] - np.min(verification_objectives)
                ),
                "tolerance": verification_tolerance,
                "passed": bool(
                    winner["objective"] <= np.min(verification_objectives) + verification_tolerance
                ),
            },
        },
        "function_evaluations": evaluations,
        "legacy_bounded": {
            "rate_s_h": float(legacy.x),
            "training_objective": float(legacy.fun),
            "converged": bool(legacy.success),
            "function_evaluations": int(legacy.nfev),
            "message": str(legacy.message),
            "rate_difference_global_minus_legacy_s_h": float(winner["rate_s_h"] - legacy.x),
            "objective_improvement_global_minus_legacy": float(winner["objective"] - legacy.fun),
        },
    }


def fit_train_rates(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    bound_s_h: float,
) -> dict[str, Any]:
    """Fit independent per-source rates from TRAIN rows and TRAIN CFOs only."""
    # Construct membership and every objective input from TRAIN rows.  In
    # particular, HELD source labels, geometry, values, and counts cannot alter
    # the optimizer calls or their control flow.
    train_rows = np.asarray(data.train, dtype=bool)
    source_values = data.source.astype(str)
    track_values = data.track.astype(str)
    source_names = np.unique(source_values[train_rows])
    fitted: dict[str, float] = {}
    rows_out = []
    for source in source_names:
        selected_rows = np.flatnonzero(train_rows & (source_values == source))
        tracks = np.unique(track_values[selected_rows])
        selected_tracks = tuple(str(track) for track in tracks)

        def objective(
            rate: float,
            rows: np.ndarray = selected_rows,
            local_tracks: tuple[str, ...] = selected_tracks,
        ) -> float:
            phase = data.age_h[rows] * float(rate)
            prediction = orbit.doppler(
                receiver,
                orbit.quartic(data.p_nodes[rows], phase),
                orbit.quartic(data.v_nodes[rows], phase),
                search,
            )
            raw = data.y[rows] - prediction
            local_track = track_values[rows]
            errors = []
            for track in local_tracks:
                selected = local_track == track
                if not np.any(selected):
                    raise ValueError(f"source track lacks TRAIN rows: {track}")
                cfo = float(np.mean(raw[selected]))
                errors.append(raw[selected] - cfo)
            error = np.concatenate(errors)
            z = error / ROBUST_SCALE_HZ
            return float(
                np.sum(np.sqrt(1.0 + z * z) - 1.0) + 0.5 * (float(rate) / RATE_SIGMA_S_H) ** 2
            )

        local_age_h = np.asarray(data.age_h[selected_rows], dtype=float)
        local_y = np.asarray(data.y[selected_rows], dtype=float)
        local_p_nodes = np.asarray(data.p_nodes[selected_rows], dtype=float)
        local_v_nodes = np.asarray(data.v_nodes[selected_rows], dtype=float)
        local_track = track_values[selected_rows]

        def objective_many(
            rates: np.ndarray,
            ages: np.ndarray = local_age_h,
            observations: np.ndarray = local_y,
            position_nodes: np.ndarray = local_p_nodes,
            velocity_nodes: np.ndarray = local_v_nodes,
            observation_tracks: np.ndarray = local_track,
            source_tracks: tuple[str, ...] = selected_tracks,
        ) -> np.ndarray:
            rates = np.asarray(rates, dtype=float)
            answers = np.empty(len(rates), dtype=float)
            chunk_size = 128
            for start in range(0, len(rates), chunk_size):
                selected_rates = rates[start : start + chunk_size]
                count = len(selected_rates)
                phase = (selected_rates[:, None] * ages[None, :]).reshape(-1)
                prediction = orbit.doppler(
                    receiver,
                    orbit.quartic(np.tile(position_nodes, (count, 1, 1)), phase),
                    orbit.quartic(np.tile(velocity_nodes, (count, 1, 1)), phase),
                    search,
                ).reshape(count, len(observations))
                raw = observations[None, :] - prediction
                total = np.zeros(count, dtype=float)
                for track in source_tracks:
                    selected = observation_tracks == track
                    error = raw[:, selected] - np.mean(raw[:, selected], axis=1)[:, None]
                    z = error / ROBUST_SCALE_HZ
                    total += np.sum(np.sqrt(1.0 + z * z) - 1.0, axis=1)
                answers[start : start + count] = (
                    total + 0.5 * (selected_rates / RATE_SIGMA_S_H) ** 2
                )
            return answers

        maximum_abs_age_h = float(np.max(np.abs(local_age_h)))
        result = global_profile_minimize(
            objective,
            bound_s_h,
            maximum_abs_age_h=maximum_abs_age_h,
            objective_many=objective_many,
        )
        fitted[str(source)] = float(result["rate_s_h"])
        rows_out.append(
            {
                "source": str(source),
                "training_observations": len(selected_rows),
                "training_tracks": len(selected_tracks),
                "maximum_abs_age_h": maximum_abs_age_h,
                "maximum_abs_fitted_phase_s": maximum_abs_age_h * abs(float(result["rate_s_h"])),
                **result,
            }
        )
    tolerance = boundary_tolerance_s_h(bound_s_h)
    boundary_rows = [row for row in rows_out if bound_s_h - abs(row["rate_s_h"]) <= tolerance]
    return {
        "rates_s_h": fitted,
        "sources": rows_out,
        "converged": all(row["converged"] for row in rows_out),
        "source_count": len(rows_out),
        "rate_bound_s_h": bound_s_h,
        "rate_xatol_s_h": RATE_XATOL_S_H,
        "boundary_tolerance_s_h": tolerance,
        "boundary_tolerance_definition": "max(5*xatol, 32*machine_epsilon*max(1,bound))",
        "effective_boundary_rate_count": len(boundary_rows),
        "effective_boundary_sources": [row["source"] for row in boundary_rows],
        "total_function_evaluations": int(sum(row["function_evaluations"] for row in rows_out)),
        "global_vs_legacy_rate_discrepancy_tolerance_s_h": tolerance,
        "global_vs_legacy_rate_discrepancy_count": sum(
            abs(row["legacy_bounded"]["rate_difference_global_minus_legacy_s_h"]) > tolerance
            for row in rows_out
        ),
        "global_better_than_legacy_objective_count": sum(
            row["legacy_bounded"]["objective_improvement_global_minus_legacy"] < -1e-9
            for row in rows_out
        ),
        "ambiguous_profile_count": sum(row["best_vs_second"]["ambiguous"] for row in rows_out),
        "ambiguous_profile_sources": [
            row["source"] for row in rows_out if row["best_vs_second"]["ambiguous"]
        ],
        "half_step_verification_failure_count": sum(
            not row["grid"]["half_step_verification"]["passed"] for row in rows_out
        ),
        "maximum_abs_fitted_phase_s": max(row["maximum_abs_fitted_phase_s"] for row in rows_out),
        "rate_distribution": rate_distribution([row["rate_s_h"] for row in rows_out]),
    }


def session_held_changes(
    candidate: dict[str, Any], baseline: dict[str, Any]
) -> list[dict[str, Any]]:
    baseline_by_session = {row["session_id"]: row for row in baseline["session_scores"]}
    if set(baseline_by_session) != {row["session_id"] for row in candidate["session_scores"]}:
        raise ValueError("session membership mismatch")
    return [
        {
            "session_id": row["session_id"],
            "baseline_held_capped_loss": baseline_by_session[row["session_id"]]["held_capped_loss"],
            "candidate_held_capped_loss": row["held_capped_loss"],
            "candidate_minus_baseline": row["held_capped_loss"]
            - baseline_by_session[row["session_id"]]["held_capped_loss"],
        }
        for row in candidate["session_scores"]
    ]


def exact_train_profile_audit(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    tau_s: float,
    source: str,
    rates_s_h: list[float],
) -> dict[str, Any]:
    """Exact-SGP4 score near-tied TRAIN candidates without changing selection."""
    replay = load_module(ROOT / "tools/replay_regional_doppler.py", f"i23_exact_profile_{source}")
    from leo.sky.propagation import parse_element_sets

    payloads: dict[str, Any] = {}
    rows_by_session = []
    for sid, info in data.sources.items():
        rows = np.flatnonzero(
            (data.session.astype(str) == str(sid))
            & (data.source.astype(str) == str(source))
            & np.asarray(data.train, dtype=bool)
        )
        if not len(rows):
            continue
        ages = np.asarray(data.age_h[rows], dtype=float)
        if np.max(ages) - np.min(ages) > 1e-12:
            raise ValueError("source/session causal age is not constant")
        payload = payloads.setdefault(
            info["snapshot_digest"], orbit.archive_payload(info["snapshot_digest"])
        )
        catalogue = parse_element_sets(payload.decode("ascii"))
        index = {str(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        rows_by_session.append((rows, catalogue, index[str(source)], float(ages[0])))
    if not rows_by_session:
        raise ValueError(f"exact TRAIN audit source is absent: {source}")
    results = []
    for rate in rates_s_h:
        raw_by_track: dict[str, list[np.ndarray]] = {}
        maximum_phase_s = 0.0
        observations = 0
        for rows, catalogue, source_index, age_h in rows_by_session:
            phase_s = age_h * float(rate)
            p, v, valid = replay.state_arrays(
                catalogue,
                [source_index],
                int(data.sources[str(data.session[rows[0]])]["capture_start_utc_ns"]),
                data.time_s[rows],
                orbit_time_s=phase_s,
                clock_s=float(tau_s),
            )
            if len(valid) != 1:
                raise ValueError("exact near-tied TRAIN propagation failed")
            raw = np.asarray(data.y[rows], dtype=float) - orbit.doppler(
                receiver, p[0], v[0], search
            )
            for track in np.unique(data.track[rows].astype(str)):
                selected = data.track[rows].astype(str) == track
                raw_by_track.setdefault(str(track), []).append(raw[selected])
            maximum_phase_s = max(maximum_phase_s, abs(phase_s))
            observations += len(rows)
        objective = 0.5 * (float(rate) / RATE_SIGMA_S_H) ** 2
        for pieces in raw_by_track.values():
            raw = np.concatenate(pieces)
            error = raw - np.mean(raw)
            z = error / ROBUST_SCALE_HZ
            objective += float(np.sum(np.sqrt(1.0 + z * z) - 1.0))
        results.append(
            {
                "rate_s_h": float(rate),
                "training_objective": objective,
                "training_observations": observations,
                "training_tracks": len(raw_by_track),
                "maximum_abs_phase_s": maximum_phase_s,
            }
        )
    return {
        "source": source,
        "candidates": results,
        "objective_second_minus_selected": results[1]["training_objective"]
        - results[0]["training_objective"],
        "selected_rate_remains_exact_preferred": bool(
            results[0]["training_objective"] <= results[1]["training_objective"]
        ),
        "used_for_selection_or_gate": False,
    }


def run_group(group: str) -> dict[str, Any]:
    begun = time.perf_counter()
    ds1 = load_module(DS1_RUNNER, f"i22_ds1_{group}")
    orbit = load_module(ORBIT, f"i22_orbit_{group}")
    case = load_case(group)
    point = load_train_selected_point(group)
    _clock, engine = ds1.make_engine(case)
    # The original DS1 engine verifies each receipt/cache pair but does not
    # retain the directory in its session dictionary.  The exact orbit builder
    # needs that already-verified directory to read causal TLE provenance.
    for session in engine.sessions:
        session["cache_path"] = str(ds1.CACHE_ROOTS[group] / session["session_id"])
    data = orbit.prepare(
        engine,
        point["latitude_deg"],
        point["longitude_deg"],
        point["tau_s"],
    )
    receiver, _up = engine.search.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
    unsupported = unsupported_by_session(engine, data.assignments)
    sources = tuple(sorted(np.unique(data.source.astype(str))))
    zero_rates = {source: 0.0 for source in sources}
    # The complete bound schedule is fit before any HELD score is calculated.
    # It is unconditional: no result from an earlier stage can stop or widen it.
    fits = [
        fit_train_rates(data, receiver, engine.search, orbit, bound) for bound in RATE_BOUNDS_S_H
    ]
    half_fit = fits[1]
    by_source = {row["source"]: row for row in half_fit["sources"]}
    half_fit["ambiguous_profile_exact_train_audits"] = [
        exact_train_profile_audit(
            data,
            receiver,
            engine.search,
            orbit,
            point["tau_s"],
            source,
            [
                by_source[source]["rate_s_h"],
                by_source[source]["best_vs_second"]["second_rate_s_h"],
            ],
        )
        for source in half_fit["ambiguous_profile_sources"]
    ]
    zero_score = score_rates(data, receiver, engine.search, orbit, zero_rates, unsupported)
    zero_gate = orbit.exact_replay_gate(
        data, receiver, engine.search, point["tau_s"], zero_rates, tolerance_hz=0.2
    )
    stages = []
    quarter_score = None
    for fit in fits:
        fitted_rates = fit["rates_s_h"]
        score = score_rates(data, receiver, engine.search, orbit, fitted_rates, unsupported)
        if quarter_score is None:
            quarter_score = score
        gate = orbit.exact_replay_gate(
            data, receiver, engine.search, point["tau_s"], fitted_rates, tolerance_hz=0.2
        )
        stages.append(
            {
                "rate_bound_s_h": fit["rate_bound_s_h"],
                "fit": fit,
                "score": score,
                "exact_sgp4_gate": gate,
                "held_delta_vs_zero": score["equal_session_held_capped_loss"]
                - zero_score["equal_session_held_capped_loss"],
                "held_delta_vs_quarter": score["equal_session_held_capped_loss"]
                - quarter_score["equal_session_held_capped_loss"],
                "session_held_changes_vs_zero": session_held_changes(score, zero_score),
                "session_held_changes_vs_quarter": session_held_changes(score, quarter_score),
            }
        )
    prospective = stages[1]
    return {
        "group_id": group,
        "case_id": case["case_id"],
        "fixed_point": point,
        "mask_counts": {
            "training_observations": int(data.train.sum()),
            "held_observations": int((~data.train).sum()),
            "supported_tracks": len(data.weights),
            "unsupported_tracks": int(sum(row["track_count"] for row in unsupported.values())),
            "sessions": len(np.unique(data.session.astype(str))),
            "sources": len(sources),
        },
        "identity_selection": "ordinary DS1 hard association on randomized TRAIN rows only",
        "zero_rate": {"score": zero_score, "exact_sgp4_gate": zero_gate},
        "rate_schedule": stages,
        "training_side_half_bound_gate": {
            "passed": bool(
                prospective["fit"]["converged"]
                and prospective["fit"]["effective_boundary_rate_count"] == 0
                and prospective["fit"]["ambiguous_profile_count"] == 0
                and prospective["fit"]["half_step_verification_failure_count"] == 0
                and prospective["exact_sgp4_gate"]["passed"]
            ),
            "rate_bound_s_h": 0.5,
            "criteria": [
                "all half-bound TRAIN local refinements converge",
                "no half-bound fit is active under the recorded optimizer-aware tolerance",
                "no half-bound best/second profile is ambiguous",
                "all half-step verification scans cover the selected TRAIN minimum",
                "half-bound exact SGP4 replay gate passes",
            ],
            "held_used": False,
            "one_second_bound_used": False,
        },
        "bindings": {
            "seed": digest(SEEDS[group]),
            "session_bindings": engine.bindings,
        },
        "elapsed_s": time.perf_counter() - begun,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    plan = verified_json(PLAN)
    if (
        plan.get("status") != "fixed-widening-audit-no-geographic-search"
        or plan.get("reference_used_for_inference") is not False
    ):
        raise ValueError("plan does not authorize this fixed widening audit")
    groups = [run_group(group) for group in GROUPS]
    output = {
        "schema": "ds1-iteration23-widened-rate-audit/v1",
        "complete": True,
        "reference_used": False,
        "held_used_for_selection": False,
        "geographic_search_run": False,
        "groups": groups,
        "summary": {
            "group_count": len(groups),
            "predeclared_rate_bounds_s_h": list(RATE_BOUNDS_S_H),
            "all_training_side_half_bound_gates_passed": all(
                row["training_side_half_bound_gate"]["passed"] for row in groups
            ),
            "half_bound_effective_boundary_rate_count": sum(
                row["rate_schedule"][1]["fit"]["effective_boundary_rate_count"] for row in groups
            ),
            "one_second_diagnostic_boundary_rate_count": sum(
                row["rate_schedule"][2]["fit"]["effective_boundary_rate_count"] for row in groups
            ),
            "prospective_geographic_basin": {
                "decision": "go"
                if all(row["training_side_half_bound_gate"]["passed"] for row in groups)
                else "no-go",
                "rate_bound_s_h": 0.5,
                "basis": (
                    "predeclared half-bound TRAIN-only convergence, boundary, "
                    "profile-ambiguity, half-step-coverage, and exact-replay gates"
                ),
                "held_used_for_decision": False,
                "one_second_diagnostic_used_for_decision": False,
                "scope": (
                    "permission to design a separately sealed prospective basin; "
                    "this run launches none"
                ),
            },
        },
        "bindings": {
            "plan": digest(PLAN),
            "dataset": digest(DATASET),
            "runner": digest(Path(__file__)),
            "ds1_runner": digest(DS1_RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary": output["summary"],
                "decision": output["summary"]["prospective_geographic_basin"]["decision"],
                "half_bound_boundaries": output["summary"][
                    "half_bound_effective_boundary_rate_count"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
