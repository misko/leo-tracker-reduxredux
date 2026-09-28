#!/usr/bin/env python3
"""Build satellite prediction banks from grouped training windows only.

This program must run in the installed analysis interpreter which owns the
persisted ``TrackingInput`` contract.  Evaluation-window candidate outcomes
are never projected, reconstructed, or used for fitting; partition timestamps
alone define forecast destinations.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import inspect
import json
import math
import os
import pickle
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np

SIGMA_HZ = 100.0
TRACK_CAP = 3
CATALOGUE_BATCH = 512


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_digest(value: Any) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def atomic_json(path: Path, document: dict[str, Any]) -> None:
    """Replace a checkpoint only after its complete JSON is durable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def source_window_id(raw: Any, probe: Any) -> str:
    """Reproduce the public opportunity export's outcome-free window key."""
    fields = {
        "session_id": raw.session_id,
        "visit_index": probe.visit_index,
        "probe_index": probe.probe_index,
        "probe_start_ms": probe.probe_start_ms,
        "valid_start_counter": probe.valid_start_counter,
        "channel": probe.channel,
        "edge": probe.edge,
        "sample_rate_hz": raw.sample_rate_hz,
    }
    body = json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "rx-source-window/v1:" + digest(body.encode())


def partition_index(document: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    if document.get("schema") != "rx-grouped-partition/v1":
        raise ValueError("unsupported grouped partition schema")
    result: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    allowed = {"train", "reception", "held_frequency", "embargo"}
    for row in document.get("windows", ()):
        role = row.get("role")
        sid, wid = row.get("session_id"), row.get("source_window_id")
        if role not in allowed or not isinstance(sid, str) or not isinstance(wid, str):
            raise ValueError("partition window has invalid identity or role")
        if wid in result[sid]:
            raise ValueError("partition source window is duplicated")
        start, end = row.get("window_start_utc_ns"), row.get("window_end_utc_ns")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            raise ValueError("partition window has invalid UTC bounds")
        result[sid][wid] = row
    return dict(result)


def training_only_input(raw: Any, windows: dict[str, dict[str, Any]]) -> tuple[Any, dict[str, Any]]:
    """Drop every non-training probe before any projection or reconstruction."""
    kept, seen = [], defaultdict(int)
    for probe in raw.probes:
        wid = source_window_id(raw, probe)
        row = windows.get(wid)
        if row is None:
            raise ValueError(f"raw probe absent from grouped partition: {wid}")
        seen[wid] += 1
        if row["role"] == "train":
            kept.append(probe)
    missing = sorted(set(windows).difference(seen))
    if missing:
        raise ValueError(f"partition windows absent from raw input: {missing[0]}")
    if not kept:
        raise ValueError("recording has no training probes")
    locators = [
        {
            "source_window_id": source_window_id(raw, probe),
            "visit_index": probe.visit_index,
            "probe_index": probe.probe_index,
            "probe_start_ms": probe.probe_start_ms,
            "receiver_id": probe.receiver_id,
            "valid_start_counter": probe.valid_start_counter,
            "channel": probe.channel,
            "edge": probe.edge,
            "actual_rf_hz": probe.actual_rf_hz,
        }
        for probe in kept
    ]
    return dataclasses.replace(raw, probes=tuple(kept)), {
        "source_windows": len(windows),
        "training_windows": sum(row["role"] == "train" for row in windows.values()),
        "training_probes": len(kept),
        "excluded_probes": len(raw.probes) - len(kept),
        "training_probe_locators": locators,
        "training_probe_locators_digest": canonical_digest(locators),
    }


def select_training_tracks(tracks: Iterable[Any], cap: int = TRACK_CAP) -> tuple[Any, ...]:
    """Freeze a deterministic recent-track cap without consulting scores."""
    if cap <= 0:
        raise ValueError("track cap must be positive")
    rows = list(tracks)
    rows.sort(key=lambda row: (-float(np.asarray(row.times_s)[-1]), str(row.track_id)))
    return tuple(rows[:cap])


def forecast_structural_mask(size: int) -> np.ndarray:
    """Make the unscored mixed mask required by the public track contract."""
    if size < 6:
        raise ValueError("public forecast track requires at least six timestamps")
    mask = np.zeros(size, dtype=bool)
    mask[0] = True
    return mask


def rank_candidates(
    candidate_ids: object, measured_hz: object, predicted_hz: object, *, sigma_hz: float = SIGMA_HZ
) -> list[dict[str, Any]]:
    """Profile a constant CFO and rank a complete candidate matrix by train SSE."""
    ids = np.asarray(candidate_ids, dtype=int)
    measured = np.asarray(measured_hz, dtype=float)
    predicted = np.asarray(predicted_hz, dtype=float)
    if predicted.shape != (len(ids), len(measured)) or not len(measured):
        raise ValueError("candidate prediction matrix has invalid shape")
    if not math.isfinite(sigma_hz) or sigma_hz <= 0:
        raise ValueError("sigma must be finite and positive")
    offsets = np.mean(measured[None, :] - predicted, axis=1)
    residual = measured[None, :] - predicted - offsets[:, None]
    sse = np.sum(residual**2, axis=1)
    order = sorted(range(len(ids)), key=lambda index: (float(sse[index]), int(ids[index])))
    return [
        {
            "rank": rank,
            "catalog_number": int(ids[index]),
            "profiled_cfo_hz": float(offsets[index]),
            "training_sse_hz2": float(sse[index]),
            "training_rms_hz": float(np.sqrt(sse[index] / len(measured))),
            "training_log_likelihood": float(
                -0.5 * sse[index] / sigma_hz**2
                - len(measured) * math.log(sigma_hz * math.sqrt(2 * math.pi))
            ),
        }
        for rank, index in enumerate(order, 1)
    ]


def score_prediction_blocks(
    tracks: Iterable[Any], blocks: Iterable[Any], *, require_tracks: bool = True
) -> dict[str, list[dict[str, Any]]]:
    by_track: dict[str, list[Any]] = defaultdict(list)
    for block in blocks:
        by_track[block.track_id].append(block)
    output = {}
    for track in tracks:
        rows = by_track.get(track.track_id, [])
        if not rows:
            if require_tracks:
                raise ValueError(f"prediction evaluator omitted track: {track.track_id}")
            output[track.track_id] = []
            continue
        candidate_parts, prediction_parts = [], []
        for row in rows:
            ids_part = np.asarray(row.candidate_ids, dtype=int)
            prediction_part = np.asarray(row.predictions_hz)[:, 0, :]
            if hasattr(row, "visible"):
                keep = np.asarray(row.visible, dtype=bool)
                ids_part, prediction_part = ids_part[keep], prediction_part[keep]
            if len(ids_part):
                candidate_parts.append(ids_part)
                prediction_parts.append(prediction_part)
        if not candidate_parts:
            if require_tracks:
                raise ValueError(
                    f"prediction evaluator has no eligible candidate: {track.track_id}"
                )
            output[track.track_id] = []
            continue
        ids = np.concatenate(candidate_parts)
        predicted = np.concatenate(prediction_parts)
        if len(set(ids.tolist())) != len(ids):
            raise ValueError("prediction evaluator duplicated a catalogue member")
        output[track.track_id] = rank_candidates(ids, track.measured_hz, predicted)
    return output


def forecast_geometry(
    bank: Any, receiver: Any, angle: object, *, reference_rf_hz: float, light_km_s: float
) -> dict[int, tuple[np.ndarray, ...]]:
    """Compute tau-zero Doppler and ENU line of sight from a public state bank."""
    delta = bank.position_km[:, 0] - np.asarray(receiver.ecef_km)[None, None, :]
    distance = np.linalg.norm(delta, axis=-1)
    unit = delta / distance[:, :, None]
    up = unit @ np.asarray(receiver.up)
    elevation = np.rad2deg(np.arcsin(np.clip(up, -1, 1)))
    frequency = (
        -reference_rf_hz / light_km_s * np.sum(delta * bank.velocity_km_s[:, 0], axis=-1) / distance
    )
    latitude, longitude = np.asarray(angle, dtype=float)
    east = np.array([-np.sin(longitude), np.cos(longitude), 0.0])
    north = np.array(
        [
            -np.sin(latitude) * np.cos(longitude),
            -np.sin(latitude) * np.sin(longitude),
            np.cos(latitude),
        ]
    )
    return {
        int(cid): (frequency[i], elevation[i], unit[i] @ east, unit[i] @ north, up[i])
        for i, cid in enumerate(bank.candidate_ids)
    }


def snapshot_bindings(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate the sanitized authority, which contains no old hypotheses."""
    sessions = document.get("sessions")
    if not isinstance(sessions, dict):
        raise ValueError("snapshot authority has no session mapping")
    for sid, binding in sessions.items():
        required = ("input_manifest_sha256", "analysis_manifest_sha256", "snapshot_digest")
        if (
            not isinstance(sid, str)
            or not isinstance(binding, dict)
            or not all(isinstance(binding.get(key), str) for key in required)
            or not isinstance(binding.get("site"), dict)
        ):
            raise ValueError("snapshot authority session is invalid")
    return sessions


def _module_receipt(module: Any) -> dict[str, str]:
    path = Path(inspect.getsourcefile(module) or "")
    if not path.is_file():
        raise ValueError(f"cannot bind installed module source: {module.__name__}")
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def main() -> None:  # noqa: PLR0915 - linear, auditable research extraction
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--partitions", type=Path, required=True)
    parser.add_argument("--snapshot-authority", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("output already exists")

    from leo.analysis.adaptive_tle_prediction import (
        LIGHT_KM_S,
        REFERENCE_RF_HZ,
        AdaptiveTrackInput,
        ReceiverPoint,
        RegionalTrackPredictionEvaluator,
        build_prediction_banks,
    )
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs

    from leo.analysis import adaptive_tle_prediction as prediction_module
    from leo.application import scanner_trajectory as projection_module
    from leo.operations import adaptive_tle_position_inputs as preparation_module
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky import propagation as propagation_module
    from leo.sky.frames import geodetic_to_ecef_km

    inventory = {row["session_id"]: row for row in json.loads(args.inventory.read_text())}
    manifest = json.loads(args.manifest.read_text())
    partition_document = json.loads(args.partitions.read_text())
    partitions = partition_index(partition_document)
    old = snapshot_bindings(json.loads(args.snapshot_authority.read_text()))
    poses = {
        row["pose"]["session_id"]: row["pose"]["pose_authority"] for row in manifest["sessions"]
    }

    class CacheStore:
        def __init__(self, value: Any):
            self.value = value

        def load(self, sid: str) -> Any:
            if sid != self.value.session_id:
                raise KeyError(sid)
            return self.value

    recordings, prediction_rows = [], []
    for sid in sorted(partitions):
        entry, binding = inventory[sid], old[sid]
        payload = Path(entry["cache_file"]).read_bytes()
        if not entry["ready"] or digest(payload) != entry["cache_sha256"]:
            raise ValueError(f"derived cache failed inventory binding: {sid}")
        raw = pickle.loads(payload)
        for key in ("input_manifest_sha256", "analysis_manifest_sha256"):
            if getattr(raw, key) != entry[key] or getattr(raw, key) != binding[key]:
                raise ValueError(f"raw/historical {key} mismatch: {sid}")
        filtered, counts = training_only_input(raw, partitions[sid])
        prepared = prepare_adaptive_tle_position_inputs(
            sid, inputs=CacheStore(filtered), archive=TleArchiveReader(args.tle_root)
        )
        if prepared.snapshot_digest != binding["snapshot_digest"]:
            raise ValueError(f"training preparation changed causal snapshot: {sid}")
        tracks = select_training_tracks(prepared.tracks)
        if not tracks:
            raise ValueError(f"training partition reconstructs no qualifying tracks: {sid}")

        pose = poses[sid]
        if any(pose[key] != binding["site"][key] for key in ("latitude_deg", "longitude_deg")):
            raise ValueError(f"manifest/snapshot site mismatch: {sid}")
        angle = np.deg2rad([pose["latitude_deg"], pose["longitude_deg"]])
        receiver = ReceiverPoint(
            geodetic_to_ecef_km(pose["latitude_deg"], pose["longitude_deg"], 0),
            np.array(
                [
                    np.cos(angle[0]) * np.cos(angle[1]),
                    np.cos(angle[0]) * np.sin(angle[1]),
                    np.sin(angle[0]),
                ]
            ),
        )
        accumulated: dict[str, list[dict[str, Any]]] = defaultdict(list)
        receipts = []
        candidate_indices = np.asarray(prepared.candidate_indices, dtype=int)
        for begin in range(0, len(candidate_indices), CATALOGUE_BATCH):
            banks, receipt = build_prediction_banks(
                prepared.catalogue,
                candidate_indices[begin : begin + CATALOGUE_BATCH],
                prepared.start_utc_ns,
                tracks,
                taus_s=np.array([0.0]),
            )
            blocks = list(
                RegionalTrackPredictionEvaluator(
                    banks,
                    lambda _east, _north, point=receiver: point,
                    taus_s=np.array([0.0]),
                )(0, 0)
            )
            for track_id, rows in score_prediction_blocks(
                tracks, blocks, require_tracks=False
            ).items():
                accumulated[track_id].extend(rows)
            receipts.append(dataclasses.asdict(receipt))
        ranked = {
            track.track_id: sorted(
                accumulated[track.track_id],
                key=lambda row: (row["training_sse_hz2"], row["catalog_number"]),
            )
            for track in tracks
        }
        for rows in ranked.values():
            peak = max(row["training_log_likelihood"] for row in rows)
            weights = np.exp(np.asarray([row["training_log_likelihood"] - peak for row in rows]))
            weights /= weights.sum()
            for rank, row in enumerate(rows, 1):
                row["rank"] = rank
                row["catalogue_probability"] = float(weights[rank - 1])

        target_windows = sorted(
            (
                row
                for row in partitions[sid].values()
                if row["role"] in {"reception", "held_frequency"}
            ),
            key=lambda row: (row["window_start_utc_ns"], row["source_window_id"]),
        )
        target_midpoints = np.asarray(
            [row["window_midpoint_utc_ns"] for row in target_windows], dtype=np.int64
        )
        target_times = (target_midpoints - prepared.start_utc_ns).astype(float) / 1e9
        selected_ids = sorted(
            {row["catalog_number"] for track in tracks for row in ranked[track.track_id][:3]}
        )
        index_by_id = {
            int(value): index for index, value in enumerate(prepared.catalogue.satellite_numbers)
        }
        if target_windows:
            forecast = AdaptiveTrackInput(
                "partition-target-windows",
                tuple(row["source_window_id"] for row in target_windows),
                target_times,
                np.zeros(len(target_times)),
                forecast_structural_mask(len(target_times)),
            )
            future_banks, _ = build_prediction_banks(
                prepared.catalogue,
                [index_by_id[value] for value in selected_ids],
                prepared.start_utc_ns,
                [forecast],
                taus_s=np.array([0.0]),
            )
            bank = future_banks[0]
            future = forecast_geometry(
                bank,
                receiver,
                angle,
                reference_rf_hz=REFERENCE_RF_HZ,
                light_km_s=LIGHT_KM_S,
            )
        else:
            future = {}
        for track in tracks:
            top = ranked[track.track_id][:3]
            retained_mass = sum(row["catalogue_probability"] for row in top)
            for candidate in top:
                candidate["conditional_top3_probability"] = (
                    candidate["catalogue_probability"] / retained_mass
                )
            prediction_rows.append(
                {
                    "session_id": sid,
                    "track_id": track.track_id,
                    "training_observation_ids": list(track.observation_ids),
                    "training_start_utc_ns": prepared.start_utc_ns
                    + round(float(track.times_s[0]) * 1e9),
                    "training_end_utc_ns": prepared.start_utc_ns
                    + round(float(track.times_s[-1]) * 1e9),
                    "retained_catalogue_probability_mass": retained_mass,
                    "top_candidates": [
                        {
                            **candidate,
                            "window_predictions": [
                                {
                                    "source_window_id": window["source_window_id"],
                                    "role": window["role"],
                                    "window_start_utc_ns": window["window_start_utc_ns"],
                                    "window_end_utc_ns": window["window_end_utc_ns"],
                                    "prediction_utc_ns": window["window_midpoint_utc_ns"],
                                    "predicted_hz": float(
                                        future[candidate["catalog_number"]][0][index]
                                        + candidate["profiled_cfo_hz"]
                                    ),
                                    "elevation_deg": float(
                                        future[candidate["catalog_number"]][1][index]
                                    ),
                                    "visible": bool(
                                        future[candidate["catalog_number"]][1][index] >= 0
                                    ),
                                    "los_enu_unit": {
                                        "east": float(
                                            future[candidate["catalog_number"]][2][index]
                                        ),
                                        "north": float(
                                            future[candidate["catalog_number"]][3][index]
                                        ),
                                        "up": float(future[candidate["catalog_number"]][4][index]),
                                    },
                                }
                                for index, window in enumerate(target_windows)
                            ],
                        }
                        for candidate in top
                    ],
                }
            )
        recordings.append(
            {
                "session_id": sid,
                **counts,
                "reconstructed_training_tracks": len(prepared.tracks),
                "selected_training_tracks": len(tracks),
                "eligible_catalogue_count": len(prepared.candidate_indices),
                "snapshot_digest": prepared.snapshot_digest,
                "training_evidence_sha256": prepared.evidence_sha256,
                "prediction_bank_receipts": receipts,
            }
        )
        atomic_json(
            args.output,
            {
                "schema": "rx-training-candidate-bank/v1",
                "status": "running",
                "completed_session_ids": [row["session_id"] for row in recordings],
                "recordings": recordings,
                "tracks": prediction_rows,
            },
        )

    result = {
        "schema": "rx-training-candidate-bank/v1",
        "status": "complete",
        "protocol": {
            "partition_filter_order": "raw.probes role=train before projection/reconstruction",
            "track_selection": (
                "latest training end UTC descending, then track_id; cap 3 per recording"
            ),
            "candidate_search": (
                "complete causal Starlink catalogue passed to the public predictor; "
                "public training-epoch visibility eligibility; tau=0; known roof point"
            ),
            "ranking": (
                "constant CFO profiled on every selected training observation; SSE; sigma_hz=100"
            ),
            "structural_masks": (
                "prepared masks are retained only for the public contract and ignored by ranking; "
                "forecast mask is first-true/remainder-false and is not scored"
            ),
            "prediction_destinations": (
                "partition timestamps only; non-training outcomes are never used or projected"
            ),
            "reception_model": "none",
        },
        "sigma_hz": SIGMA_HZ,
        "track_cap_per_recording": TRACK_CAP,
        "catalogue_batch_size": CATALOGUE_BATCH,
        "prediction_reference_rf_hz": REFERENCE_RF_HZ,
        "trajectory_canonical_rf_hz": 11_200_000_000.0,
        "source_digests": {
            "inventory": digest(args.inventory.read_bytes()),
            "manifest": digest(args.manifest.read_bytes()),
            "partitions": digest(args.partitions.read_bytes()),
            "snapshot_authority": digest(args.snapshot_authority.read_bytes()),
        },
        "runtime_source_receipts": {
            "preparation": _module_receipt(preparation_module),
            "prediction": _module_receipt(prediction_module),
            "projection": _module_receipt(projection_module),
            "propagation": _module_receipt(propagation_module),
        },
        "environment": {
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "sgp4_version": version("sgp4"),
            "numpy_version": np.__version__,
        },
        "partition_binding_digest": canonical_digest(partition_document),
        "forecast_coordinate": "normalized_track_hz_only",
        "raw_candidate_matching_ready": False,
        "raw_candidate_matching_limitation": (
            "training-only RF/channel/receiver alias anchors are not yet exported; "
            "no evaluation-window alias choice was made"
        ),
        "recordings": recordings,
        "tracks": prediction_rows,
    }
    atomic_json(args.output, result)


if __name__ == "__main__":
    main()
