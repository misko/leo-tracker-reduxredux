#!/usr/bin/env python3
"""Compare two strictly causal catalogue snapshots for the first long TRAIN scan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.catalogue_prediction import element_pair_digest
from leo.cli.adaptive_tle_position import PRIORS
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import parse_element_set_records, parse_element_sets
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

CAUSAL_LEAD_S = 505
REFERENCE_RF_HZ = 11_200_000_000.0


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def quantiles(values: np.ndarray) -> dict[str, float | None]:
    finite = np.asarray(values, dtype=float)[np.isfinite(values)]
    if not len(finite):
        return {key: None for key in ("p50", "p90", "p99", "max")}
    return {
        "p50": float(np.quantile(finite, 0.50)),
        "p90": float(np.quantile(finite, 0.90)),
        "p99": float(np.quantile(finite, 0.99)),
        "max": float(np.max(finite)),
    }


def element_digests(snapshot_text: str) -> dict[int, str]:
    return {
        record.satellite_number: element_pair_digest(record.first_line, record.second_line)
        for record in parse_element_set_records(snapshot_text)
    }


def representative_training_times(prepared) -> np.ndarray:
    values = sorted(
        {
            float(time)
            for track in prepared.tracks
            for time, training in zip(track.times_s, track.training_mask, strict=True)
            if training
        }
    )
    if len(values) < 3:
        raise ValueError("three representative TRAIN epochs are required")
    return np.asarray([values[0], values[len(values) // 2], values[-1]], dtype=float)


def state_by_norad(catalogue, norads: np.ndarray, start_utc_ns: int, times_s: np.ndarray):
    index = {int(number): position for position, number in enumerate(catalogue.satellite_numbers)}
    present = np.asarray([int(number) in index for number in norads], dtype=bool)
    selected = np.asarray([index[int(number)] for number in norads[present]], dtype=int)
    position, velocity, valid = propagate_candidate_states(
        catalogue, selected, start_utc_ns, times_s, np.asarray([0.0])
    )
    # propagate_candidate_states filters failed rows; return the NORADs that survived too.
    return (
        np.asarray(catalogue.satellite_numbers, dtype=np.int64)[valid],
        position[:, 0],
        velocity[:, 0],
        int(np.sum(~present)),
    )


def relative_rtn(current_position, current_velocity, prior_position) -> np.ndarray:
    delta_m = (current_position - prior_position) * 1000.0
    radial = current_position / np.linalg.norm(current_position, axis=-1, keepdims=True)
    cross = np.cross(current_position, current_velocity)
    cross /= np.linalg.norm(cross, axis=-1, keepdims=True)
    along = np.cross(cross, radial)
    return np.stack(
        (
            np.sum(delta_m * radial, axis=-1),
            np.sum(delta_m * along, axis=-1),
            np.sum(delta_m * cross, axis=-1),
        ),
        axis=-1,
    )


def doppler_shapes(current_position, current_velocity, prior_position, prior_velocity):
    result = {}
    for name, (latitude, longitude, _radius) in PRIORS.items():
        receiver = geodetic_to_ecef_km(latitude, longitude, 0)

        def shift(position, velocity, receiver=receiver):
            line = position - receiver
            rate = np.sum(velocity * line, axis=-1) / np.linalg.norm(line, axis=-1)
            return doppler_shift_hz(REFERENCE_RF_HZ, rate)

        difference = shift(current_position, current_velocity) - shift(
            prior_position, prior_velocity
        )
        residual = difference - np.mean(difference, axis=1, keepdims=True)
        per_norad_rms = np.sqrt(np.mean(residual**2, axis=1))
        result[name] = {
            "constant_cfo_removed_per_norad": True,
            "shape_difference_rms_hz": quantiles(per_norad_rms),
            "absolute_shape_difference_hz": quantiles(np.abs(residual)),
        }
    return result


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output file required")
    cohort = json.loads(args.cohort_manifest.read_text())
    first_train = cohort["partitions"]["train"]["session_ids"][0]
    if args.session_id != first_train:
        raise ValueError("only the first frozen TRAIN session is permitted")
    cache_receipt = json.loads(args.cache_receipt.read_text())
    if cache_receipt["session_id"] != args.session_id:
        raise ValueError("cache receipt does not bind the requested TRAIN session")
    cache = np.load(args.cache_receipt.with_name("state_cache.npz"), allow_pickle=False)
    regional_norads = np.asarray(cache["candidate_id"], dtype=np.int64)
    if len(regional_norads) != 880 or len(set(regional_norads.tolist())) != len(regional_norads):
        raise ValueError("expected exactly 880 unique cached regional NORADs")

    archive = TleArchiveReader(args.tle_root)
    store = ScannerTrackingInputStore(args.bulk_root)
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            args.session_id, inputs=store, archive=archive
        )
    finally:
        store.close()
    cutoff = prepared.start_utc_ns - CAUSAL_LEAD_S * 1_000_000_000
    current_ref = archive.select_latest_before(cutoff)
    prior_ref = archive.select_latest_before(current_ref.collected_utc_ns)
    if not prior_ref.collected_utc_ns < current_ref.collected_utc_ns < cutoff:
        raise ValueError("snapshot selection is not strictly causal and ordered")
    current_text, _ = exclude_labelled_starlink_debris(archive.read(current_ref))
    prior_text, _ = exclude_labelled_starlink_debris(archive.read(prior_ref))
    current_catalogue = parse_element_sets(current_text)
    prior_catalogue = parse_element_sets(prior_text)
    epochs = representative_training_times(prepared)
    current_ids, current_p, current_v, missing_current = state_by_norad(
        current_catalogue, regional_norads, prepared.start_utc_ns, epochs
    )
    prior_ids, prior_p, prior_v, missing_prior = state_by_norad(
        prior_catalogue, regional_norads, prepared.start_utc_ns, epochs
    )
    common = np.intersect1d(current_ids, prior_ids)
    if not len(common):
        raise ValueError("no cached regional NORAD survives in both snapshots")

    def align(ids, values):
        rows = {int(value): position for position, value in enumerate(ids)}
        return values[[rows[int(value)] for value in common]]

    current_p, current_v = align(current_ids, current_p), align(current_ids, current_v)
    prior_p, prior_v = align(prior_ids, prior_p), align(prior_ids, prior_v)
    rtn = relative_rtn(current_p, current_v, prior_p)
    current_elements = element_digests(current_text)
    prior_elements = element_digests(prior_text)
    same_elements = sum(
        current_elements[int(value)] == prior_elements[int(value)] for value in common
    )
    result = {
        "schema": "causal-orbit-catalogue-variability/v1",
        "scope": {
            "session_id": args.session_id,
            "partition": "train",
            "position_fit_or_receiver_truth_used": False,
            "interpretation": "catalogue-update inconsistency proxy, not calibrated orbital error",
        },
        "causality": {
            "start_utc_ns": prepared.start_utc_ns,
            "cutoff_utc_ns": cutoff,
            "lead_before_start_s": CAUSAL_LEAD_S,
            "current_snapshot": {
                "collected_utc_ns": current_ref.collected_utc_ns,
                "sha256": current_ref.sha256,
                "age_at_cutoff_s": (cutoff - current_ref.collected_utc_ns) / 1e9,
            },
            "preceding_snapshot": {
                "collected_utc_ns": prior_ref.collected_utc_ns,
                "sha256": prior_ref.sha256,
                "age_at_cutoff_s": (cutoff - prior_ref.collected_utc_ns) / 1e9,
            },
            "both_strictly_before_cutoff": True,
        },
        "representative_training_epochs": {
            "policy": "beginning, middle, end of sorted unique training rows",
            "offset_s": epochs.tolist(),
            "utc_ns": [int(prepared.start_utc_ns + round(value * 1e9)) for value in epochs],
        },
        "candidate_accounting": {
            "cached_regional_norads": len(regional_norads),
            "current_snapshot_catalogue_count": len(current_catalogue.names),
            "preceding_snapshot_catalogue_count": len(prior_catalogue.names),
            "missing_from_current_snapshot": missing_current,
            "missing_from_preceding_snapshot": missing_prior,
            "propagation_surviving_current": len(current_ids),
            "propagation_surviving_preceding": len(prior_ids),
            "matched_propagated_norads": len(common),
            "same_element_pair_count": same_elements,
            "changed_element_pair_count": len(common) - same_elements,
        },
        "relative_position_current_minus_preceding_m": {
            "reference_frame": "current ECEF radial-along-cross basis at each epoch",
            "radial_signed_m": quantiles(rtn[..., 0]),
            "along_signed_m": quantiles(rtn[..., 1]),
            "cross_signed_m": quantiles(rtn[..., 2]),
            "radial_absolute_m": quantiles(np.abs(rtn[..., 0])),
            "along_absolute_m": quantiles(np.abs(rtn[..., 1])),
            "cross_absolute_m": quantiles(np.abs(rtn[..., 2])),
        },
        "doppler_shape_current_minus_preceding": doppler_shapes(
            current_p, current_v, prior_p, prior_v
        ),
        "bindings": {
            "audit_helper": sha256(Path(__file__)),
            "cohort_manifest": sha256(args.cohort_manifest),
            "cache_receipt": sha256(args.cache_receipt),
            "cache_state": sha256(args.cache_receipt.with_name("state_cache.npz")),
            "prepared_evidence": prepared.evidence_sha256,
            "prepared_snapshot": prepared.snapshot_digest,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result["candidate_accounting"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--cohort-manifest", type=Path, required=True)
    parser.add_argument("--cache-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    run(parser.parse_args())


if __name__ == "__main__":
    main()
