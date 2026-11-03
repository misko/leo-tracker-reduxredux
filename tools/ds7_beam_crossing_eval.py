#!/usr/bin/env python3
"""Bounded evaluator for the conditional DS7 paired-receiver beam pilot.

This runner consumes only the frozen compact JSON contract.  It does not read
IQ, fit a position, or turn missing counterparts into target non-detections.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import ds7_beam_crossing as core
import numpy as np

SEED = 20260928
RIDGE = 1.0
MAXITER = 300
MAXFUN = 5000
ARMS = ("static_ou", "temporal_ou", "geometry_free_ou", "static_iid", "geometry_free_iid")


@dataclass(frozen=True)
class PreparedTrack:
    session_id: str
    track: core.ConditionalTrack
    channel: np.ndarray
    edge: np.ndarray
    sample_rate_hz: np.ndarray
    log_anchor_margin: np.ndarray


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_split(session_ids: list[str]) -> tuple[list[str], list[str]]:
    """Return the outcome-independent frozen six/four recording assignment."""
    unique = sorted(set(session_ids))
    if len(unique) != 10:
        raise ValueError("the frozen pilot requires exactly ten sessions")
    ordered = sorted(unique, key=lambda sid: hashlib.sha256(f"{SEED}:{sid}".encode()).hexdigest())
    return ordered[:6], ordered[6:]


def azel_to_enu(azimuth_deg: object, elevation_deg: object) -> np.ndarray:
    azimuth = np.radians(np.asarray(azimuth_deg, dtype=float))
    elevation = np.radians(np.asarray(elevation_deg, dtype=float))
    horizontal = np.cos(elevation)
    return np.stack(
        [horizontal * np.sin(azimuth), horizontal * np.cos(azimuth), np.sin(elevation)],
        axis=-1,
    )


def _normalized_log_weights(probabilities: object) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 1 or len(values) == 0 or np.any(values < 0) or values.sum() <= 0:
        raise ValueError("candidate probabilities must be a nonempty distribution")
    values = np.maximum(values / values.sum(), np.finfo(float).tiny)
    values /= values.sum()
    return np.log(values)


def load_inputs(contract_path: Path) -> tuple[list[PreparedTrack], dict]:
    contract = json.loads(contract_path.read_text())
    root = Path(__file__).resolve().parents[1]
    rows_path = root / contract["conditional_endpoint_rows"]["path"]
    associations_path = root / contract["candidate_temporal_los"]["path"]
    if sha256_path(rows_path) != contract["conditional_endpoint_rows"]["sha256"]:
        raise ValueError("conditional endpoint hash mismatch")
    if sha256_path(associations_path) != contract["candidate_temporal_los"]["sha256"]:
        raise ValueError("association hash mismatch")
    rows = json.loads(rows_path.read_text())
    association_document = json.loads(associations_path.read_text())
    association_rows = {}
    for branch in association_document["branches"]:
        sid = branch["session_id"]
        for row in branch["rows"]:
            key = (sid, row["track_id"], row["projected_observation_id"])
            if key in association_rows:
                raise ValueError("duplicate association join key")
            association_rows[key] = row

    # A physical pair may appear once from each detected anchor. It is one ratio,
    # so retain the lexicographically first anchor before any outcome is modeled.
    matched = [
        row for row in rows if row["matched"] and row["log_margin_ratio_rx1_rx0"] is not None
    ]
    pairs: dict[str, dict] = {}
    for row in sorted(
        matched,
        key=lambda value: (value["receiver_id"] != "rx0", value["anchor_key"]),
    ):
        pairs.setdefault(row["physical_pair_key"], row)
    selected_rows = list(pairs.values())

    grouped: dict[tuple[str, str], list[tuple[dict, dict]]] = defaultdict(list)
    for row in selected_rows:
        key = (row["session_id"], row["track_id"], row["observation_id"])
        if key not in association_rows:
            raise ValueError(f"missing exact association join: {key}")
        association = association_rows[key]
        if association["observation_utc_ns"] != row["observation_utc_ns"]:
            raise ValueError("joined observation UTC mismatch")
        grouped[key[:2]].append((row, association))

    b0, b1 = core.nominal_boresights()
    prepared = []
    rank_counts = Counter()
    for (sid, track_id), members in sorted(grouped.items()):
        members.sort(key=lambda item: item[0]["observation_utc_ns"])
        if len(members) < 3:
            rank_counts["fewer_than_three_rows"] += 1
            continue
        candidate_ids = members[0][1]["candidate_ids"]
        probabilities = members[0][1]["candidate_probabilities"]
        for _, association in members[1:]:
            if association["candidate_ids"] != candidate_ids or not np.allclose(
                association["candidate_probabilities"], probabilities, rtol=0.0, atol=1e-14
            ):
                raise ValueError("candidate identity or training weight changed within track")
        times_ns = np.array([row["observation_utc_ns"] for row, _ in members], dtype=np.int64)
        times = (times_ns - times_ns[0]).astype(float) / 1e9
        azimuth = np.array([association["candidate_azimuth_deg"] for _, association in members]).T
        elevation = np.array(
            [association["candidate_elevation_deg"] for _, association in members]
        ).T
        los = azel_to_enu(azimuth, elevation)
        features = core.trajectory_features(times, los, b0, b1)
        track = core.ConditionalTrack(
            f"{sid}:{track_id}",
            _normalized_log_weights(probabilities),
            times,
            np.array([row["log_margin_ratio_rx1_rx0"] for row, _ in members], dtype=float),
            np.ones(len(members), dtype=bool),
            features,
        )
        core.validate_track(track)
        rank = (
            core.projected_temporal_rank(track, np.ones(len(members), dtype=bool))
            if len(members) >= 4
            else 0
        )
        rank_counts[f"incremental_rank_{rank}"] += 1
        prepared.append(
            PreparedTrack(
                sid,
                track,
                np.array([row["channel"] for row, _ in members]),
                np.array([row["edge"] for row, _ in members]),
                np.array([row["sample_rate_hz"] for row, _ in members]),
                np.log(np.array([row["anchor_margin"] for row, _ in members], dtype=float)),
            )
        )

    sessions = sorted({row["session_id"] for row in rows})
    accounting = {
        "contract_rows": len(rows),
        "matched_anchor_rows": len(matched),
        "unique_matched_physical_pairs": len(selected_rows),
        "duplicate_anchor_rows_removed": len(matched) - len(selected_rows),
        "unmatched_conditional_anchor_rows_excluded": len(rows) - len(matched),
        "modeled_tracks": len(prepared),
        "modeled_rows": sum(len(item.track.times) for item in prepared),
        "rank_accounting": dict(rank_counts),
        "all_sessions": sessions,
        "rows_by_session": dict(Counter(row["session_id"] for row in rows)),
        "modeled_rows_by_session": dict(
            Counter(item.session_id for item in prepared for _ in item.track.times)
        ),
    }
    if sessions != sorted(branch["session_id"] for branch in association_document["branches"]):
        raise ValueError("ten-session coverage mismatch")
    return prepared, accounting


def _arm_theta(arm: str, free: np.ndarray) -> tuple[np.ndarray, bool, tuple[int, ...]]:
    if arm == "geometry_free_iid":
        return np.array([free[0], 0.0, free[1]]), False, ()
    if arm == "static_iid":
        return np.array([free[0], free[1], free[2]]), False, (1,)
    if arm == "geometry_free_ou":
        return np.array([free[0], 0.0, 0.0, free[1], free[2]]), True, ()
    if arm == "static_ou":
        return np.array([free[0], free[1], 0.0, free[2], free[3]]), True, (1,)
    if arm == "temporal_ou":
        return np.asarray(free), True, (1, 2)
    raise ValueError(f"unknown arm: {arm}")


def fit_nuisance(
    training: list[PreparedTrack], evaluation: list[PreparedTrack]
) -> tuple[list[PreparedTrack], list[PreparedTrack], dict]:
    """Fit one shared training-only nuisance regression and freeze its offsets."""
    levels = {
        "channel": sorted({str(value) for item in training for value in item.channel}),
        "edge": sorted({str(value) for item in training for value in item.edge}),
        "sample_rate_hz": sorted(
            {str(value) for item in training for value in item.sample_rate_hz}
        ),
    }
    evaluation_levels = {
        "channel": sorted({str(value) for item in evaluation for value in item.channel}),
        "edge": sorted({str(value) for item in evaluation for value in item.edge}),
        "sample_rate_hz": sorted(
            {str(value) for item in evaluation for value in item.sample_rate_hz}
        ),
    }
    unsupported = {key: sorted(set(evaluation_levels[key]) - set(levels[key])) for key in levels}
    margin_center = float(np.mean(np.concatenate([item.log_anchor_margin for item in training])))

    def design(item: PreparedTrack) -> np.ndarray:
        columns = [np.ones(len(item.track.times))]
        for name, values in (
            ("channel", item.channel),
            ("edge", item.edge),
            ("sample_rate_hz", item.sample_rate_hz),
        ):
            # The first training level is the reference category.
            columns.extend(
                (values.astype(str) == level).astype(float) for level in levels[name][1:]
            )
        columns.append(item.log_anchor_margin - margin_center)
        return np.column_stack(columns)

    matrix = np.vstack([design(item) for item in training])
    response = np.concatenate([item.track.log_rx1_over_rx0 for item in training])
    penalty = np.eye(matrix.shape[1]) * RIDGE
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(matrix.T @ matrix + penalty, matrix.T @ response)

    def residualize(items: list[PreparedTrack]) -> list[PreparedTrack]:
        output = []
        for item in items:
            nuisance_mean = design(item) @ coefficients
            track = core.ConditionalTrack(
                item.track.track_id,
                item.track.log_weights,
                item.track.times,
                item.track.log_rx1_over_rx0,
                item.track.training_mask,
                item.track.features,
                nuisance_mean,
            )
            output.append(
                PreparedTrack(
                    item.session_id,
                    track,
                    item.channel,
                    item.edge,
                    item.sample_rate_hz,
                    item.log_anchor_margin,
                )
            )
        return output

    metadata = {
        "levels": levels,
        "evaluation_levels": evaluation_levels,
        "unsupported_evaluation_levels": unsupported,
        "log_anchor_margin_center": margin_center,
        "coefficients": coefficients.tolist(),
        "ridge_on_slopes": RIDGE,
        "training_rows": len(response),
    }
    return residualize(training), residualize(evaluation), metadata


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def objective(arm: str, free: object, tracks: list[core.ConditionalTrack]) -> float:
    theta, temporal, penalized = _arm_theta(arm, np.asarray(free, dtype=float))
    total = 0.0
    for track in tracks:
        scores = core.selected_component_scores(
            track, theta, np.ones(len(track.times), dtype=bool), temporal=temporal
        )
        total -= _logsumexp(track.log_weights + scores)
    total += RIDGE * sum(float(theta[index]) ** 2 for index in penalized)
    return total


def _starts_and_bounds(
    arm: str, observed: np.ndarray
) -> tuple[list[np.ndarray], list[tuple[float, float]]]:
    center = float(np.median(observed))
    spread = max(float(np.std(observed)), 0.05)
    if arm == "geometry_free_iid":
        base, bounds = [center, math.log(spread)], [(-10, 10), (-6, 4)]
    elif arm == "static_iid":
        base, bounds = [center, 1.0, math.log(spread)], [(-10, 10), (0, 50), (-6, 4)]
    elif arm == "geometry_free_ou":
        base, bounds = [center, 0.0, math.log(spread)], [(-10, 10), (-4, 10), (-6, 4)]
    elif arm == "static_ou":
        base, bounds = [center, 1.0, 0.0, math.log(spread)], [(-10, 10), (0, 50), (-4, 10), (-6, 4)]
    else:
        base, bounds = (
            [center, 1.0, 0.0, 0.0, math.log(spread)],
            [(-10, 10), (0, 50), (-50, 50), (-4, 10), (-6, 4)],
        )
    shifts = (0.0, -0.5, 0.5)
    return [
        np.array(base, dtype=float) + np.array([shift] + [0.0] * (len(base) - 1))
        for shift in shifts
    ], bounds


def fit_arm(arm: str, tracks: list[core.ConditionalTrack]) -> dict:
    from scipy.optimize import minimize

    observed = np.concatenate([track.log_rx1_over_rx0 - track.nuisance_mean for track in tracks])
    starts, bounds = _starts_and_bounds(arm, observed)
    runs = []
    for start in starts:
        result = minimize(
            lambda free: objective(arm, free, tracks),
            start,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": MAXITER, "maxfun": MAXFUN},
        )
        runs.append(result)
    winner = min(runs, key=lambda result: float(result.fun))
    theta, temporal, _ = _arm_theta(arm, winner.x)
    boundary_indices = [
        index
        for index, (value, (low, high)) in enumerate(zip(winner.x, bounds, strict=True))
        if abs(float(value) - low) < 1e-6 or abs(float(value) - high) < 1e-6
    ]
    at_boundary = bool(boundary_indices)
    geometry_slope_zero = (
        arm in {"static_iid", "static_ou", "temporal_ou"} and 1 in boundary_indices
    )
    return {
        "free_parameters": winner.x.tolist(),
        "theta": theta.tolist(),
        "temporal": temporal,
        "training_objective": float(winner.fun),
        "converged": bool(winner.success),
        "at_boundary": at_boundary,
        "boundary_parameter_indices": boundary_indices,
        "geometry_slope_zero": geometry_slope_zero,
        "qualification_interpretation": (
            "no_geometry_signal"
            if geometry_slope_zero
            else "numerical_boundary"
            if at_boundary
            else "interior"
        ),
        "starts": [
            {"objective": float(run.fun), "success": bool(run.success), "nfev": int(run.nfev)}
            for run in runs
        ],
    }


def score_tracks(tracks: list[PreparedTrack], fit: dict, control: str | None = None) -> dict:
    theta = np.asarray(fit["theta"], dtype=float)
    temporal = bool(fit["temporal"])
    per_session = Counter()
    rows = Counter()
    for item in tracks:
        track = item.track
        if control == "geometry_swap":
            track = core.receiver_swap(track)
        elif control == "time_shuffle":
            track = core.deterministic_time_shuffle(track, SEED)
        elif control == "trajectory_reversal":
            track = core.reverse_candidate_trajectory(track)
        selected = np.ones(len(track.times), dtype=bool)
        scores = core.selected_component_scores(track, theta, selected, temporal=temporal)
        per_session[item.session_id] += _logsumexp(track.log_weights + scores)
        rows[item.session_id] += len(track.times)
    return {
        "total_log_density": float(sum(per_session.values())),
        "rows": int(sum(rows.values())),
        "per_session": {
            sid: {
                "log_density": float(per_session[sid]),
                "rows": rows[sid],
                "mean": float(per_session[sid] / rows[sid]),
            }
            for sid in sorted(rows)
        },
    }


def _write_progress(path: Path | None, result: dict) -> None:
    if path is None:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _rank_label(item: PreparedTrack) -> str:
    rank = 0
    if len(item.track.times) >= 4:
        selected = np.ones(len(item.track.times), dtype=bool)
        rank = core.projected_temporal_rank(item.track, selected)
    return f"incremental_rank_{rank}"


def _crossing_support(items: list[PreparedTrack]) -> dict:
    any_finite = sum(np.any(np.isfinite(item.track.features.crossing_time)) for item in items)
    all_finite = sum(np.all(np.isfinite(item.track.features.crossing_time)) for item in items)
    return {
        "tracks": len(items),
        "tracks_with_any_candidate_nominal_contrast_zero": int(any_finite),
        "tracks_with_all_candidates_nominal_contrast_zero": int(all_finite),
    }


def run(contract_path: Path, progress_path: Path | None = None) -> dict:
    started = time.monotonic()
    prepared, accounting = load_inputs(contract_path)
    train_ids, eval_ids = frozen_split(accounting["all_sessions"])
    train_items = [item for item in prepared if item.session_id in train_ids]
    eval_items = [item for item in prepared if item.session_id in eval_ids]
    train_items, eval_items, nuisance = fit_nuisance(train_items, eval_items)
    scale = core.fit_feature_scale([item.track for item in train_items])
    train = [core.apply_feature_scale(item.track, scale) for item in train_items]
    evaluation = [
        PreparedTrack(
            item.session_id,
            core.apply_feature_scale(item.track, scale),
            item.channel,
            item.edge,
            item.sample_rate_hz,
            item.log_anchor_margin,
        )
        for item in eval_items
    ]
    result = {
        "schema": "ds7-conditional-beam-crossing-evaluation/v1",
        "status": "running",
        "contract_path": str(contract_path),
        "contract_sha256": sha256_path(contract_path),
        "seed": SEED,
        "ridge": RIDGE,
        "optimizer_limits": {"maxiter_per_start": MAXITER, "maxfun_per_start": MAXFUN},
        "split": {"train": train_ids, "evaluation": eval_ids},
        "feature_scale": asdict(scale),
        "frozen_training_nuisance": nuisance,
        "accounting": accounting,
        "rank_support": {
            partition: dict(Counter(_rank_label(item) for item in items))
            for partition, items in (("train", train_items), ("evaluation", eval_items))
        },
        "nominal_contrast_zero_support": {
            "train": _crossing_support(train_items),
            "evaluation": _crossing_support(eval_items),
        },
        "fits": {},
        "held_scores": {},
        "held_only_controls": {},
    }
    _write_progress(progress_path, result)
    fits = result["fits"]
    for arm in ARMS:
        fits[arm] = fit_arm(arm, train)
        result["held_scores"][arm] = score_tracks(evaluation, fits[arm])
        if arm in {"static_ou", "temporal_ou"}:
            result["held_only_controls"][arm] = {
                control: score_tracks(evaluation, fits[arm], control)
                for control in ("geometry_swap", "time_shuffle", "trajectory_reversal")
            }
        result["last_completed_arm"] = arm
        result["elapsed_seconds"] = time.monotonic() - started
        _write_progress(progress_path, result)
    scores = result["held_scores"]
    controls = result["held_only_controls"]
    static = scores["static_ou"]
    temporal = scores["temporal_ou"]
    deltas = {
        sid: temporal["per_session"][sid]["log_density"] - static["per_session"][sid]["log_density"]
        for sid in eval_ids
    }
    primary_gate = {
        "aggregate_temporal_minus_static_ou": (
            temporal["total_log_density"] - static["total_log_density"]
        ),
        "evaluation_recordings_improved": sum(value > 0 for value in deltas.values()),
        "evaluation_recordings_total": len(deltas),
        "per_recording_delta": deltas,
        "beats_each_frozen_temporal_control": all(
            temporal["total_log_density"] > value["total_log_density"]
            for value in controls["temporal_ou"].values()
        ),
    }
    unsupported = nuisance["unsupported_evaluation_levels"]
    qualified = (
        all(fit["converged"] and not fit["at_boundary"] for fit in fits.values())
        and accounting["rank_accounting"].get("incremental_rank_1", 0) > 0
        and all(
            accounting["modeled_rows_by_session"].get(sid, 0) > 0
            for sid in accounting["all_sessions"]
        )
        and not any(unsupported.values())
        and primary_gate["aggregate_temporal_minus_static_ou"] > 0
        and primary_gate["evaluation_recordings_improved"] >= 3
        and primary_gate["beats_each_frozen_temporal_control"]
    )
    result.update(
        {
            "status": "qualified_exploratory" if qualified else "unqualified_exploratory",
            "interpretation": (
                "conditional reused-preprocessing feasibility; "
                "not a clean fresh pipeline validation"
            ),
            "comparator_note": (
                "static_iid is candidate-specific nominal geometry; the legacy posterior-mean "
                "rowwise model is not reproduced"
            ),
            "preprocessing_exposure": ["scan-fw-aa9770c66396e928", "scan-fw-9d7b6a0db558703a"],
            "primary_exploratory_gate": primary_gate,
            "elapsed_seconds": time.monotonic() - started,
            "claims_excluded": [
                "unconditional detection",
                "held frequency prediction",
                "position improvement",
                "physical beam calibration",
            ],
        }
    )
    _write_progress(progress_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.contract, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
