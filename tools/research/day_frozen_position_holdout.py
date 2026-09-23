#!/usr/bin/env python3
"""Strict new-day validation at five frozen receiver positions.

Full-catalogue identity, integer tau, and CFO are selected using randomized
training rows only.  A retention receipt is sealed before complementary
evaluation frequencies are scored.
"""

# ruff: noqa: E402 -- numerical thread limits precede NumPy imports.
from __future__ import annotations

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import (
    ReceiverPoint,
    RegionalTrackPredictionEvaluator,
    build_prediction_banks,
)
from leo.contracts.digests import canonical_digest
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

TAUS = np.arange(-5.0, 6.0)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x") as stream:
        stream.write(payload)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _site(latitude: float, longitude: float) -> ReceiverPoint:
    lat, lon = np.deg2rad([latitude, longitude])
    return ReceiverPoint(
        geodetic_to_ecef_km(latitude, longitude, 0),
        np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]),
    )


def training_rows(prediction, top_k: int) -> list[dict]:
    """Rank hypotheses without indexing or reducing any evaluation frequency."""
    training = np.asarray(prediction.training_mask, dtype=bool)
    residual = (
        np.asarray(prediction.measured_hz)[None, None, training]
        - np.asarray(prediction.predictions_hz)[..., training]
    )
    offset = np.mean(residual, axis=-1)
    mse = np.mean((residual - offset[..., None]) ** 2, axis=-1)
    visible = np.asarray(prediction.visible, dtype=bool)
    if visible.ndim == 1:
        visible = np.broadcast_to(visible[:, None], mse.shape)
    mse = np.where(visible, mse, np.inf)
    flat = np.argsort(mse, axis=None, kind="stable")[:top_k]
    rows = []
    for value in flat:
        candidate, tau = np.unravel_index(value, mse.shape)
        if not np.isfinite(mse[candidate, tau]):
            continue
        rows.append(
            {
                "candidate_id": str(prediction.candidate_ids[candidate]),
                "tau_s": float(prediction.taus_s[tau]),
                "offset_hz": float(offset[candidate, tau]),
                "training_rms_hz": float(np.sqrt(mse[candidate, tau])),
            }
        )
    return rows


def _merge_top(rows: list[dict], additions: list[dict], top_k: int) -> list[dict]:
    unique = {(row["candidate_id"], row["tau_s"]): row for row in rows}
    for row in additions:
        key = row["candidate_id"], row["tau_s"]
        old = unique.get(key)
        if old is None or row["training_rms_hz"] < old["training_rms_hz"]:
            unique[key] = row
    return sorted(
        unique.values(),
        key=lambda row: (row["training_rms_hz"], row["candidate_id"], row["tau_s"]),
    )[:top_k]


def _selection_digest(rows) -> str:
    compact = [
        {
            "location_id": row["location_id"],
            "track_id": row["track_id"],
            "hypotheses": row["hypotheses"],
        }
        for row in rows
    ]
    return canonical_digest(compact)


def _invariance_test() -> bool:
    from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction

    rng = np.random.default_rng(9023)
    mask = np.array([1, 0, 1, 0, 1, 1, 0, 0], dtype=bool)
    measured = rng.normal(size=8)
    prediction = rng.normal(size=(4, 11, 8))

    def rank(y):
        item = AdaptiveTrackPrediction(
            "t",
            tuple(f"o{i}" for i in range(8)),
            np.arange(8.0),
            y,
            mask,
            np.arange(4).astype(str),
            TAUS,
            prediction,
            np.ones(4, dtype=bool),
        )
        return canonical_digest(training_rows(item, 5))

    changed = measured.copy()
    changed[~mask] = rng.normal(1e9, 1e8, np.sum(~mask))
    return rank(measured) == rank(changed)


def run(args) -> None:
    if args.output.exists():
        raise ValueError("fresh output directory required")
    if not _invariance_test():
        raise AssertionError("training retention changed with evaluation frequencies")
    inventory = json.loads(args.inventory.read_text())
    frozen_document = json.loads(args.locations.read_text())
    frozen = frozen_document["locations"] if isinstance(frozen_document, dict) else frozen_document
    requested = args.sessions or (
        frozen_document.get("session_ids", inventory["eligible_session_ids"][: args.scan_limit])
        if isinstance(frozen_document, dict)
        else inventory["eligible_session_ids"][: args.scan_limit]
    )
    if (
        isinstance(frozen_document, dict)
        and frozen_document.get("inventory_sha256")
        and _digest(args.inventory).removeprefix("sha256:") != frozen_document["inventory_sha256"]
    ):
        raise ValueError("frozen protocol inventory digest mismatch")
    inventory_rows = {row["session_id"]: row for row in inventory["scans"]}
    started = time.monotonic()
    args.output.mkdir(parents=True)
    session_results = []
    for session_id in requested:
        session_started = time.monotonic()
        if session_started - started > args.budget_seconds:
            raise TimeoutError("heldout validation budget exhausted before next scan")
        store = ScannerTrackingInputStore(args.bulk_root)
        try:
            prepared = prepare_adaptive_tle_position_inputs(
                session_id, inputs=store, archive=TleArchiveReader(args.tle_root)
            )
        finally:
            store.close()
        authority = inventory_rows[session_id]
        evidence_digest = hashlib.sha256(
            json.dumps(
                list(prepared.track_evidence), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if (
            authority["state"] != "eligible"
            or authority["tracks"] != len(prepared.tracks)
            or authority["observations"] != prepared.eligible_observation_count
            or authority["evidence_digest"] != evidence_digest
            or authority["input_manifest_sha256"] != prepared.input_manifest_sha256
            or authority["analysis_manifest_sha256"] != prepared.analysis_manifest_sha256
        ):
            raise ValueError("prepared evidence differs from frozen inventory authority")
        retained_map = {
            (location["location_id"], track.track_id): []
            for location in frozen
            for track in prepared.tracks
        }
        bank_receipts = []
        # Chunk propagation itself, not merely scoring, to enforce the RSS bound.
        for begin in range(0, len(prepared.candidate_indices), args.candidate_block):
            candidate_indices = prepared.candidate_indices[begin : begin + args.candidate_block]
            banks, bank_receipt = build_prediction_banks(
                prepared.catalogue,
                candidate_indices,
                prepared.start_utc_ns,
                prepared.tracks,
                taus_s=TAUS,
            )
            bank_receipts.append(bank_receipt.__dict__)
            if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > args.max_rss_kib:
                raise MemoryError("heldout validator exceeded RSS limit")
            for location in frozen:
                site = _site(location["latitude_deg"], location["longitude_deg"])
                evaluator = RegionalTrackPredictionEvaluator(
                    banks,
                    lambda _east, _north, value=site: value,
                    taus_s=TAUS,
                    candidate_block=args.candidate_block,
                )
                for prediction in evaluator(0.0, 0.0):
                    key = location["location_id"], prediction.track_id
                    retained_map[key] = _merge_top(
                        retained_map[key], training_rows(prediction, args.top_k), args.top_k
                    )
            del banks
            if time.monotonic() - started > args.budget_seconds:
                raise TimeoutError("heldout validation budget exhausted in catalogue training")
        retained = [
            {
                "location_id": location["location_id"],
                "track_id": track.track_id,
                "training_mask_digest": canonical_digest(track.training_mask.tolist()),
                "hypotheses": retained_map[(location["location_id"], track.track_id)],
            }
            for location in frozen
            for track in prepared.tracks
        ]
        receipt = {
            "schema": "day-frozen-position-training-retention/v1",
            "session_id": session_id,
            "evidence_sha256": prepared.evidence_sha256,
            "snapshot_digest": prepared.snapshot_digest,
            "full_candidate_count": len(prepared.candidate_indices),
            "propagation_failure_count": len(prepared.candidate_indices)
            - sum(row["candidate_count"] for row in bank_receipts),
            "track_count": len(prepared.tracks),
            "observation_count": prepared.eligible_observation_count,
            "locations_digest": _digest(args.locations),
            "tau_s": TAUS.tolist(),
            "top_k_per_location_track": args.top_k,
            "evaluation_frequency_loaded_but_used_for_selection": False,
            "selection_digest": _selection_digest(retained),
            "rows": retained,
        }
        receipt_path = args.output / "retention" / f"{session_id}.json"
        _write(receipt_path, receipt)
        # Evaluation phase begins only after the immutable training receipt exists.
        evaluation = []
        retained_lookup = {
            (row["location_id"], row["track_id"]): row["hypotheses"][0]
            for row in retained
            if row["hypotheses"]
        }
        number_to_index = {
            str(prepared.catalogue.satellite_numbers[index]): int(index)
            for index in prepared.candidate_indices
        }
        selected_indices = sorted(
            {
                number_to_index[row["candidate_id"]]
                for row in retained_lookup.values()
                if row is not None
            }
        )
        banks, evaluation_bank_receipt = build_prediction_banks(
            prepared.catalogue,
            selected_indices,
            prepared.start_utc_ns,
            prepared.tracks,
            taus_s=TAUS,
        )
        for location in frozen:
            site = _site(location["latitude_deg"], location["longitude_deg"])
            evaluator = RegionalTrackPredictionEvaluator(
                banks,
                lambda _east, _north, value=site: value,
                taus_s=TAUS,
                candidate_block=args.candidate_block,
            )
            pending = {
                track.track_id: retained_lookup.get((location["location_id"], track.track_id))
                for track in prepared.tracks
            }
            for prediction in evaluator(0.0, 0.0):
                choice = pending[prediction.track_id]
                if choice is None or choice.get("evaluation_rms_hz") is not None:
                    continue
                candidates = np.flatnonzero(
                    np.asarray(prediction.candidate_ids).astype(str) == choice["candidate_id"]
                )
                if not len(candidates):
                    continue
                tau = int(np.flatnonzero(prediction.taus_s == choice["tau_s"])[0])
                mask = ~np.asarray(prediction.training_mask, dtype=bool)
                residual = (
                    np.asarray(prediction.measured_hz)[mask]
                    - prediction.predictions_hz[int(candidates[0]), tau, mask]
                    - choice["offset_hz"]
                )
                choice["evaluation_rms_hz"] = float(np.sqrt(np.mean(residual**2)))
            for track in prepared.tracks:
                choice = pending[track.track_id]
                evaluation.append(
                    {
                        "location_id": location["location_id"],
                        "track_id": track.track_id,
                        "weight_s": int(len(np.unique(np.floor(track.times_s).astype(int)))),
                        **({"matched": False} if choice is None else {"matched": True, **choice}),
                    }
                )
        session_results.append(
            {
                "session_id": session_id,
                "retention_digest": _digest(receipt_path),
                "training_bank_receipts": bank_receipts,
                "evaluation_bank_receipt": evaluation_bank_receipt.__dict__,
                "evaluation": evaluation,
                "runtime_s": time.monotonic() - session_started,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        )
        print(
            json.dumps({"session": session_id, "runtime_s": session_results[-1]["runtime_s"]}),
            flush=True,
        )
        del banks
    result = {
        "schema": "day-frozen-position-holdout/v1",
        "complete": True,
        "locations_digest": _digest(args.locations),
        "inventory_digest": _digest(args.inventory),
        "protocol_digest": _digest(args.locations),
        "training_decision_invariance_test": True,
        "full_catalogue_training_selection": True,
        "tau_step_s": 1.0,
        "sessions": session_results,
        "runtime_s": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    _write(args.output / "results.json", result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sessions", nargs="*")
    parser.add_argument("--scan-limit", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--candidate-block", type=int, default=256)
    parser.add_argument("--budget-seconds", type=float, default=900)
    parser.add_argument("--max-rss-kib", type=int, default=2_000_000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
