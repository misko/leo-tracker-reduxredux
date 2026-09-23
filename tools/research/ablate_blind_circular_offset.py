#!/usr/bin/env python3
"""Conditional whole-track predictive ablation of a circular CFO intercept."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    Region,
    ScoreConfig,
    logsumexp,
)
from leo.sky.propagation import parse_element_sets

PILOT_ALIAS_HZ = 1.0 / 4.4e-6
CANONICAL_RF_HZ = 11_200_000_000.0
SIGMA_ARMS_HZ = (3_000.0, 10_000.0, 30_000.0)
OUTLIER_ARMS = (0.05, 0.2)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"{name} has no loader")
    spec.loader.exec_module(module)
    return module


def fold_number(session_id: str, episode_id: str, folds: int = 5) -> int:
    if folds < 2:
        raise ValueError("at least two folds required")
    value = hashlib.sha256(f"{session_id}|{episode_id}".encode()).hexdigest()
    return int(value[:16], 16) % folds


def wrap_alias_hz(value):
    values = np.asarray(value, dtype=float)
    wrapped = (values + PILOT_ALIAS_HZ / 2) % PILOT_ALIAS_HZ - PILOT_ALIAS_HZ / 2
    return float(wrapped) if wrapped.ndim == 0 else wrapped


def circular_factor(offset_hz, grid_hz, sigma_hz, outlier_probability):
    """Dimensionless P*((1-epsilon)*wrapped_normal + epsilon/P)."""
    if sigma_hz <= 0 or not 0 <= outlier_probability < 1:
        raise ValueError("invalid circular-factor controls")
    # Center the finite image stencil. This also makes the public helper invariant
    # to callers supplying an equivalent offset outside the principal interval.
    residual = wrap_alias_hz(np.asarray(offset_hz)[..., None] - np.asarray(grid_hz))
    image_count = int(np.ceil(8 * sigma_hz / PILOT_ALIAS_HZ)) + 1
    kernel = np.zeros_like(residual, dtype=float)
    for image in range(-image_count, image_count + 1):
        kernel += np.exp(-0.5 * ((residual + image * PILOT_ALIAS_HZ) / sigma_hz) ** 2)
    wrapped_normal_times_period = PILOT_ALIAS_HZ / (np.sqrt(2 * np.pi) * sigma_hz) * kernel
    return (1 - outlier_probability) * wrapped_normal_times_period + outlier_probability


def predictive_delta(log_likelihood, training, evaluation):
    """One heldout track score under training posterior versus uniform circle."""
    likelihood = np.asarray(log_likelihood, dtype=float)
    train = np.asarray(training, dtype=bool)
    evaluate = np.asarray(evaluation, dtype=bool)
    if likelihood.ndim != 2 or likelihood.shape[0] != len(train) or len(train) != len(evaluate):
        raise ValueError("likelihood and masks are misaligned")
    if np.any(train & evaluate) or not np.any(train) or np.sum(evaluate) != 1:
        raise ValueError("one disjoint evaluation track required")
    posterior_log_mass = np.sum(likelihood[train], axis=0)
    posterior_log_mass -= logsumexp(posterior_log_mass)
    row = likelihood[evaluate][0]
    predictive = logsumexp(row + posterior_log_mass)
    uniform = logsumexp(row) - np.log(len(row))
    return float(predictive - uniform)


def track_log_likelihood(candidate_log_shape, null_log_shape, offset_hz, grid_hz, sigma, outlier):
    factor = circular_factor(offset_hz, grid_hz, sigma, outlier)
    signal = logsumexp(np.asarray(candidate_log_shape)[:, None] + np.log(factor), axis=0)
    return np.logaddexp(signal, null_log_shape)


def run(args) -> None:
    if args.output.exists():
        raise ValueError("fresh output required")
    refinement = json.loads(args.refinement.read_text())
    checksum = args.refinement.with_name("result.sha256")
    if (
        checksum.read_text().strip() != hashlib.sha256(args.refinement.read_bytes()).hexdigest()
        or refinement.get("position_truth_used") is not False
        or not refinement.get("complete")
    ):
        raise ValueError("sealed truth-free refinement required")
    acquisition_path = Path(refinement["run"]) / "result.json"
    if digest(acquisition_path) != refinement["source_result_digest"]:
        raise ValueError("acquisition binding mismatch")
    acquisition = json.loads(acquisition_path.read_text())
    config = ScoreConfig(**acquisition["score"])
    region = Region(**refinement["region"])
    receiver = region.points(
        [refinement["selected"]["east_km"]], [refinement["selected"]["north_km"]]
    )
    lane_by_track = {}
    rf_digests = {}
    for path in sorted(args.rf_shards.glob("scan-*.json")):
        shard = json.loads(path.read_text())
        rf_digests[str(path)] = digest(path)
        for track in shard["tracks"]:
            key = (shard["session"]["session_id"], track["tracklet_id"])
            if key in lane_by_track:
                raise ValueError("duplicate RF lane authority")
            lane_by_track[key] = track["lane"]
    replay_path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    replay = load_module(replay_path, "circular_offset_replay")
    tracks = []
    support = []
    for session_id in refinement["sessions"]:
        evidence_path = args.evidence / "evidence" / f"{session_id}.json"
        document = json.loads(evidence_path.read_text())
        provenance = refinement["provenance"][session_id]
        if digest(evidence_path) != provenance["rf_digest"]:
            raise ValueError("RF evidence binding mismatch")
        metadata = document["inventory"]
        if metadata["tle_collected_ns"] >= metadata["reference_utc_ns"] - 5_000_000_000:
            raise ValueError("TLE snapshot violates the five-second causal guard")
        tle_path = evidence_path.parent / metadata["tle_file"]
        if Path(metadata["tle_file"]).name != metadata["tle_file"]:
            raise ValueError("unsafe TLE basename")
        if (
            digest(tle_path) != metadata["tle_digest"]
            or digest(tle_path) != provenance["tle_digest"]
        ):
            raise ValueError("TLE binding mismatch")
        catalogue = parse_element_sets(tle_path.read_text())
        indices, population = replay.regional_catalogue(
            catalogue, metadata["reference_utc_ns"], region
        )
        series_by_track = {row["tracklet_id"]: row for row in document["series"]}
        if len(series_by_track) != len(document["series"]):
            raise ValueError("duplicate evidence series track")
        for episode_id, arc in replay.load_observations(document, max_per_partition=0):
            episode = next(row for row in document["episodes"] if row["episode_id"] == episode_id)
            if len(episode["members"]) != 1:
                raise ValueError("ablation requires one RF track per episode")
            lane = lane_by_track[(session_id, episode["members"][0])]
            series = series_by_track[episode["members"][0]]
            if (
                int(lane["receiver_id"]) != int(series["receiver_id"])
                or int(lane["channel"]) != int(series["channel"])
                or float(lane["actual_rf_hz"]) != float(series["actual_rf_hz"])
                or float(lane["canonical_rf_hz"]) != CANONICAL_RF_HZ
                or int(episode["channel"]) != int(series["channel"])
            ):
                raise ValueError("RF lane metadata differs from evidence series")
            p, v, retained = replay.state_arrays(
                catalogue, indices, metadata["reference_utc_ns"], arc.time_s
            )
            norads = np.asarray(catalogue.satellite_numbers)[retained]
            support_digest = (
                "sha256:" + hashlib.sha256(np.sort(norads).astype("<i8").tobytes()).hexdigest()
            )
            baseline = next(
                item for item in provenance["evaluated_support"] if item["episode_id"] == episode_id
            )
            if support_digest != baseline["evaluated_norad_digest"]:
                raise ValueError("candidate support differs from frozen refinement")
            delta = p - receiver.ecef_km[0]
            distance = np.linalg.norm(delta, axis=-1)
            prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=-1) / distance
            elevation = np.sum(delta * receiver.up[0], axis=-1) / distance
            visible = np.min(elevation, axis=-1) >= np.sin(np.deg2rad(config.minimum_elevation_deg))
            observed = np.asarray(arc.frequency_hz)
            residual = observed[None, :] - prediction
            means = np.mean(residual, axis=1)
            mse = np.mean((residual - means[:, None]) ** 2, axis=1)
            null_mse = float(np.mean((observed - np.mean(observed)) ** 2))
            n = config.effective_count
            candidate_log_shape = (
                -0.5 * n * mse / config.signal_sigma_hz**2
                - n * np.log(config.signal_sigma_hz)
                + np.log(config.signal_prior / population)
            )
            candidate_log_shape = np.where(visible, candidate_log_shape, -np.inf)
            null_log_shape = (
                -0.5 * n * null_mse / config.null_sigma_hz**2
                - n * np.log(config.null_sigma_hz)
                + np.log1p(-config.signal_prior)
            )
            native_mean = means * lane["actual_rf_hz"] / CANONICAL_RF_HZ
            tracks.append(
                {
                    "session_id": session_id,
                    "episode_id": episode_id,
                    "receiver_id": lane["receiver_id"],
                    "pilot_edge": lane["edge"],
                    "channel": lane["channel"],
                    "fold": fold_number(session_id, episode_id),
                    "candidate_log_shape": candidate_log_shape,
                    "null_log_shape": null_log_shape,
                    "offset_hz": wrap_alias_hz(native_mean),
                }
            )
            support.append(
                {
                    "session_id": session_id,
                    "episode_id": episode_id,
                    "full_catalogue_size": population,
                    "candidate_count": len(norads),
                    "candidate_digest": support_digest,
                    "regional_prefilter_exclusion_count": population - len(indices),
                    "propagation_or_radius_exclusion_count": len(indices) - len(norads),
                }
            )
    if len(tracks) != 165:
        raise ValueError("expected all 165 RF tracks")
    grid = np.linspace(-PILOT_ALIAS_HZ / 2, PILOT_ALIAS_HZ / 2, args.grid_size, endpoint=False)
    groups = defaultdict(list)
    for index, track in enumerate(tracks):
        groups[(track["receiver_id"], track["pilot_edge"])].append(index)
    arms = []
    for sigma in SIGMA_ARMS_HZ:
        for outlier in OUTLIER_ARMS:
            rows = []
            for group, indexes in sorted(groups.items()):
                likelihood = np.asarray(
                    [
                        track_log_likelihood(
                            tracks[i]["candidate_log_shape"],
                            tracks[i]["null_log_shape"],
                            tracks[i]["offset_hz"],
                            grid,
                            sigma,
                            outlier,
                        )
                        for i in indexes
                    ]
                )
                for local, index in enumerate(indexes):
                    fold = tracks[index]["fold"]
                    training = np.asarray(
                        [tracks[other]["fold"] != fold for other in indexes], dtype=bool
                    )
                    evaluation = np.arange(len(indexes)) == local
                    rows.append(
                        {
                            "session_id": tracks[index]["session_id"],
                            "episode_id": tracks[index]["episode_id"],
                            "receiver_id": group[0],
                            "pilot_edge": group[1],
                            "fold": fold,
                            "training_track_count": int(np.sum(training)),
                            "delta_log_score": predictive_delta(likelihood, training, evaluation),
                        }
                    )
            arms.append(
                {
                    "sigma_hz": sigma,
                    "outlier_probability": outlier,
                    "track_count": len(rows),
                    "total_delta_log_score": float(sum(row["delta_log_score"] for row in rows)),
                    "median_delta_log_score": float(
                        np.median([row["delta_log_score"] for row in rows])
                    ),
                    "positive_track_count": sum(row["delta_log_score"] > 0 for row in rows),
                    "tracks": rows,
                }
            )
    output = {
        "schema": "blind-circular-offset-conditional-ablation/v1",
        "truth_accessed": False,
        "conditional_on_all_track_shape_fitted_position": True,
        "position_or_identity_validation": False,
        "track_count": len(tracks),
        "fold_rule": "sha256(session_id+'|'+episode_id) first 64 bits modulo 5",
        "grid_size": args.grid_size,
        "alias_spacing_hz": PILOT_ALIAS_HZ,
        "arms_are_exploratory_all_reported": True,
        "arms": arms,
        "support": support,
        "limitations": [
            "shape pseudo-energy is a composite likelihood, not a calibrated generative model",
            "position was already fitted from all track shapes",
            "RF tracks and dual receivers can be correlated; totals are not confidence measures",
            "hyperparameter arms were informed by the all-data descriptive audit",
            "latent circular intercept has no asserted physical LO or LNB meaning",
        ],
        "provenance": {
            "refinement_digest": digest(args.refinement),
            "rf_shard_digests": rf_digests,
            "replay_source_digest": digest(replay_path),
            "source_code_digest": digest(Path(__file__)),
        },
    }
    output["content_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--rf-shards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--grid-size", type=int, default=1024)
    run(parser.parse_args())
