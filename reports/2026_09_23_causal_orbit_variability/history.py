#!/usr/bin/env python3
"""Find the nearest prior causal snapshot pair with changed regional elements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from audit import (
    CAUSAL_LEAD_S,
    doppler_shapes,
    element_digests,
    quantiles,
    relative_rtn,
    representative_training_times,
    sha256,
    state_by_norad,
)

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

MAXIMUM_PREVIOUS_SNAPSHOTS = 24
MAXIMUM_HISTORY_S = 24 * 60 * 60


def catalogue_and_elements(archive, reference):
    text, _ = exclude_labelled_starlink_debris(archive.read(reference))
    return parse_element_sets(text), element_digests(text)


def comparison(archive, newer, older, norads, start_utc_ns, epochs):
    newer_catalogue, newer_elements = catalogue_and_elements(archive, newer)
    older_catalogue, older_elements = catalogue_and_elements(archive, older)
    changed = np.asarray(
        [
            number
            for number in norads
            if int(number) in newer_elements
            and int(number) in older_elements
            and newer_elements[int(number)] != older_elements[int(number)]
        ],
        dtype=np.int64,
    )
    same_elements = sum(
        int(number) in newer_elements
        and int(number) in older_elements
        and newer_elements[int(number)] == older_elements[int(number)]
        for number in norads
    )
    current_ids, current_p, current_v, missing_current = state_by_norad(
        newer_catalogue, norads, start_utc_ns, epochs
    )
    prior_ids, prior_p, prior_v, missing_prior = state_by_norad(
        older_catalogue, norads, start_utc_ns, epochs
    )
    common = np.intersect1d(current_ids, prior_ids)
    locations_current = {int(value): index for index, value in enumerate(current_ids)}
    locations_prior = {int(value): index for index, value in enumerate(prior_ids)}
    current_p = current_p[[locations_current[int(value)] for value in common]]
    current_v = current_v[[locations_current[int(value)] for value in common]]
    prior_p = prior_p[[locations_prior[int(value)] for value in common]]
    prior_v = prior_v[[locations_prior[int(value)] for value in common]]
    rtn = relative_rtn(current_p, current_v, prior_p)

    def values(mask):
        subset = rtn[mask]
        return {
            "matched_propagated_norads": int(np.sum(mask)),
            "relative_position_newer_minus_older_m": {
                "reference_frame": "newer ECEF radial-along-cross basis",
                "radial_absolute_m": quantiles(np.abs(subset[..., 0])),
                "along_absolute_m": quantiles(np.abs(subset[..., 1])),
                "cross_absolute_m": quantiles(np.abs(subset[..., 2])),
            },
            "doppler_shape_newer_minus_older": doppler_shapes(
                current_p[mask], current_v[mask], prior_p[mask], prior_v[mask]
            )
            if np.any(mask)
            else None,
        }

    changed_mask = np.isin(common, changed)
    return {
        "newer_snapshot": {
            "collected_utc_ns": newer.collected_utc_ns,
            "sha256": newer.sha256,
        },
        "older_snapshot": {
            "collected_utc_ns": older.collected_utc_ns,
            "sha256": older.sha256,
        },
        "newer_catalogue_count": len(newer_catalogue.names),
        "older_catalogue_count": len(older_catalogue.names),
        "missing_from_newer_snapshot": missing_current,
        "missing_from_older_snapshot": missing_prior,
        "changed_element_pair_count": int(len(changed)),
        "same_element_pair_count": same_elements,
        "all_cached_regional_norads": values(np.ones(len(common), dtype=bool)),
        "changed_element_subset": values(changed_mask),
    }


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output file required")
    cohort = json.loads(args.cohort_manifest.read_text())
    if args.session_id != cohort["partitions"]["train"]["session_ids"][0]:
        raise ValueError("only the first frozen TRAIN session is permitted")
    immediate = json.loads(args.immediate_results.read_text())
    cache = np.load(args.cache_receipt.with_name("state_cache.npz"), allow_pickle=False)
    norads = np.asarray(cache["candidate_id"], dtype=np.int64)
    if len(norads) != 880 or len(set(norads.tolist())) != len(norads):
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
    baseline = archive.select_latest_before(cutoff)
    if baseline.sha256 != immediate["causality"]["current_snapshot"]["sha256"]:
        raise ValueError("archive baseline differs from the preserved immediate-pair audit")
    if not baseline.collected_utc_ns < cutoff:
        raise ValueError("baseline snapshot is not causal")
    epochs = representative_training_times(prepared)
    older_refs = sorted(
        (
            item
            for item in archive.list_snapshots()
            if item.collected_utc_ns < baseline.collected_utc_ns
        ),
        key=lambda item: (item.collected_utc_ns, item.provider, item.sha256),
        reverse=True,
    )
    checked, newer, selected = [], baseline, None
    for ordinal, older in enumerate(older_refs[:MAXIMUM_PREVIOUS_SNAPSHOTS], start=1):
        age_s = (cutoff - older.collected_utc_ns) / 1e9
        if baseline.collected_utc_ns - older.collected_utc_ns > MAXIMUM_HISTORY_S * 1e9:
            break
        item = comparison(archive, newer, older, norads, prepared.start_utc_ns, epochs)
        item["pair_ordinal_backwards"] = ordinal
        item["older_age_at_cutoff_s"] = age_s
        item["newer_age_at_cutoff_s"] = (cutoff - newer.collected_utc_ns) / 1e9
        checked.append(item)
        if item["changed_element_pair_count"]:
            selected = item
            break
        newer = older
    result = {
        "schema": "causal-orbit-catalogue-history-variability/v1",
        "scope": {
            "session_id": args.session_id,
            "partition": "train",
            "position_fit_or_receiver_truth_used": False,
            "interpretation": "catalogue-update inconsistency proxy, not calibrated orbital error",
        },
        "causality": {
            "start_utc_ns": prepared.start_utc_ns,
            "cutoff_utc_ns": cutoff,
            "baseline_snapshot": {
                "collected_utc_ns": baseline.collected_utc_ns,
                "sha256": baseline.sha256,
            },
            "maximum_previous_snapshots": MAXIMUM_PREVIOUS_SNAPSHOTS,
            "maximum_history_s": MAXIMUM_HISTORY_S,
            "all_checked_snapshots_strictly_before_baseline_and_cutoff": True,
        },
        "representative_training_epochs": {
            "policy": "beginning, middle, end of sorted unique training rows",
            "offset_s": epochs.tolist(),
        },
        "checked_adjacent_snapshot_pairs": checked,
        "closest_changed_pair": selected,
        "limit_reached_without_changed_pair": selected is None,
        "bindings": {
            "history_helper": sha256(Path(__file__)),
            "immediate_results": sha256(args.immediate_results),
            "cohort_manifest": sha256(args.cohort_manifest),
            "cache_receipt": sha256(args.cache_receipt),
            "cache_state": sha256(args.cache_receipt.with_name("state_cache.npz")),
            "prepared_evidence": prepared.evidence_sha256,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        json.dumps(
            {"checked_pairs": len(checked), "found_changed_pair": selected is not None}, indent=2
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--cohort-manifest", type=Path, required=True)
    parser.add_argument("--cache-receipt", type=Path, required=True)
    parser.add_argument("--immediate-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    run(parser.parse_args())


if __name__ == "__main__":
    main()
