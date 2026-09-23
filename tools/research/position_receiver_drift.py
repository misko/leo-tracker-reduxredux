#!/usr/bin/env python3
"""Exact-RX receiver drift experiment with shared bracket timing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

RIDGES = (0.0, 100.0, 1000.0, 10000.0)
SAMPLE_COUNT = 12


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def cache_index(grouped, replication_root: Path, original_cache: Path):
    caches, scans, cache_digests = grouped.cache_sources(replication_root, original_cache)
    return caches, scans, cache_digests


def reconstruct_mapping(session_id: str, evidence: dict, store) -> dict:
    """Reconstruct exact public-contract observation-to-RX identities."""
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        persistent_hop_tracklet_graph,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates

    source = store.load(session_id)
    config = PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    candidates = project_scanner_candidates(source)
    trajectory = reconstruct_persistent_hop_trajectories(candidates, config=config)
    records = {}
    for hypothesis in trajectory.hypotheses:
        for track_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, track_id)
            for observation in graph.observations:
                value = (observation.stream_id, observation.receiver_path_id)
                previous = records.get(observation.observation_id)
                if previous is not None and previous != value:
                    raise ValueError(f"conflicting RX identity in {session_id}")
                records[observation.observation_id] = value
    wanted = [oid for track in evidence["tracks"] for oid in track["observation_ids"]]
    missing = set(wanted) - records.keys()
    if missing:
        raise ValueError(f"{session_id} misses {len(missing)} cached observations")
    return {
        "session_id": session_id,
        "input_manifest_sha256": source.input_manifest_sha256,
        "analysis_manifest_sha256": source.analysis_manifest_sha256,
        "trajectory_config_digest": config.digest,
        "cached_observation_count": len(wanted),
        "matched_count": len(set(wanted)),
        "receiver_counts": dict(Counter("|".join(records[oid]) for oid in wanted)),
        "mapping": {oid: list(records[oid]) for oid in sorted(set(wanted))},
    }


def export_mappings(args) -> None:
    if args.output.exists():
        raise FileExistsError(args.output)
    split = json.loads(args.split.read_text())
    grouped = load_module(args.grouped_tool, "receiver_drift_grouped_export")
    caches, _, cache_digests = cache_index(grouped, args.replication_root, args.original_cache)
    if args.partition == "train12":
        sessions = split["partitions"]["train"]["session_ids"][:SAMPLE_COUNT]
    elif args.partition == "validation":
        sessions = split["partitions"]["validation"]["session_ids"]
    else:
        raise ValueError("only train12 or validation mapping export is allowed")
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    rows = []
    store = ScannerTrackingInputStore(args.bulk_root)
    try:
        for session_id in sessions:
            evidence = json.loads(
                (caches[session_id] / "evidence" / f"{session_id}.json").read_text()
            )
            rows.append(reconstruct_mapping(session_id, evidence, store))
    finally:
        store.close()
    payload = {
        "schema": "exact-receiver-mapping/v1",
        "partition": args.partition,
        "split_sha256": digest(args.split),
        "cache_manifest_sha256": cache_digests,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def receiver_vector(track: dict, mapping: dict) -> np.ndarray:
    values = []
    for oid in track["observation_ids"]:
        if oid not in mapping:
            raise ValueError(f"missing exact receiver mapping for {oid}")
        values.append(mapping[oid][0])
    return np.asarray(values)


def _solve_coefficients(residuals, times, masks, receivers, ridge):
    track_count = len(residuals)
    rx_names = sorted({str(rx) for values in receivers for rx in values})
    rx_index = {value: index for index, value in enumerate(rx_names)}
    rows, values = [], []
    for track_index, (residual, time_s, mask, rx_values) in enumerate(
        zip(residuals, times, masks, receivers, strict=True)
    ):
        centered = time_s - np.mean(time_s[mask])
        for value, elapsed, rx in zip(residual[mask], centered[mask], rx_values[mask], strict=True):
            design = np.zeros(track_count + len(rx_names))
            design[track_index] = 1.0
            design[track_count + rx_index[str(rx)]] = elapsed
            rows.append(design)
            values.append(value)
    design = np.asarray(rows)
    if ridge:
        penalty = np.zeros((len(rx_names), track_count + len(rx_names)))
        penalty[:, track_count:] = np.sqrt(ridge) * np.eye(len(rx_names))
        design = np.vstack((design, penalty))
        values.extend([0.0] * len(rx_names))
    coefficients = np.linalg.lstsq(design, np.asarray(values), rcond=None)[0]
    return coefficients[:track_count], dict(zip(rx_names, coefficients[track_count:], strict=True))


def fit_receiver_slopes(
    predictions, receiver_ids, tau_index: int, ridge: float | None, include_evaluation=False
):
    """Alternate exact candidate assignment with one penalized slope per RX."""
    masks = [np.asarray(row.training_mask, dtype=bool) for row in predictions]
    times = [np.asarray(row.times_s, dtype=float) for row in predictions]
    measured = [np.asarray(row.measured_hz, dtype=float) for row in predictions]
    choices = []
    for row, mask, values in zip(predictions, masks, measured, strict=True):
        residual = values[None, :] - row.predictions_hz[:, tau_index, :]
        centered = residual[:, mask] - np.mean(residual[:, mask], axis=1)[:, None]
        mse = np.mean(centered**2, axis=1)
        visible = np.asarray(row.visible)
        if visible.ndim == 2:
            visible = visible[:, tau_index]
        mse = np.where(visible, mse, np.inf)
        if not np.any(np.isfinite(mse)):
            raise ValueError("all candidates are invisible")
        choices.append(int(np.argmin(mse)))
    slopes = {str(rx): 0.0 for values in receiver_ids for rx in values}
    for _ in range(12):
        residuals = [
            values - row.predictions_hz[choice, tau_index]
            for row, values, choice in zip(predictions, measured, choices, strict=True)
        ]
        if ridge is None:
            intercepts = np.asarray(
                [np.mean(residual[mask]) for residual, mask in zip(residuals, masks, strict=True)]
            )
        else:
            intercepts, slopes = _solve_coefficients(residuals, times, masks, receiver_ids, ridge)
        updated = []
        for row, values, time_s, mask, rx_values in zip(
            predictions, measured, times, masks, receiver_ids, strict=True
        ):
            elapsed = time_s - np.mean(time_s[mask])
            correction = np.asarray([slopes[str(rx)] for rx in rx_values]) * elapsed
            residual = values[None, :] - row.predictions_hz[:, tau_index, :] - correction
            offset = np.mean(residual[:, mask], axis=1)
            mse = np.mean((residual[:, mask] - offset[:, None]) ** 2, axis=1)
            visible = np.asarray(row.visible)
            if visible.ndim == 2:
                visible = visible[:, tau_index]
            mse = np.where(visible, mse, np.inf)
            if not np.any(np.isfinite(mse)):
                raise ValueError("all candidates are invisible")
            updated.append(int(np.argmin(mse)))
        if updated == choices:
            break
        choices = updated
    residuals = [
        values - row.predictions_hz[choice, tau_index]
        for row, values, choice in zip(predictions, measured, choices, strict=True)
    ]
    if ridge is None:
        intercepts = np.asarray(
            [np.mean(residual[mask]) for residual, mask in zip(residuals, masks, strict=True)]
        )
    else:
        intercepts, slopes = _solve_coefficients(residuals, times, masks, receiver_ids, ridge)
    train_sse = reserved_sse = train_count = reserved_count = 0
    tracks = []
    for row, residual, time_s, mask, rx_values, choice, intercept in zip(
        predictions, residuals, times, masks, receiver_ids, choices, intercepts, strict=True
    ):
        elapsed = time_s - np.mean(time_s[mask])
        fitted = intercept + np.asarray([slopes[str(rx)] for rx in rx_values]) * elapsed
        error = residual - fitted
        train_sse += float(np.sum(error[mask] ** 2))
        if include_evaluation:
            reserved_sse += float(np.sum(error[~mask] ** 2))
        train_count += int(np.sum(mask))
        reserved_count += int(np.sum(~mask)) if include_evaluation else 0
        tracks.append({
            "candidate_id": str(row.candidate_ids[choice]),
            "offset_hz": float(intercept),
            "training_rms_hz": float(np.sqrt(np.mean(error[mask] ** 2))),
            "evaluation_rms_hz": (
                float(np.sqrt(np.mean(error[~mask] ** 2))) if include_evaluation else None
            ),
            "weight_s": int(len(np.unique(np.floor(time_s)))),
        })
    total_weight = sum(row["weight_s"] for row in tracks)
    capped_loss = sum(
        row["weight_s"] * min(800.0, row["training_rms_hz"]) ** 2 for row in tracks
    )
    penalty = 0.0 if ridge is None else ridge * sum(value * value for value in slopes.values())
    return {
        "objective": float(np.sqrt((capped_loss + penalty) / total_weight)),
        "training_rms_hz": float(np.sqrt(train_sse / train_count)),
        "reserved_rms_hz": (
            float(np.sqrt(reserved_sse / reserved_count)) if reserved_count else None
        ),
        "reserved_sse_hz2": reserved_sse,
        "reserved_count": reserved_count,
        "penalty_hz2_s": float(penalty),
        "slopes_hz_per_s": {key: float(value) for key, value in slopes.items()},
        "tracks": tracks,
    }


def fit_scan(
    joint, evidence, arrays, point, timing_grid, mapping, ridge, include_evaluation=False
):
    predictions = [
        joint.prediction_for_track(
            evidence, arrays, track, float(point[0]), float(point[1]), taus_s=timing_grid
        )
        for track in evidence["tracks"]
    ]
    identities = [receiver_vector(track, mapping) for track in evidence["tracks"]]
    candidates = [
        fit_receiver_slopes(predictions, identities, index, ridge, include_evaluation)
        for index in range(len(timing_grid))
    ]
    selected_index = min(range(len(candidates)), key=lambda index: candidates[index]["objective"])
    return {
        "tau_s": float(timing_grid[selected_index]),
        "tau_index": selected_index,
        "grid_size": len(timing_grid),
        "boundary_hit": selected_index in (0, len(timing_grid) - 1),
        **candidates[selected_index],
    }


def timing_grids(timing_path: Path, sessions) -> dict:
    timing = json.loads(timing_path.read_text())
    rows = {row["session_id"]: row["timing"] for row in timing["rows"]}
    if set(rows) != set(sessions):
        raise ValueError("timing metadata must exactly cover requested sessions")
    result = {}
    for session, row in rows.items():
        if not row["qualified"]:
            raise ValueError(f"unqualified timing authority {session}")
        low = (row["first_sample_earliest_utc_ns"] - row["first_sample_estimate_utc_ns"]) / 1e9
        high = (row["first_sample_latest_utc_ns"] - row["first_sample_estimate_utc_ns"]) / 1e9
        result[session] = np.linspace(low, high, 17)
    return result


def load_mapping(path: Path, expected_sessions) -> dict:
    payload = json.loads(path.read_text())
    rows = {row["session_id"]: row for row in payload["rows"]}
    if set(rows) != set(expected_sessions):
        raise ValueError("receiver mapping must exactly cover requested sessions")
    return {session: row["mapping"] for session, row in rows.items()}


def training_select(args) -> None:
    if args.output.exists():
        raise FileExistsError(args.output)
    split = json.loads(args.split.read_text())
    sessions = split["partitions"]["train"]["session_ids"][:SAMPLE_COUNT]
    grouped = load_module(args.grouped_tool, "receiver_drift_grouped_train")
    joint = load_module(args.joint_tool, "receiver_drift_joint_train")
    caches, scans, cache_digests = cache_index(grouped, args.replication_root, args.original_cache)
    grids = timing_grids(args.timing_metadata, sessions)
    mappings = load_mapping(args.mapping, sessions)
    rows = []
    started = time.monotonic()
    for session in sessions:
        evidence, arrays = joint.load_scan_cache(caches[session], session)
        published = scans[session]
        _, source = min(
            published["priors"].items(),
            key=lambda item: item[1]["selected"]["capped_weighted_rmse_hz"],
        )
        point = source["selected"]
        fits = []
        for ridge in RIDGES:
            fit = fit_scan(
                joint, evidence, arrays,
                (point["latitude_deg"], point["longitude_deg"]),
                grids[session], mappings[session], ridge, True,
            )
            fits.append({"ridge_s2": ridge, **fit})
        rows.append({"session_id": session, "fits": fits})
    scores = []
    for ridge in RIDGES:
        selected = [next(fit for fit in row["fits"] if fit["ridge_s2"] == ridge) for row in rows]
        count = sum(fit["reserved_count"] for fit in selected)
        sse = sum(fit["reserved_sse_hz2"] for fit in selected)
        scores.append({"ridge_s2": ridge, "reserved_rms_hz": float(np.sqrt(sse / count))})
    winner = min(scores, key=lambda row: (row["reserved_rms_hz"], -row["ridge_s2"]))
    result = {
        "schema": "receiver-drift-training-selection/v1",
        "scope": "first 12 frozen TRAIN sessions; training-only inner validation",
        "position_truth_used": False,
        "validation_evidence_accessed": False,
        "test_evidence_accessed": False,
        "ridge_candidates_s2": RIDGES,
        "scores": scores,
        "selected_ridge_s2": winner["ridge_s2"],
        "rows": rows,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "split": digest(args.split), "timing": digest(args.timing_metadata),
            "mapping": digest(args.mapping), "tool": digest(Path(__file__)),
            "cache_manifest_sha256": cache_digests,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload)
    args.output.with_suffix(".sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )


def score_window(
    grouped, joint, prepared, sessions, point, grids, mappings, ridge,
    include_evaluation=False,
):
    scans, rows = [], []
    for session in sessions:
        evidence, arrays = prepared[session]
        fit = fit_scan(
            joint, evidence, arrays, point, grids[session], mappings[session], ridge,
            include_evaluation,
        )
        scans.append({key: value for key, value in fit.items() if key != "tracks"})
        rows.extend(
            {"session_id": session, "weight_s": track["weight_s"], "score": track}
            for track in fit["tracks"]
        )
    total_weight = sum(row["weight_s"] for row in rows)
    capped = sum(
        row["weight_s"] * min(800.0, row["score"]["training_rms_hz"]) ** 2
        for row in rows
    )
    penalty = sum(scan["penalty_hz2_s"] for scan in scans)
    objective = float(np.sqrt((capped + penalty) / total_weight))
    return objective, scans, rows


def validation_run(args) -> None:
    if (args.output / "inference.json").exists():
        raise FileExistsError(args.output / "inference.json")
    split = json.loads(args.split.read_text())
    validation = split["partitions"]["validation"]
    sessions = validation["session_ids"]
    training = json.loads(args.training_selection.read_text())
    ridge = float(training["selected_ridge_s2"])
    prior = load_module(args.prior_tool, "receiver_drift_prior_validation")
    grouped = load_module(args.grouped_tool, "receiver_drift_grouped_validation")
    joint = load_module(args.joint_tool, "receiver_drift_joint_validation")
    caches, scans, cache_digests = cache_index(grouped, args.replication_root, args.original_cache)
    grids = timing_grids(args.timing_metadata, sessions)
    mappings = load_mapping(args.mapping, sessions)
    authority = {row["session_id"]: row for row in json.loads(args.inventory.read_text())["scans"]}
    for session in sessions:
        evidence = json.loads((caches[session] / "evidence" / f"{session}.json").read_text())
        evidence_digest = prior.value_digest(evidence["tracks"]).removeprefix("sha256:")
        if evidence_digest != authority[session]["evidence_digest"]:
            raise ValueError("cached evidence differs from inventory")
    groups = [group for group in split["groups"] if group["group_id"] in validation["group_ids"]]
    windows = []
    for group in groups:
        windows.extend((
            {"window_id": group["group_id"], "session_ids": group["session_ids"]},
            {
                "window_id": group["group_id"] + "-first-scan",
                "session_ids": group["session_ids"][:1],
            },
        ))
    arms = (("zero_drift_capped800", None), ("receiver_drift_capped800", ridge))
    started = time.monotonic()
    output_windows = []
    for window in windows:
        active = window["session_ids"]
        prepared = {sid: joint.load_scan_cache(caches[sid], sid) for sid in active}
        seeds = prior.deterministic_seeds(prior.published_seed_rows(active, scans, authority))
        arm_rows = []
        for name, selected_ridge in arms:
            fits = []
            for seed_index, seed in enumerate(seeds, start=1):
                fit = prior.bounded_fit(
                    lambda point, value=selected_ridge, data=prepared, ids=active: score_window(
                        grouped, joint, data, ids, point, grids, mappings, value
                    )[0],
                    seed,
                    max_evaluations=args.max_evaluations,
                )
                fits.append({"seed_id": seed_index, "seed": seed, **fit})
            arm_rows.append({
                "method": name,
                "ridge_s2": selected_ridge,
                "fits": fits,
                "selected": min(fits, key=lambda row: row["training_rmse_hz"]),
            })
        output_windows.append({**window, "seeds": seeds, "arms": arm_rows})
    inference = {
        "schema": "receiver-drift-position/v1",
        "position_truth_used": False,
        "test_evidence_accessed": False,
        "selected_ridge_s2": ridge,
        "windows": output_windows,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "split": digest(args.split), "inventory": digest(args.inventory),
            "timing": digest(args.timing_metadata), "mapping": digest(args.mapping),
            "training_selection": digest(args.training_selection), "tool": digest(Path(__file__)),
            "cache_manifest_sha256": cache_digests,
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    for window in results["windows"]:
        active = window["session_ids"]
        prepared = {sid: joint.load_scan_cache(caches[sid], sid) for sid in active}
        for arm in window["arms"]:
            selected = arm["selected"]
            point = (selected["latitude_deg"], selected["longitude_deg"])
            _, scan_rows, tracks = score_window(
                grouped, joint, prepared, active, point, grids, mappings, arm["ridge_s2"], True
            )
            selected["scans"] = scan_rows
            selected["reserved_capped800_rmse_hz"] = grouped.aggregate(
                tracks, "evaluation_rms_hz", "capped800", "duration"
            )
            selected["reserved_uncapped_rmse_hz"] = grouped.aggregate(
                tracks, "evaluation_rms_hz", "uncapped", "duration"
            )
            selected["reference_error_km"] = prior.haversine_km(point, prior.REFERENCE)
    results["reference_coordinate"] = {
        "latitude_deg": prior.REFERENCE[0], "longitude_deg": prior.REFERENCE[1],
        "role": "post-seal only",
    }
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def common_parser(parser):
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--grouped-tool", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--original-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export-mappings")
    common_parser(export)
    export.add_argument("--partition", choices=("train12", "validation"), required=True)
    export.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    export.set_defaults(handler=export_mappings)
    train = sub.add_parser("train")
    common_parser(train)
    train.add_argument("--joint-tool", type=Path, required=True)
    train.add_argument("--timing-metadata", type=Path, required=True)
    train.add_argument("--mapping", type=Path, required=True)
    train.set_defaults(handler=training_select)
    validate = sub.add_parser("validate")
    common_parser(validate)
    validate.add_argument("--joint-tool", type=Path, required=True)
    validate.add_argument("--prior-tool", type=Path, required=True)
    validate.add_argument("--inventory", type=Path, required=True)
    validate.add_argument("--timing-metadata", type=Path, required=True)
    validate.add_argument("--mapping", type=Path, required=True)
    validate.add_argument("--training-selection", type=Path, required=True)
    validate.add_argument("--max-evaluations", type=int, default=150)
    validate.set_defaults(handler=validation_run)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
