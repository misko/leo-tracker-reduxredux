"""Describe competing frozen prefix tracks without fitting or selecting a match."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

ROLES = ("reception", "held_frequency")
RECEIVERS = ("rx0", "rx1")
THRESHOLDS = (500, 1500)


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _lane_key(row):
    return (
        row["session_id"],
        int(row["channel"]),
        str(row["edge"]),
        float(row["actual_rf_hz"]),
    )


def _wrapped_absolute(value, prediction, period):
    return abs((float(value) - float(prediction) + period / 2.0) % period - period / 2.0)


def _mean(rows):
    if not rows:
        return None
    names = rows[0]["metrics"]
    return {
        "windows": len(rows),
        "metrics": {
            name: math.fsum(row["metrics"][name] for row in rows) / len(rows)
            for name in names
        },
    }


def _track_receipt(track):
    points = track.get("training_alias_points", [])
    if not points:
        raise ValueError("mapped prefix track has no support points")
    times = [point.get("support_center_utc_ns") for point in points]
    if any(not isinstance(value, int) for value in times):
        raise ValueError("prefix support times must be integer nanoseconds")
    window_candidates = {}
    window_observations = {}
    seen_observations = set()
    for point in points:
        window_id = point.get("source_window_id")
        candidate_id = point.get("candidate_id")
        observation_id = point.get("observation_id")
        if (
            not isinstance(window_id, str)
            or not isinstance(candidate_id, str)
            or not isinstance(observation_id, str)
        ):
            raise ValueError("prefix support lacks public window/candidate/observation identity")
        if observation_id in seen_observations:
            raise ValueError("prefix track repeats a public observation identity")
        seen_observations.add(observation_id)
        window_candidates.setdefault(window_id, []).append(candidate_id)
        window_observations.setdefault(window_id, []).append(observation_id)
    return {
        "track_id": track["track_id"],
        "receiver_id": int(track["receiver_id"]),
        "support_points": len(points),
        "support_windows": len(window_candidates),
        "support_start_utc_ns": min(times),
        "support_end_utc_ns": max(times),
        "support_window_ids": sorted(window_candidates),
        "candidate_ids_by_window": {
            window: sorted(values) for window, values in sorted(window_candidates.items())
        },
        "observation_ids_by_window": {
            window: sorted(values) for window, values in sorted(window_observations.items())
        },
    }


def _overlaps(receipts):
    rows = []
    for left, right in combinations(receipts, 2):
        if left["receiver_id"] != right["receiver_id"]:
            continue
        shared = sorted(set(left["support_window_ids"]) & set(right["support_window_ids"]))
        windows = []
        for window_id in shared:
            left_ids = left["candidate_ids_by_window"][window_id]
            right_ids = right["candidate_ids_by_window"][window_id]
            left_observations = left["observation_ids_by_window"][window_id]
            right_observations = right["observation_ids_by_window"][window_id]
            windows.append(
                {
                    "source_window_id": window_id,
                    "left_candidate_ids": left_ids,
                    "right_candidate_ids": right_ids,
                    "candidate_id_sets_disjoint": set(left_ids).isdisjoint(right_ids),
                    "left_observation_ids": left_observations,
                    "right_observation_ids": right_observations,
                    "observation_id_sets_disjoint": set(left_observations).isdisjoint(
                        right_observations
                    ),
                }
            )
        rows.append(
            {
                "left_track_id": left["track_id"],
                "right_track_id": right["track_id"],
                "receiver_id": left["receiver_id"],
                "shared_source_windows": len(windows),
                "distinct_observation_overlap_windows": sum(
                    row["observation_id_sets_disjoint"] for row in windows
                ),
                "windows": windows,
            }
        )
    return rows


def analyze(document, mapping):
    """Compare all-nominee and track-conditional forecast compatibility."""
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported geometry dataset")
    if mapping.get("schema") != "rx-training-alias-mapping/v1" or mapping.get(
        "status"
    ) != "complete":
        raise ValueError("mapping must be complete rx-training-alias-mapping/v1")
    mapped = {}
    for track in mapping.get("tracks", []):
        key = _lane_key(track)
        identity = (str(track["track_id"]), int(track["receiver_id"]))
        if identity in {(row["track_id"], int(row["receiver_id"])) for row in mapped.get(key, [])}:
            raise ValueError("mapping repeats a lane/track/receiver identity")
        mapped.setdefault(key, []).append(track)

    lanes = []
    record_windows = {}
    record_splits = {}
    seen_window_ids = set()
    for source in document.get("lanes", []):
        key = _lane_key(source["lane"])
        split = source.get("recording_split")
        if split not in {"calibration", "evaluation"}:
            raise ValueError("lane recording split must be calibration or evaluation")
        if key[0] in record_splits and record_splits[key[0]] != split:
            raise ValueError("recording has conflicting split labels")
        record_splits[key[0]] = split
        period = float(source.get("alias_period_hz", np.nan))
        if not math.isfinite(period) or period <= 0:
            raise ValueError("alias period must be positive and finite")
        components = source.get("components", [])
        if len(components) < 2 or components[-1].get("kind") != "other" or any(
            row.get("kind") != "track_candidate" for row in components[:-1]
        ):
            raise ValueError("components must be track candidates followed by other")
        nominees = components[:-1]
        nominee_keys = [(row.get("track_id"), row.get("catalog_number")) for row in nominees]
        if len(nominee_keys) != len(set(nominee_keys)):
            raise ValueError("duplicate track/catalog nominee key")
        track_ids = sorted({str(row["track_id"]) for row in nominees})
        tracks = mapped.get(key, [])
        mapped_ids = {str(track["track_id"]) for track in tracks}
        if mapped_ids != set(track_ids):
            raise ValueError("dataset nominee tracks do not exactly match mapping lane")
        windows = source.get("windows", [])
        times = [window.get("prediction_utc_ns") for window in windows]
        if not windows or any(not isinstance(value, int) for value in times) or any(
            right <= left for left, right in zip(times, times[1:], strict=False)
        ):
            raise ValueError("scored windows must have increasing integer times")
        roles = [window.get("role") for window in windows]
        if any(role not in ROLES for role in roles):
            raise ValueError("unsupported scored window role")
        if "held_frequency" in roles and any(
            role == "reception" for role in roles[roles.index("held_frequency") :]
        ):
            raise ValueError("reception windows must precede held-frequency windows")
        window_ids = [window.get("source_window_id") for window in windows]
        if any(not isinstance(value, str) or not value for value in window_ids) or any(
            value in seen_window_ids for value in window_ids
        ):
            raise ValueError("source window IDs must be nonempty and globally unique")
        if len(window_ids) != len(set(window_ids)):
            raise ValueError("source window IDs must be unique within a lane")
        seen_window_ids.update(window_ids)
        receipts = [_track_receipt(track) for track in tracks]
        first_scored = min(times)
        if any(receipt["support_end_utc_ns"] >= first_scored for receipt in receipts):
            raise ValueError("prefix support is not strictly earlier than scored windows")
        receipt_by_track = {}
        for receipt in receipts:
            receipt_by_track.setdefault(receipt["track_id"], []).append(receipt)
        log_prior = np.asarray(
            [
                -np.inf if nominee.get("log_prior") is None else float(nominee["log_prior"])
                for nominee in nominees
            ]
        )
        if np.any(np.isnan(log_prior)) or np.any(log_prior == np.inf) or not np.isfinite(
            logsumexp(log_prior)
        ):
            raise ValueError("lane has no finite nominee prior mass")
        frozen_weights = np.exp(log_prior - logsumexp(log_prior))
        conditional = {}
        for track_id in track_ids:
            indices = [
                index
                for index, nominee in enumerate(nominees)
                if nominee["track_id"] == track_id
            ]
            track_logs = log_prior[indices]
            if not np.isfinite(logsumexp(track_logs)):
                raise ValueError("prefix track has no finite conditional nominee mass")
            weights = np.exp(track_logs - logsumexp(track_logs))
            conditional[track_id] = (indices, weights)

        window_rows = []
        for window in windows:
            predictions = window.get("predictions", [])
            if len(predictions) != len(nominees):
                raise ValueError("prediction/nominee cardinality mismatch")
            prediction_keys = [
                (prediction.get("track_id"), prediction.get("catalog_number"))
                for prediction in predictions
            ]
            if prediction_keys != nominee_keys:
                raise ValueError("prediction key set/order does not match nominees")
            compatible = {}
            for index, (nominee, prediction) in enumerate(zip(nominees, predictions, strict=True)):
                expected = (nominee["track_id"], int(nominee["catalog_number"]))
                actual = (prediction.get("track_id"), int(prediction.get("catalog_number")))
                if actual != expected:
                    raise ValueError("prediction/nominee order mismatch")
                visible = prediction.get("visible")
                mu = float(prediction.get("mu_canonical_rx0_hz", np.nan))
                if not isinstance(visible, bool) or not math.isfinite(mu):
                    raise ValueError("invalid forecast visibility or frequency")
                compatible[index] = {}
                for receiver in RECEIVERS:
                    observed = window.get("observed", {}).get(receiver)
                    if not isinstance(observed, list):
                        raise ValueError("window lacks receiver candidate list")
                    if any(
                        not math.isfinite(float(candidate.get("canonical_rx0_hz", np.nan)))
                        for candidate in observed
                    ):
                        raise ValueError("observed candidate frequency must be finite")
                    residual = min(
                        (
                            _wrapped_absolute(
                                candidate["canonical_rx0_hz"], mu, period
                            )
                            for candidate in observed
                        ),
                        default=math.inf,
                    )
                    compatible[index][receiver] = {
                        threshold: bool(visible and residual <= threshold)
                        for threshold in THRESHOLDS
                    }
            metrics = {}
            track_metrics = {}
            for track_id, (indices, weights) in conditional.items():
                row = {}
                for receiver in RECEIVERS:
                    for threshold in THRESHOLDS:
                        name = f"{receiver}_within_{threshold}hz"
                        row[name] = math.fsum(
                            weight * compatible[index][receiver][threshold]
                            for index, weight in zip(indices, weights, strict=True)
                        )
                row["forecast_age_s"] = (
                    window["prediction_utc_ns"]
                    - max(item["support_end_utc_ns"] for item in receipt_by_track[track_id])
                ) / 1e9
                if row["forecast_age_s"] <= 0:
                    raise ValueError("forecast age must be strictly positive")
                track_metrics[track_id] = row
            for receiver in RECEIVERS:
                for threshold in THRESHOLDS:
                    suffix = f"{receiver}_within_{threshold}hz"
                    metrics[f"frozen_prior_weighted_{suffix}"] = math.fsum(
                        weight * compatible[index][receiver][threshold]
                        for index, weight in enumerate(frozen_weights)
                    )
                    metrics[f"any_nominee_ceiling_{suffix}"] = float(
                        any(
                            compatible[index][receiver][threshold]
                            for index in range(len(nominees))
                        )
                    )
                    metrics[f"optimistic_track_conditional_max_{suffix}"] = max(
                        row[suffix] for row in track_metrics.values()
                    )
            exported = {
                "source_window_id": window["source_window_id"],
                "role": window["role"],
                "prediction_utc_ns": window["prediction_utc_ns"],
                "observed_counts": {
                    receiver: len(window["observed"][receiver]) for receiver in RECEIVERS
                },
                "metrics": metrics,
                "tracks": track_metrics,
            }
            window_rows.append(exported)
            record_windows.setdefault(key[0], []).append(exported)
        lanes.append(
            {
                "lane": source["lane"],
                "recording_split": split,
                "track_count": len(track_ids),
                "tracks": [
                    {
                        "track_id": track_id,
                        "conditional_nominee_count": len(conditional[track_id][0]),
                        "conditional_nominees": [
                            {
                                "track_id": nominees[index]["track_id"],
                                "catalog_number": nominees[index]["catalog_number"],
                                "log_prior": (
                                    float(log_prior[index])
                                    if np.isfinite(log_prior[index])
                                    else None
                                ),
                            }
                            for index in conditional[track_id][0]
                        ],
                        "conditional_nominee_weights": conditional[track_id][1].tolist(),
                        "prefix_receivers": receipt_by_track[track_id],
                    }
                    for track_id in track_ids
                ],
                "prefix_track_pair_overlaps": _overlaps(receipts),
                "windows": window_rows,
            }
        )

    records = {}
    for session_id, windows in record_windows.items():
        records[session_id] = {
            "recording_split": record_splits[session_id],
            "roles": {
                role: _mean([window for window in windows if window["role"] == role])
                for role in ROLES
            },
        }
    aggregate = {}
    for role in ROLES:
        supported = {
            sid: row["roles"][role]
            for sid, row in records.items()
            if row["roles"][role] is not None
        }
        if not supported:
            continue
        names = next(iter(supported.values()))["metrics"]
        aggregate[role] = {
            "records": len(supported),
            "windows": sum(row["windows"] for row in supported.values()),
            "metrics": {
                name: math.fsum(row["metrics"][name] for row in supported.values())
                / len(supported)
                for name in names
            },
        }
    aggregate_by_split = {}
    for split in sorted(set(record_splits.values())):
        aggregate_by_split[split] = {}
        for role in ROLES:
            supported = {
                sid: row["roles"][role]
                for sid, row in records.items()
                if row["recording_split"] == split and row["roles"][role] is not None
            }
            if not supported:
                continue
            names = next(iter(supported.values()))["metrics"]
            aggregate_by_split[split][role] = {
                "records": len(supported),
                "windows": sum(row["windows"] for row in supported.values()),
                "metrics": {
                    name: math.fsum(row["metrics"][name] for row in supported.values())
                    / len(supported)
                    for name in names
                },
            }
    return {
        "schema": "rx-track-competition/v1",
        "status": "complete",
        "lanes": lanes,
        "records": records,
        "aggregate_equal_record": aggregate,
        "aggregate_equal_record_by_split": aggregate_by_split,
        "interpretation": (
            "Conditional weights are normalized within each frozen prefix track. The maximum "
            "across tracks and all-nominee ceiling are optimistic support diagnostics, not "
            "calibrated satellite probabilities or matching decisions."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_payload, mapping_payload = args.dataset.read_bytes(), args.mapping.read_bytes()
    document, mapping = json.loads(dataset_payload), json.loads(mapping_payload)
    mapping_hash = _digest(mapping_payload)
    if document.get("source_digests", {}).get("mapping") != f"sha256:{mapping_hash}":
        raise ValueError("dataset is not directly bound to mapping bytes")
    result = analyze(document, mapping)
    result["source_sha256"] = {
        "dataset": _digest(dataset_payload),
        "mapping": mapping_hash,
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
