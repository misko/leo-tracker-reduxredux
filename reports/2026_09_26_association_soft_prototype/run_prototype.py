#!/usr/bin/env python3
"""Bounded, truth-free soft-association replay of published adaptive scans."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import (
    RegionalTrackPredictionEvaluator,
    build_prediction_banks,
)
from leo.cli.adaptive_tle_position import PRIORS, REFERENCE, _coordinates, _point_factory
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

CAP_HZ = 800.0
TEMPERATURES_HZ = (5.0, 10.0, 20.0)
MARGINS_HZ = (5.0, 10.0, 20.0)
OFFSETS_KM = (-12.5, 0.0, 12.5)


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    q = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(
        (lon2 - lon1) / 2
    ) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, q)))


def _local(center: tuple[float, float], point: tuple[float, float]) -> tuple[float, float]:
    lat1, lon1, lat2, lon2 = map(math.radians, (*center, *point))
    dlon = lon2 - lon1
    bearing = math.atan2(
        math.sin(dlon) * math.cos(lat2),
        math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon),
    )
    distance = _distance_km(center, point)
    return distance * math.sin(bearing), distance * math.cos(bearing)


def _candidate_rows(blocks) -> dict[str, dict[str, float]]:
    """Return best-tau train/heldout values for every distinct identity."""
    candidates: dict[str, dict[str, float]] = {}
    for block in blocks:
        measured = np.asarray(block.measured_hz)
        prediction = np.asarray(block.predictions_hz)
        train = np.asarray(block.training_mask)
        visible = np.asarray(block.visible)
        if not len(block.candidate_ids):
            continue
        residual = measured[None, None, :] - prediction
        offsets = np.mean(residual[:, :, train], axis=2)
        centered = residual - offsets[:, :, None]
        train_rms = np.sqrt(np.mean(centered[:, :, train] ** 2, axis=2))
        held_rms = np.sqrt(np.mean(centered[:, :, ~train] ** 2, axis=2))
        if visible.ndim == 1:
            visible = np.broadcast_to(visible[:, None], train_rms.shape)
        train_rms = np.where(visible, train_rms, np.inf)
        tau_rows = np.argmin(train_rms, axis=1)
        for index, candidate_id in enumerate(block.candidate_ids):
            tau = int(tau_rows[index])
            if not np.isfinite(train_rms[index, tau]):
                continue
            row = {
                "candidate_id": str(candidate_id),
                "heldout_rms_hz": float(held_rms[index, tau]),
                "training_rms_hz": float(train_rms[index, tau]),
                "tau_s": float(block.taus_s[tau]),
            }
            previous = candidates.get(row["candidate_id"])
            if previous is None or (
                row["heldout_rms_hz"], row["training_rms_hz"], row["tau_s"]
            ) < (
                previous["heldout_rms_hz"], previous["training_rms_hz"], previous["tau_s"]
            ):
                candidates[row["candidate_id"]] = row
    return candidates


def _track_summary(blocks) -> dict:
    blocks = tuple(blocks)
    first = blocks[0]
    rows = sorted(
        _candidate_rows(blocks).values(),
        key=lambda row: (row["heldout_rms_hz"], row["training_rms_hz"], int(row["candidate_id"])),
    )
    weight = len(np.unique(np.floor(first.times_s).astype(int)))
    if not rows:
        return {"track_id": first.track_id, "weight_s": weight, "candidates": []}
    margin = None if len(rows) < 2 else rows[1]["heldout_rms_hz"] - rows[0]["heldout_rms_hz"]
    return {
        "track_id": first.track_id,
        "weight_s": weight,
        "candidate_count": len(rows),
        "margin_hz": margin,
        "candidates": rows[:3],
    }


def _scores(tracks: list[dict]) -> dict[str, float]:
    total = sum(row["weight_s"] for row in tracks)
    losses: dict[str, float] = {"hard": 0.0}
    losses.update({f"soft_T{int(t)}": 0.0 for t in TEMPERATURES_HZ})
    losses.update({f"reject_m{int(m)}": 0.0 for m in MARGINS_HZ})
    for track in tracks:
        rows = track["candidates"]
        weight = track["weight_s"]
        if not rows:
            for key in losses:
                losses[key] += weight * CAP_HZ**2
            continue
        rms = np.asarray([row["heldout_rms_hz"] for row in rows])
        capped2 = np.minimum(rms, CAP_HZ) ** 2
        losses["hard"] += weight * capped2[0]
        for temperature in TEMPERATURES_HZ:
            probabilities = np.exp(-(rms - rms[0]) / temperature)
            probabilities /= np.sum(probabilities)
            losses[f"soft_T{int(temperature)}"] += weight * float(probabilities @ capped2)
        margin = None if len(rows) < 2 else float(rms[1] - rms[0])
        for threshold in MARGINS_HZ:
            # With no visible runner, ambiguity is unresolved rather than infinite evidence.
            loss = CAP_HZ**2 if margin is None or margin < threshold else capped2[0]
            losses[f"reject_m{int(threshold)}"] += weight * loss
    return {key: math.sqrt(value / total) for key, value in losses.items()}


def _proposals(document: dict) -> list[dict]:
    points: dict[tuple[float, float], dict] = {}
    for prior in document["priors"]:
        selected = prior["selected"]
        center = (selected["latitude_deg"], selected["longitude_deg"])
        for east in OFFSETS_KM:
            for north in OFFSETS_KM:
                lat, lon = _coordinates(*center, east, north)
                key = (round(lat, 8), round(lon, 8))
                points[key] = {
                    "latitude_deg": lat,
                    "longitude_deg": lon,
                    "seed": prior["name"],
                    "seed_east_km": east,
                    "seed_north_km": north,
                }
    return list(points.values())


def _analyze_session(bulk_root: Path, tle_root: Path, session_id: str) -> dict:
    started = time.monotonic()
    document_path = bulk_root / "scanner-adaptive-tle-position-v2" / session_id / "document.json"
    document = json.loads(document_path.read_text())
    store = ScannerTrackingInputStore(bulk_root)
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            session_id, inputs=store, archive=TleArchiveReader(tle_root)
        )
    finally:
        store.close()
    if prepared.evidence_sha256 != document["evidence_sha256"]:
        raise ValueError(f"{session_id}: prepared evidence does not match published evidence")
    published_snapshot = document["diagnostics"]["snapshot_digest"]
    if prepared.snapshot_digest != published_snapshot:
        raise ValueError(f"{session_id}: prepared TLE snapshot does not match publication")
    banks, receipt = build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns, prepared.tracks
    )
    proposals = _proposals(document)
    evaluations = []
    # Score every physical point once. Local coordinates only express prior eligibility.
    geometry_name = "sacramento"
    geometry_lat, geometry_lon, _ = PRIORS[geometry_name]
    evaluator = RegionalTrackPredictionEvaluator(banks, _point_factory(geometry_lat, geometry_lon))
    scored = []
    for proposal_index, proposal in enumerate(proposals):
        point = (proposal["latitude_deg"], proposal["longitude_deg"])
        east, north = _local((geometry_lat, geometry_lon), point)
        grouped: dict[str, list] = {}
        for block in evaluator(east, north):
            grouped.setdefault(block.track_id, []).append(block)
        tracks = [_track_summary(grouped[key]) for key in sorted(grouped)]
        scored.append((proposal_index, proposal, tracks, _scores(tracks)))
    for prior_name, (latitude, longitude, radius_km) in PRIORS.items():
        center = (latitude, longitude)
        for proposal_index, proposal, tracks, scores in scored:
            point = (proposal["latitude_deg"], proposal["longitude_deg"])
            east, north = _local(center, point)
            if math.hypot(east, north) > radius_km + 1e-6:
                continue
            evaluations.append(
                {
                    "prior": prior_name,
                    "proposal_index": proposal_index,
                    **proposal,
                    "east_km": east,
                    "north_km": north,
                    "scores_hz": scores,
                    "tracks": tracks,
                }
            )
    selections = {}
    for prior_name in PRIORS:
        eligible = [row for row in evaluations if row["prior"] == prior_name]
        selections[prior_name] = {}
        for method in next(iter(eligible))["scores_hz"]:
            chosen = min(eligible, key=lambda row: (row["scores_hz"][method], row["proposal_index"]))
            selections[prior_name][method] = {
                "proposal_index": chosen["proposal_index"],
                "score_hz": chosen["scores_hz"][method],
                "latitude_deg": chosen["latitude_deg"],
                "longitude_deg": chosen["longitude_deg"],
            }
    # Truth is touched only after every method has selected a proposal.
    for methods in selections.values():
        for selected in methods.values():
            selected["horizontal_error_km"] = _distance_km(
                (selected["latitude_deg"], selected["longitude_deg"]), REFERENCE
            )
    published = {
        row["name"]: {
            "score_hz": row["selected"]["capped_weighted_rmse_hz"],
            "horizontal_error_km": row["selected"]["horizontal_error_m"] / 1000,
            "latitude_deg": row["selected"]["latitude_deg"],
            "longitude_deg": row["selected"]["longitude_deg"],
        }
        for row in document["priors"]
    }
    parity = {}
    for prior_name, expected in published.items():
        row = min(
            (item for item in evaluations if item["prior"] == prior_name),
            key=lambda item: _distance_km(
                (item["latitude_deg"], item["longitude_deg"]),
                (expected["latitude_deg"], expected["longitude_deg"]),
            ),
        )
        proposal_distance = _distance_km(
            (row["latitude_deg"], row["longitude_deg"]),
            (expected["latitude_deg"], expected["longitude_deg"]),
        )
        if proposal_distance > 1e-5:
            raise ValueError(f"{session_id}/{prior_name}: exact published seed is absent")
        difference = row["scores_hz"]["hard"] - expected["score_hz"]
        parity[prior_name] = {
            "proposal_distance_km": proposal_distance,
            "replayed_score_hz": row["scores_hz"]["hard"],
            "difference_hz": difference,
        }
        if abs(difference) > 1e-5:
            raise ValueError(f"{session_id}/{prior_name}: hard-score parity failed by {difference} Hz")
    return {
        "session_id": session_id,
        "elapsed_s": time.monotonic() - started,
        "candidate_count": receipt.candidate_count,
        "track_count": receipt.track_count,
        "proposal_count": len(proposals),
        "published": published,
        "bindings": {
            "document_sha256": hashlib.sha256(document_path.read_bytes()).hexdigest(),
            "evidence_sha256": prepared.evidence_sha256,
            "snapshot_digest": prepared.snapshot_digest,
        },
        "parity": parity,
        "selections": selections,
        "evaluations": evaluations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("sessions", nargs="+")
    args = parser.parse_args()
    payload = {
        "schema": "association-soft-prototype/v1",
        "protocol": {
            "temperatures_hz": TEMPERATURES_HZ,
            "reject_margins_hz": MARGINS_HZ,
            "top_k": 3,
            "cap_hz": CAP_HZ,
            "offsets_km": OFFSETS_KM,
            "proposal_source": "union-of-published-prior-winners-plus-local-offsets-truth-free",
            "soft_weights": "heuristic-heldout-rms-softmax-not-calibrated-probabilities",
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "sessions": [],
    }
    for raw in args.sessions:
        session_id = raw if raw.startswith("scan-fw-") else f"scan-fw-{raw}"
        result = _analyze_session(args.bulk_root, args.tle_root, session_id)
        payload["sessions"].append(result)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")
        print(session_id, f"{result['elapsed_s']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
