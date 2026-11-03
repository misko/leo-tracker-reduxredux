#!/usr/bin/env python3
"""Metadata-only diagnostic for edge candidates near zero-residual proposals."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

import candidate_prevalence_diagnostic as prevalence
from finite_set_fit import GroupMedianGeometryData, build_likelihood_arms
from finite_set_fixed_position import _evaluate_state
from finite_set_likelihood import DEFAULT_ALIAS_HZ, circular_residual
from rough_smoke import load_module, serializable
from selection import ROOT


DEFAULT_RUN_ID = "edge-alias-diagnostic-v1"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
FRAME_RATE_HZ = 750.0
FREQUENCY_THRESHOLDS_HZ = (1e-6, 1.0, 10.0, 50.0, 100.0, 200.0, 443.0, 1000.0)
EPOCH_THRESHOLDS_SAMPLES = (1e-6, 0.01, 0.1, 0.25, 0.5, 1.0, 10.0, 100.0)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _circular_distance(left, right, period):
    return abs(float((left - right + 0.5 * period) % period - 0.5 * period))


def _quantiles(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return {"count": 0}
    points = (0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0)
    result = np.quantile(values, points)
    return {
        "count": len(values),
        **{f"q{int(point * 100):02d}": float(value) for point, value in zip(points, result, strict=True)},
    }


def nearest_zero_pairs(rows, *, alias_hz=DEFAULT_ALIAS_HZ, frame_period_samples):
    """Pair each edge row to its nearest zero row in the same physical probe."""

    if not math.isfinite(alias_hz) or alias_hz <= 0:
        raise ValueError("alias_hz must be positive and finite")
    if not math.isfinite(frame_period_samples) or frame_period_samples <= 0:
        raise ValueError("frame_period_samples must be positive and finite")
    by_probe = defaultdict(list)
    for index, row in enumerate(rows):
        by_probe[tuple(row["probe_key"])].append(index)
    pairs = []
    no_zero = []
    tied_nearest = []
    for edge_index, edge in enumerate(rows):
        if edge["residual_class"] != "edge":
            continue
        zero_indices = [
            index
            for index in by_probe[tuple(edge["probe_key"])]
            if rows[index]["residual_class"] == "zero"
        ]
        if not zero_indices:
            no_zero.append(edge_index)
            continue
        candidates = []
        for zero_index in zero_indices:
            zero = rows[zero_index]
            final_difference = abs(
                float(
                    circular_residual(
                        edge["tracking_cfo_hz"],
                        zero["tracking_cfo_hz"],
                        alias_hz,
                    )
                )
            )
            acquired_difference = abs(
                float(
                    circular_residual(
                        edge["acquired_cfo_hz"],
                        zero["acquired_cfo_hz"],
                        alias_hz,
                    )
                )
            )
            half_alias_error = abs(0.5 * alias_hz - acquired_difference)
            epoch_difference = _circular_distance(
                edge["fractional_epoch_samples"],
                zero["fractional_epoch_samples"],
                frame_period_samples,
            )
            candidates.append(
                {
                    "edge_row": edge_index,
                    "zero_row": zero_index,
                    "final_circular_frequency_difference_hz": final_difference,
                    "acquired_half_alias_error_hz": half_alias_error,
                    "frame_epoch_difference_samples": epoch_difference,
                }
            )
        best_frequency = min(item["final_circular_frequency_difference_hz"] for item in candidates)
        tied = [
            item
            for item in candidates
            if math.isclose(
                item["final_circular_frequency_difference_hz"],
                best_frequency,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ]
        pair = {
            **tied[0],
            "zero_rows": [item["zero_row"] for item in tied],
            "nearest_zero_tie_count": len(tied),
        }
        pair.pop("zero_row")
        pairs.append(pair)
        if len(tied) > 1:
            tied_nearest.append(
                {
                    "edge_row": edge_index,
                    "zero_rows": pair["zero_rows"],
                    "frequency_difference_hz": best_frequency,
                }
            )
    return {
        "pairs": pairs,
        "no_zero_edge_rows": no_zero,
        "tied_nearest_zero_families": tied_nearest,
        "edge_row_count": sum(row["residual_class"] == "edge" for row in rows),
    }


def _support_summary(pairs, row_catalog_mass, catalog_numbers, total_signal_mass):
    row_catalog_mass = np.asarray(row_catalog_mass, dtype=float)
    catalog_numbers = np.asarray(catalog_numbers, dtype=int)
    if row_catalog_mass.ndim != 2 or row_catalog_mass.shape[1] != len(catalog_numbers):
        raise ValueError("row catalog mass shape differs from catalog numbers")
    edge_rows = np.asarray([pair["edge_row"] for pair in pairs], dtype=int)
    zero_row_families = [np.asarray(pair["zero_rows"], dtype=int) for pair in pairs]
    if not len(pairs):
        return {
            "pair_count": 0,
            "distinct_zero_row_count": 0,
            "edge_signal_mass": 0.0,
            "edge_signal_mass_prevalence": 0.0,
            "paired_zero_signal_mass_with_reuse": 0.0,
            "posterior_catalog_overlap_mass": 0.0,
            "same_dominant_catalog_pair_count": 0,
            "catalog_contributions": [],
        }
    edge_mass = row_catalog_mass[edge_rows]
    zero_mass = np.stack(
        [np.sum(row_catalog_mass[family], axis=0) for family in zero_row_families]
    )
    edge_signal = float(np.sum(edge_mass))
    zero_signal = float(np.sum(zero_mass))
    overlap = float(np.sum(np.minimum(edge_mass, zero_mass)))
    edge_top = np.argmax(edge_mass, axis=1)
    zero_top = np.argmax(zero_mass, axis=1)
    edge_support = np.sum(edge_mass, axis=0)
    zero_support = np.sum(zero_mass, axis=0)
    return {
        "pair_count": len(pairs),
        "distinct_zero_row_count": len(
            {int(row) for family in zero_row_families for row in family}
        ),
        "tied_zero_family_count": sum(len(family) > 1 for family in zero_row_families),
        "edge_signal_mass": edge_signal,
        "edge_signal_mass_prevalence": edge_signal / total_signal_mass if total_signal_mass else 0.0,
        "paired_zero_signal_mass_with_reuse": zero_signal,
        "posterior_catalog_overlap_mass": overlap,
        "posterior_overlap_fraction_of_edge_mass": overlap / edge_signal if edge_signal else 0.0,
        "posterior_overlap_fraction_of_smaller_pair_mass": (
            overlap / min(edge_signal, zero_signal) if min(edge_signal, zero_signal) else 0.0
        ),
        "same_dominant_catalog_pair_count": int(np.sum(edge_top == zero_top)),
        "same_dominant_catalog_fraction": float(np.mean(edge_top == zero_top)),
        "catalog_contributions": [
            {
                "catalog_number": int(number),
                "edge_signal_mass": float(edge_value),
                "paired_zero_signal_mass_with_reuse": float(zero_value),
                "overlap_mass": float(minimum),
            }
            for number, edge_value, zero_value, minimum in zip(
                catalog_numbers,
                edge_support,
                zero_support,
                np.sum(np.minimum(edge_mass, zero_mass), axis=0),
                strict=True,
            )
        ],
    }


def _compact_support_summary(pairs, row_catalog_mass, total_signal_mass):
    row_catalog_mass = np.asarray(row_catalog_mass, dtype=float)
    if not pairs:
        return {
            "pair_count": 0,
            "distinct_zero_row_count": 0,
            "edge_signal_mass": 0.0,
            "edge_signal_mass_prevalence": 0.0,
            "posterior_catalog_overlap_mass": 0.0,
            "same_dominant_catalog_pair_count": 0,
        }
    edge_rows = np.asarray([pair["edge_row"] for pair in pairs], dtype=int)
    zero_row_families = [np.asarray(pair["zero_rows"], dtype=int) for pair in pairs]
    edge_mass = row_catalog_mass[edge_rows]
    zero_mass = np.stack(
        [np.sum(row_catalog_mass[family], axis=0) for family in zero_row_families]
    )
    edge_signal = float(np.sum(edge_mass))
    overlap = float(np.sum(np.minimum(edge_mass, zero_mass)))
    same_dominant = np.argmax(edge_mass, axis=1) == np.argmax(zero_mass, axis=1)
    return {
        "pair_count": len(pairs),
        "distinct_zero_row_count": len(
            {int(row) for family in zero_row_families for row in family}
        ),
        "tied_zero_family_count": sum(len(family) > 1 for family in zero_row_families),
        "edge_signal_mass": edge_signal,
        "edge_signal_mass_prevalence": edge_signal / total_signal_mass if total_signal_mass else 0.0,
        "posterior_catalog_overlap_mass": overlap,
        "posterior_overlap_fraction_of_edge_mass": overlap / edge_signal if edge_signal else 0.0,
        "same_dominant_catalog_pair_count": int(np.sum(same_dominant)),
        "same_dominant_catalog_fraction": float(np.mean(same_dominant)),
    }


def summarize_pairs(pairing, row_catalog_mass, catalog_numbers, *, total_signal_mass, sample_rate_hz):
    pairs = pairing["pairs"]
    final = [pair["final_circular_frequency_difference_hz"] for pair in pairs]
    half_alias = [pair["acquired_half_alias_error_hz"] for pair in pairs]
    epoch = [pair["frame_epoch_difference_samples"] for pair in pairs]
    thresholds = []
    for threshold in FREQUENCY_THRESHOLDS_HZ:
        selected = [
            pair
            for pair in pairs
            if pair["final_circular_frequency_difference_hz"] <= threshold
        ]
        entry = {
            "final_frequency_threshold_hz": threshold,
            **_support_summary(selected, row_catalog_mass, catalog_numbers, total_signal_mass),
            "acquired_half_alias_error_hz": _quantiles(
                [pair["acquired_half_alias_error_hz"] for pair in selected]
            ),
            "frame_epoch_difference_samples": _quantiles(
                [pair["frame_epoch_difference_samples"] for pair in selected]
            ),
            "frame_epoch_difference_us": _quantiles(
                [1e6 * pair["frame_epoch_difference_samples"] / sample_rate_hz for pair in selected]
            ),
            "epoch_threshold_counts": {
                str(value): sum(
                    pair["frame_epoch_difference_samples"] <= value for pair in selected
                )
                for value in EPOCH_THRESHOLDS_SAMPLES
            },
            "joint_epoch_thresholds": [
                {
                    "frame_epoch_threshold_samples": epoch_threshold,
                    **_compact_support_summary(
                        [
                            pair
                            for pair in selected
                            if pair["frame_epoch_difference_samples"] <= epoch_threshold
                        ],
                        row_catalog_mass,
                        total_signal_mass,
                    ),
                }
                for epoch_threshold in EPOCH_THRESHOLDS_SAMPLES
            ],
        }
        thresholds.append(entry)
    return {
        "pair_count": len(pairs),
        "paired_edge_row_count": len(pairs),
        "final_circular_frequency_difference_hz": _quantiles(final),
        "acquired_half_alias_error_hz": _quantiles(half_alias),
        "frame_epoch_difference_samples": _quantiles(epoch),
        "frame_epoch_difference_us": _quantiles(
            [1e6 * value / sample_rate_hz for value in epoch]
        ),
        "acquired_half_alias_threshold_counts": {
            str(value): sum(item <= value for item in half_alias)
            for value in FREQUENCY_THRESHOLDS_HZ
        },
        "final_frequency_thresholds": thresholds,
    }


def _metadata(root, session_id, expected_input, expected_analysis):
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.contracts.digests import canonical_digest as leo_canonical_digest
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    tracking_store = ScannerTrackingInputStore(root)
    try:
        source = tracking_store.load(session_id)
    finally:
        tracking_store.close()
    if source.input_manifest_sha256 != expected_input or source.analysis_manifest_sha256 != expected_analysis:
        raise ValueError("tracking source differs from frozen bundle")
    projected = project_scanner_candidates(source)
    iq_store = AdaptiveHopIqStore(root, read_only=True)
    published = iq_store.inspect(session_id)
    if published.manifest_sha256 != expected_input:
        iq_store.close()
        raise ValueError("IQ metadata manifest differs from frozen bundle")
    binding = bind_actual_visit_analysis(
        published.manifest.receipt,
        input_manifest_sha256=published.manifest_sha256,
        probe_stride_ms=120,
    )
    analysis_store = AdaptiveHopAnalysisStore(root, read_only=True)
    metadata = []
    try:
        with analysis_store.job(binding) as job:
            manifest = job.manifest()
            if manifest is None or leo_canonical_digest(manifest.model_dump(mode="json")) != expected_analysis:
                raise ValueError("analysis metadata differs from frozen bundle")
            sample_rate_hz = int(manifest.configuration.sample_rate_hz)
            for product in job.published_visits():
                for probe in product.probes:
                    for candidate in probe.candidates:
                        if not candidate.passed_fractional_margin_gate:
                            continue
                        label, native_bin, canonical = prevalence.classify_residual(
                            candidate.fractional_residual_cfo_hz
                        )
                        metadata.append(
                            {
                                "key": [
                                    int(product.visit_index),
                                    int(probe.receiver_id),
                                    int(probe.probe_index),
                                    int(candidate.candidate_rank),
                                ],
                                "probe_key": [
                                    int(product.visit_index),
                                    int(probe.receiver_id),
                                    int(probe.probe_index),
                                ],
                                "candidate_rank": int(candidate.candidate_rank),
                                "integer_epoch_sample": int(candidate.integer_epoch_sample),
                                "integer_session_sample": int(candidate.integer_session_sample),
                                "fractional_epoch_offset_samples": float(
                                    candidate.fractional_epoch_offset_samples
                                ),
                                "acquired_cfo_hz": float(candidate.acquired_cfo_hz),
                                "native_residual_cfo_hz": float(candidate.fractional_residual_cfo_hz),
                                "canonical_residual_cfo_hz": canonical,
                                "native_residual_bin": native_bin,
                                "tracking_cfo_hz": float(candidate.fractional_tracking_cfo_hz),
                                "fractional_epoch_samples": float(
                                    candidate.integer_epoch_sample
                                    + candidate.fractional_epoch_offset_samples
                                ),
                                "fractional_margin": float(candidate.fractional_margin),
                                "residual_class": label,
                                "candidate_spec": candidate.model_dump(mode="json"),
                            }
                        )
    finally:
        analysis_store.close()
        iq_store.close()
    keys = [
        [point.visit_index, point.receiver_id, point.probe_index, point.candidate_rank]
        for point in projected
    ]
    joined, accounting = prevalence.join_projected_metadata(keys, metadata)
    return source, projected, joined, accounting, sample_rate_hz


def run_case(unit_id, *, bulk_root=DEFAULT_BULK_ROOT):
    dataset, session_id, expected_k = prevalence.UNITS[unit_id]
    fit_path = ROOT / "runs" / prevalence.SOURCE_RUN_ID / unit_id / "fit.json"
    bundle_dir = ROOT / "scans" / session_id
    bundle_json = bundle_dir / "bundle.json"
    bundle_npz = bundle_dir / "bundle.npz"
    source_fit = json.loads(fit_path.read_text())
    manifest = json.loads(bundle_json.read_text())
    if source_fit.get("reference_read_before_seal") is not False or source_fit.get("evaluation_written") is not False:
        raise ValueError("finite-set source is not a sealed truth-free fit")
    leader = source_fit["fit"]["finite_set_selection"]["score_leader"]
    satellites = np.asarray(leader["satellite_indices"], dtype=int)
    if len(satellites) != expected_k:
        raise ValueError("sealed finite-set leader cardinality changed")
    bundle = load_module(
        f"edge_alias_bundle_{unit_id}",
        ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py",
    )
    data = bundle.Data(bundle_dir)
    _, projected, joined, join, sample_rate_hz = _metadata(
        Path(bulk_root),
        session_id,
        manifest["provenance"]["input_manifest_sha256"],
        manifest["provenance"]["persisted_analysis_manifest_sha256"],
    )
    row_binding = prevalence._verify_bundle_rows(data, manifest, projected)
    if any(row is None for row in joined):
        raise ValueError("exact metadata join is incomplete; no edge pairs were forced")
    frame_period_samples = sample_rate_hz / FRAME_RATE_HZ
    geometry = GroupMedianGeometryData(data)
    likelihood = build_likelihood_arms(
        geometry, len(satellites), len(source_fit["fit"]["full_bank"])
    )["finite_set"]
    state = _evaluate_state(
        geometry,
        np.asarray(leader["parameters"], dtype=float),
        satellites,
        likelihood,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
    )
    if not np.isclose(state["objective"], leader["objective"], rtol=0, atol=1e-6):
        raise ValueError("sealed finite-set objective does not reproduce")
    result = state["result"]
    row_catalog_mass = np.asarray(result["row_association_probability"], dtype=float)
    catalog_numbers = np.asarray(data.numbers)[satellites]
    total_signal_mass = float(np.sum(row_catalog_mass))
    pairing = nearest_zero_pairs(
        joined,
        alias_hz=DEFAULT_ALIAS_HZ,
        frame_period_samples=frame_period_samples,
    )
    pair_lineage = []
    for pair in pairing["pairs"]:
        edge_row = pair["edge_row"]
        zero_rows = pair["zero_rows"]
        zero_unique_peaks = sorted(
            {int(result["original_to_unique"][zero_row]) for zero_row in zero_rows}
        )
        zero_epochs = [joined[zero_row]["fractional_epoch_samples"] for zero_row in zero_rows]
        pair_lineage.append(
            {
                **pair,
                "edge_candidate_id": projected[edge_row].candidate_id,
                "zero_candidate_ids": [projected[zero_row].candidate_id for zero_row in zero_rows],
                "edge_unique_peak": int(result["original_to_unique"][edge_row]),
                "zero_unique_peaks": zero_unique_peaks,
                "zero_family_within_one_existing_cluster": len(zero_unique_peaks) == 1,
                "zero_family_epoch_spread_samples": max(zero_epochs) - min(zero_epochs),
                "edge": joined[edge_row],
                "nearest_zero_family": [joined[zero_row] for zero_row in zero_rows],
            }
        )
    cross_cluster_ties = [
        item
        for item in pair_lineage
        if item["nearest_zero_tie_count"] > 1
        and not item["zero_family_within_one_existing_cluster"]
    ]
    usable_pairs = [
        pair
        for pair, lineage in zip(pairing["pairs"], pair_lineage, strict=True)
        if lineage["zero_family_within_one_existing_cluster"]
    ]
    summary = summarize_pairs(
        {"pairs": usable_pairs},
        row_catalog_mass,
        catalog_numbers,
        total_signal_mass=total_signal_mass,
        sample_rate_hz=sample_rate_hz,
    )
    edge_rows = [index for index, row in enumerate(joined) if row["residual_class"] == "edge"]
    no_zero_mass = float(np.sum(row_catalog_mass[pairing["no_zero_edge_rows"]]))
    source_paths = [
        Path(__file__),
        Path(prevalence.__file__),
        fit_path,
        bundle_json,
        bundle_npz,
        Path(sys.modules["finite_set_likelihood"].__file__),
        Path(sys.modules["finite_set_fit"].__file__),
    ]
    return {
        "schema": "edge-zero-alias-offspring-diagnostic/v2",
        "created_utc": datetime.now(UTC).isoformat(),
        "unit_id": unit_id,
        "dataset": dataset,
        "session_id": session_id,
        "source_run_id": prevalence.SOURCE_RUN_ID,
        "source_fit": str(fit_path),
        "source_fit_sha256": _digest(fit_path),
        "selection_conditioning": {
            "selected_bank_size": len(satellites),
            "catalog_numbers": catalog_numbers,
            "interpretation": "Posterior support is conditional on the sealed finite-set-linear-v2 bank and free state; pairing itself uses only candidate metadata.",
        },
        "join": {**join, **row_binding},
        "pairing_policy": {
            "probe_key": "(visit_index, receiver_id, probe_index)",
            "edge_definition": "canonical native residual bins with absolute index 251 through 256",
            "zero_definition": "canonical native residual exactly zero within 1e-9 Hz",
            "nearest_zero": "minimum final tracking-CFO circular distance under the full 1/4.4us alias; exact 1e-9-Hz raw-row ties are usable only when every tied row belongs to one existing prepared unique-peak cluster",
            "frame_epoch": "integer_epoch_sample plus fractional_epoch_offset_samples, circular modulo sample_rate/750Hz",
            "no_collapse_or_alias_period_change": True,
        },
        "accounting": {
            "all_row_count": len(joined),
            "edge_row_count": len(edge_rows),
            "paired_edge_row_count": len(pairing["pairs"]),
            "no_zero_edge_row_count": len(pairing["no_zero_edge_rows"]),
            "tied_nearest_zero_family_count": len(pairing["tied_nearest_zero_families"]),
            "within_existing_cluster_tie_count": sum(
                item["nearest_zero_tie_count"] > 1
                and item["zero_family_within_one_existing_cluster"]
                for item in pair_lineage
            ),
            "cross_cluster_tie_count": len(cross_cluster_ties),
            "cross_cluster_ties": cross_cluster_ties,
            "no_zero_edge_rows": pairing["no_zero_edge_rows"],
            "tied_nearest_zero_families": pairing["tied_nearest_zero_families"],
            "no_zero_edge_signal_mass": no_zero_mass,
            "forced_pair_count": 0,
        },
        "constants": {
            "full_alias_hz": DEFAULT_ALIAS_HZ,
            "sample_rate_hz": sample_rate_hz,
            "frame_rate_hz": FRAME_RATE_HZ,
            "frame_period_samples": frame_period_samples,
            "frequency_thresholds_hz": FREQUENCY_THRESHOLDS_HZ,
            "epoch_thresholds_samples": EPOCH_THRESHOLDS_SAMPLES,
        },
        "posterior_reproduction": {
            "sealed_objective": float(leader["objective"]),
            "reevaluated_objective": float(state["objective"]),
            "objective_absolute_difference": float(abs(state["objective"] - leader["objective"])),
            "total_signal_mass": total_signal_mass,
            "edge_signal_mass": float(np.sum(row_catalog_mass[edge_rows])),
        },
        "pair_summary": summary,
        "nearest_zero_lineage": pair_lineage,
        "provenance": {
            "source_hashes": {str(path.resolve()): _digest(path) for path in source_paths},
            "input_manifest_sha256": manifest["provenance"]["input_manifest_sha256"],
            "analysis_manifest_sha256": manifest["provenance"]["persisted_analysis_manifest_sha256"],
            "reference_accessed": False,
            "tle_queried": False,
            "iq_read": False,
            "fit_performed": False,
            "posterior_reevaluation_only": True,
        },
        "sealed": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id", choices=tuple(prevalence.UNITS))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id:
        parser.error("run-id must be one path component")
    output_dir = ROOT / "runs" / args.run_id / args.unit_id
    if output_dir.exists():
        raise FileExistsError(f"output already exists: {output_dir}")
    started = time.monotonic()
    receipt = run_case(args.unit_id, bulk_root=args.bulk_root)
    receipt["elapsed_s"] = time.monotonic() - started
    hashes = {path: _digest(path) for path in receipt["provenance"]["source_hashes"]}
    if hashes != receipt["provenance"]["source_hashes"]:
        raise RuntimeError("diagnostic provenance changed before seal")
    output_dir.mkdir(parents=True, exist_ok=False)
    output = output_dir / "diagnostic.json"
    output.write_text(json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "unit_id": args.unit_id,
                "output": str(output),
                "sha256": _digest(output),
                "elapsed_s": receipt["elapsed_s"],
                "edge_rows": receipt["accounting"]["edge_row_count"],
                "paired_rows": receipt["accounting"]["paired_edge_row_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
