#!/usr/bin/env python3
"""Extract held-frequency evidence from verified derived scanner caches.

The extractor does not read IQ.  Candidate identity, ordering, and the
training/held mask come from the frozen association product.  Only training
rows profile each candidate's constant CFO; held rows are emitted afterwards.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import pickle
from collections import defaultdict
from collections.abc import Callable, Iterable
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np

SIGMA_HZ = 100.0


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def gaussian_logpdf(residual_hz: np.ndarray, sigma_hz: float = SIGMA_HZ) -> np.ndarray:
    residual = np.asarray(residual_hz, dtype=float)
    if not math.isfinite(sigma_hz) or sigma_hz <= 0 or not np.all(np.isfinite(residual)):
        raise ValueError("frequency likelihood requires finite residuals and positive sigma")
    return -0.5 * (residual / sigma_hz) ** 2 - math.log(sigma_hz * math.sqrt(2 * math.pi))


def profile_candidates(
    measured_hz: object,
    predicted_hz: object,
    training_mask: object,
    *,
    sigma_hz: float = SIGMA_HZ,
) -> dict[str, list[float]]:
    """Profile candidate CFO and score rows without consulting held values."""
    measured = np.asarray(measured_hz, dtype=float)
    predicted = np.asarray(predicted_hz, dtype=float)
    training = np.asarray(training_mask, dtype=bool)
    if measured.ndim != 1 or predicted.ndim != 2 or predicted.shape[1] != measured.size:
        raise ValueError("measured/predicted frequency shapes disagree")
    if training.shape != measured.shape or not np.any(training) or not np.any(~training):
        raise ValueError("frequency tracks require both training and held observations")
    if not np.all(np.isfinite(measured)) or not np.all(np.isfinite(predicted)):
        raise ValueError("frequency arrays must be finite")
    offsets = np.mean(measured[None, training] - predicted[:, training], axis=1)
    residual = measured[None, :] - predicted - offsets[:, None]
    training_rms = np.sqrt(np.mean(residual[:, training] ** 2, axis=1))
    training_log_likelihood = np.sum(gaussian_logpdf(residual[:, training], sigma_hz), axis=1)
    shifted = training_log_likelihood - np.max(training_log_likelihood)
    weights = np.exp(shifted)
    weights /= weights.sum()
    return {
        "profiled_cfo_hz": offsets.tolist(),
        "training_rms_hz": training_rms.tolist(),
        "training_log_likelihood": training_log_likelihood.tolist(),
        "candidate_probabilities": weights.tolist(),
        "residual_hz": residual.tolist(),
        "log_likelihood": gaussian_logpdf(residual, sigma_hz).tolist(),
    }


def association_index(document: dict[str, Any]) -> dict[str, tuple[dict[str, Any], ...]]:
    output: dict[str, tuple[dict[str, Any], ...]] = {}
    for branch in document["branches"]:
        sid = branch["session_id"]
        rows = tuple(branch["rows"])
        keys = [(row["track_id"], row["projected_observation_id"]) for row in rows]
        if sid in output or len(keys) != len(set(keys)):
            raise ValueError("association session or observation key is duplicated")
        output[sid] = rows
    return output


def source_link_index(document: dict[str, Any], session_id: str) -> dict[tuple[str, str], str]:
    rows = document[session_id]["rows"]
    output: dict[tuple[str, str], str] = {}
    for row in rows:
        ids = row["candidate_ids"]
        if len(ids) != 1:
            continue
        key = (row["track_id"], row["observation_id"])
        if key in output:
            raise ValueError("duplicate unambiguous source link")
        output[key] = ids[0]
    return output


def extract_session(
    session_id: str,
    association_rows: Iterable[dict[str, Any]],
    source_links: dict[tuple[str, str], str],
    prepared_tracks: Iterable[Any],
    predict: Callable[[Any, list[int]], np.ndarray],
    *,
    start_utc_ns: int,
    sigma_hz: float = SIGMA_HZ,
    tolerance: float = 1e-8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join a prepared input to frozen associations and emit held rows."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in association_rows:
        grouped[row["track_id"]].append(row)
    tracks = {track.track_id: track for track in prepared_tracks}
    emitted: list[dict[str, Any]] = []
    track_count = 0
    track_masks: list[dict[str, Any]] = []
    for track_id, rows in sorted(grouped.items()):
        track = tracks.get(track_id)
        if track is None:
            raise ValueError(f"association track missing from prepared input: {track_id}")
        order = {oid: index for index, oid in enumerate(track.observation_ids)}
        if len(order) != len(track.observation_ids) or set(order) != {
            row["projected_observation_id"] for row in rows
        }:
            raise ValueError(f"association/prepared observation inventory mismatch: {track_id}")
        rows.sort(key=lambda row: order[row["projected_observation_id"]])
        candidate_ids = [int(value) for value in rows[0]["candidate_ids"]]
        stored_probabilities = np.asarray(rows[0]["candidate_probabilities"], dtype=float)
        stored_rms = np.asarray(rows[0]["candidate_training_rms_hz"], dtype=float)
        for row in rows:
            if [int(value) for value in row["candidate_ids"]] != candidate_ids:
                raise ValueError("candidate identity changed within track")
            if not np.allclose(
                row["candidate_probabilities"], stored_probabilities, rtol=0.0, atol=1e-14
            ) or not np.allclose(
                row["candidate_training_rms_hz"], stored_rms, rtol=0.0, atol=1e-12
            ):
                raise ValueError("candidate training summary changed within track")
        expected_utc_ns = np.asarray(
            [start_utc_ns + round(float(seconds) * 1e9) for seconds in track.times_s],
            dtype=np.int64,
        )
        association_utc_ns = np.asarray([row["observation_utc_ns"] for row in rows], dtype=np.int64)
        if np.any(np.abs(expected_utc_ns - association_utc_ns) > 1_000):
            raise ValueError("association/prepared observation UTC mismatch")
        support_utc_ns = np.asarray([row["support_center_utc_ns"] for row in rows], dtype=np.int64)
        propagation_utc_ns = np.asarray([row["propagation_utc_ns"] for row in rows], dtype=np.int64)
        if np.any(np.abs(association_utc_ns - support_utc_ns) > 1_000) or np.any(
            np.abs(association_utc_ns - propagation_utc_ns) > 1_000
        ):
            raise ValueError("association propagation/support UTC mismatch")
        association_mask = np.asarray([row["training"] for row in rows], dtype=bool)
        prepared_mask = np.asarray(track.training_mask, dtype=bool)
        if not np.array_equal(association_mask, prepared_mask):
            raise ValueError("association/prepared training masks disagree")
        track_masks.append(
            {
                "track_id": track_id,
                "candidate_ids": candidate_ids,
                "candidate_probabilities": stored_probabilities.tolist(),
                "candidate_training_rms_hz": stored_rms.tolist(),
                "training_observation_ids": [
                    row["projected_observation_id"]
                    for row, training in zip(rows, association_mask, strict=True)
                    if training
                ],
                "held_observation_ids": [
                    row["projected_observation_id"]
                    for row, training in zip(rows, association_mask, strict=True)
                    if not training
                ],
                "observation_sources": [
                    {
                        "observation_id": row["projected_observation_id"],
                        "training": bool(row["training"]),
                        "observation_utc_ns": row["observation_utc_ns"],
                        "source_group_id": row["source_group_id"],
                        "source_sample_start": row["source_sample_start"],
                        "source_sample_end": row["source_sample_end"],
                        "support_center_utc_ns": row["support_center_utc_ns"],
                        "stream_id": row["stream_id"],
                    }
                    for row in rows
                ],
            }
        )
        predicted = np.asarray(predict(track, candidate_ids), dtype=float)
        scored = profile_candidates(
            track.measured_hz, predicted, association_mask, sigma_hz=sigma_hz
        )
        if not np.allclose(scored["training_rms_hz"], stored_rms, rtol=tolerance, atol=tolerance):
            raise ValueError("candidate training RMS does not reproduce frozen association")
        if not np.allclose(
            scored["candidate_probabilities"], stored_probabilities, rtol=tolerance, atol=tolerance
        ):
            raise ValueError("candidate training weights do not reproduce frozen association")
        residual = np.asarray(scored["residual_hz"])
        log_likelihood = np.asarray(scored["log_likelihood"])
        offsets = scored["profiled_cfo_hz"]
        for index, row in enumerate(rows):
            if association_mask[index]:
                continue
            oid = row["projected_observation_id"]
            source_candidate_id = source_links.get((track_id, oid))
            if source_candidate_id is None:
                raise ValueError(f"held observation lacks one exact source link: {track_id}/{oid}")
            emitted.append(
                {
                    "session_id": session_id,
                    "track_id": track_id,
                    "observation_id": oid,
                    "observation_utc_ns": row["observation_utc_ns"],
                    "training": False,
                    "source_candidate_id": source_candidate_id,
                    "source_group_id": row["source_group_id"],
                    "source_sample_start": row["source_sample_start"],
                    "source_sample_end": row["source_sample_end"],
                    "support_center_utc_ns": row["support_center_utc_ns"],
                    "stream_id": row["stream_id"],
                    "candidate_ids": candidate_ids,
                    "measured_hz": float(np.asarray(track.measured_hz)[index]),
                    "candidate_predicted_hz": predicted[:, index].tolist(),
                    "candidate_profiled_cfo_hz": offsets,
                    "candidate_residual_hz": residual[:, index].tolist(),
                    "candidate_log_likelihood": log_likelihood[:, index].tolist(),
                }
            )
        track_count += 1
    return emitted, {
        "tracks": track_count,
        "held_rows": len(emitted),
        "track_masks": track_masks,
    }


def _module_receipt(module: Any) -> dict[str, str]:
    path = Path(inspect.getsourcefile(module) or "")
    if not path.is_file():
        raise ValueError(f"cannot bind installed module source: {module.__name__}")
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--associations", type=Path, required=True)
    parser.add_argument("--source-links", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("output already exists")

    # These are public derived-evidence ports from the frozen analysis runtime.
    from leo.analysis.adaptive_tle_prediction import (
        ReceiverPoint,
        RegionalTrackPredictionEvaluator,
        build_prediction_banks,
    )
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs

    from leo.analysis import adaptive_tle_prediction as prediction_module
    from leo.analysis import persistent_hop_trajectory as trajectory_module
    from leo.application import scanner_trajectory as projection_module
    from leo.operations import adaptive_tle_position_inputs as preparation_module
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky import propagation as propagation_module
    from leo.sky.frames import geodetic_to_ecef_km

    inventory = {row["session_id"]: row for row in json.loads(args.inventory.read_text())}
    manifest = json.loads(args.manifest.read_text())
    associations_document = json.loads(args.associations.read_text())
    links_document = json.loads(args.source_links.read_text())
    associations = association_index(associations_document)
    outputs: list[dict[str, Any]] = []
    accounting: dict[str, Any] = {}

    class CacheStore:
        def __init__(self, value: Any):
            self.value = value

        def load(self, sid: str) -> Any:
            if sid != self.value.session_id:
                raise KeyError(sid)
            return self.value

    poses = {
        row["pose"]["session_id"]: row["pose"]["pose_authority"] for row in manifest["sessions"]
    }
    for sid in sorted(associations):
        entry = inventory[sid]
        payload = Path(entry["cache_file"]).read_bytes()
        if not entry["ready"] or digest(payload) != entry["cache_sha256"]:
            raise ValueError(f"derived cache failed inventory binding: {sid}")
        raw = pickle.loads(payload)
        prepared = prepare_adaptive_tle_position_inputs(
            sid, inputs=CacheStore(raw), archive=TleArchiveReader(args.tle_root)
        )
        branch = next(row for row in associations_document["branches"] if row["session_id"] == sid)
        link_branch = links_document[sid]
        if (
            branch["branch"] != "truth_diagnostic"
            or branch["site"].get("diagnostic_truth") is not True
        ):
            raise ValueError(f"association branch is not the frozen truth diagnostic: {sid}")
        if branch["split"] != entry["split"]:
            raise ValueError(f"association split differs from frozen inventory: {sid}")
        if any(branch["site"][key] != poses[sid][key] for key in ("latitude_deg", "longitude_deg")):
            raise ValueError(f"association site differs from manifest pose: {sid}")
        for field in (
            "input_manifest_sha256",
            "analysis_manifest_sha256",
            "evidence_sha256",
            "snapshot_digest",
        ):
            if getattr(prepared, field) != branch[field]:
                raise ValueError(f"prepared/association {field} mismatch: {sid}")
        for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
            if link_branch[field] != entry[field] or link_branch[field] != getattr(prepared, field):
                raise ValueError(f"source-link {field} mismatch: {sid}")
        satellite_numbers = np.asarray(prepared.catalogue.satellite_numbers, dtype=int)
        index_by_id = {int(cid): index for index, cid in enumerate(satellite_numbers)}
        pose = poses[sid]
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

        def predict(
            track: Any,
            candidate_ids: list[int],
            *,
            prepared_input: Any = prepared,
            candidate_index: dict[int, int] = index_by_id,
            frozen_receiver: Any = receiver,
        ) -> np.ndarray:
            indices = np.asarray([candidate_index[cid] for cid in candidate_ids], dtype=int)
            banks, _ = build_prediction_banks(
                prepared_input.catalogue,
                indices,
                prepared_input.start_utc_ns,
                [track],
                taus_s=np.array([0.0]),
            )
            blocks = list(
                RegionalTrackPredictionEvaluator(
                    banks,
                    lambda _east, _north: frozen_receiver,
                    taus_s=np.array([0.0]),
                )(0, 0)
            )
            ids = np.concatenate([np.asarray(block.candidate_ids, dtype=int) for block in blocks])
            values = np.concatenate([np.asarray(block.predictions_hz)[:, 0, :] for block in blocks])
            lookup = {int(cid): values[index] for index, cid in enumerate(ids)}
            return np.asarray([lookup[cid] for cid in candidate_ids])

        rows, counts = extract_session(
            sid,
            associations[sid],
            source_link_index(links_document, sid),
            prepared.tracks,
            predict,
            start_utc_ns=prepared.start_utc_ns,
        )
        for row in rows:
            row["split"] = entry["split"]
        outputs.extend(rows)
        accounting[sid] = counts
        print(
            f"{sid} complete: {counts['tracks']} tracks, {counts['held_rows']} held rows",
            flush=True,
        )

    result = {
        "schema": "rx-held-frequency-evidence/v1",
        "protocol": {
            "source": "hash-verified derived ScannerTrackingInput caches; no IQ",
            "candidate_identity": "frozen association top-3; never selected from held rows",
            "prediction": (
                "tau=0 at frozen diagnostic reference coordinates; three candidates per track"
            ),
            "cfo": "per-candidate constant arithmetic mean profiled on training rows only",
            "likelihood": "normalized Gaussian log density with fixed sigma_hz=100",
            "reception_fit": "none; this artifact contains frequency evidence only",
        },
        "sigma_hz": SIGMA_HZ,
        "source_digests": {
            "inventory": digest(args.inventory.read_bytes()),
            "manifest": digest(args.manifest.read_bytes()),
            "associations": digest(args.associations.read_bytes()),
            "source_links": digest(args.source_links.read_bytes()),
        },
        "runtime_source_receipts": {
            "preparation": _module_receipt(preparation_module),
            "prediction": _module_receipt(prediction_module),
            "projection": _module_receipt(projection_module),
            "trajectory": _module_receipt(trajectory_module),
            "propagation": _module_receipt(propagation_module),
        },
        "environment": {
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "sgp4_version": version("sgp4"),
            "numpy_version": np.__version__,
        },
        "accounting": accounting,
        "rows": outputs,
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
