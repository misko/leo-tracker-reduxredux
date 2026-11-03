#!/usr/bin/env python3
"""Metadata-only native residual prevalence at sealed finite-set-v2 states."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from finite_set_fit import GroupMedianGeometryData, build_likelihood_arms
from finite_set_fixed_position import _evaluate_state
from finite_set_likelihood import DEFAULT_ALIAS_HZ, circular_residual
from rough_smoke import load_module, serializable
from selection import ROOT


SOURCE_RUN_ID = "finite-set-raw-control-v2"
DEFAULT_RUN_ID = "candidate-prevalence-v1"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
NATIVE_RESIDUAL_BIN_HZ = 1.0 / (512.0 * 4.4e-6)
UNITS = {
    "DS10-S01": ("DS10", "scan-fw-df44e74320bd2718", 23),
    "DS11-S02": ("DS11", "scan-fw-c9e1a195660d003f", 16),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def array_digest(values):
    values = np.ascontiguousarray(values)
    payload = values.dtype.str.encode() + np.asarray(values.shape, dtype="<i8").tobytes()
    return hashlib.sha256(payload + values.tobytes()).hexdigest()


def classify_residual(residual_cfo_hz):
    """Classify the native residual after canonical full-alias wrapping."""

    if not np.isfinite(residual_cfo_hz):
        raise ValueError("residual CFO must be finite")
    canonical = float(circular_residual(float(residual_cfo_hz), 0.0, DEFAULT_ALIAS_HZ))
    if abs(canonical) <= 1e-9:
        return "zero", 0, canonical
    native_bin = int(round(canonical / NATIVE_RESIDUAL_BIN_HZ))
    if abs(native_bin) == 256:
        native_bin = -256
        canonical = -0.5 * DEFAULT_ALIAS_HZ
    on_bin = math.isclose(
        canonical,
        native_bin * NATIVE_RESIDUAL_BIN_HZ,
        rel_tol=0.0,
        abs_tol=1e-6,
    )
    if on_bin and abs(native_bin) == 1:
        label = "plus_or_minus_one"
    elif on_bin and 251 <= abs(native_bin) <= 256:
        label = "edge"
    else:
        label = "other_nonzero"
    return label, native_bin, canonical


def join_projected_metadata(projected_keys, metadata_rows):
    """Join exact visit/RX/probe/rank keys while retaining every disposition."""

    by_key = defaultdict(list)
    for row in metadata_rows:
        by_key[tuple(row["key"])].append(row)
    joined = []
    unmatched_projected = []
    ambiguous_projected = []
    used = set()
    for row_index, key in enumerate(projected_keys):
        key = tuple(key)
        matches = by_key.get(key, ())
        if len(matches) == 1:
            joined.append(matches[0])
            used.add(key)
        elif not matches:
            joined.append(None)
            unmatched_projected.append({"row": row_index, "key": list(key)})
        else:
            joined.append(None)
            ambiguous_projected.append(
                {"row": row_index, "key": list(key), "match_count": len(matches)}
            )
    unmatched_metadata = [
        {"key": list(key), "match_count": len(rows)}
        for key, rows in sorted(by_key.items())
        if key not in used
    ]
    ambiguous_metadata = [
        {"key": list(key), "match_count": len(rows)}
        for key, rows in sorted(by_key.items())
        if len(rows) > 1
    ]
    return joined, {
        "projected_row_count": len(projected_keys),
        "metadata_row_count": len(metadata_rows),
        "matched_row_count": sum(row is not None for row in joined),
        "unmatched_projected_count": len(unmatched_projected),
        "ambiguous_projected_count": len(ambiguous_projected),
        "unmatched_metadata_key_count": len(unmatched_metadata),
        "ambiguous_metadata_key_count": len(ambiguous_metadata),
        "unmatched_projected": unmatched_projected,
        "ambiguous_projected": ambiguous_projected,
        "unmatched_metadata": unmatched_metadata,
        "ambiguous_metadata": ambiguous_metadata,
        "forced_matches": 0,
    }


def _dimension_table(labels, dedup_weight, row_signal, row_catalog_mass, *, catalog_numbers=None):
    labels = np.asarray(labels)
    dedup_weight = np.asarray(dedup_weight, dtype=float)
    row_signal = np.asarray(row_signal, dtype=float)
    row_catalog_mass = np.asarray(row_catalog_mass, dtype=float)
    total_signal = float(np.sum(row_signal))
    total_dedup = float(np.sum(dedup_weight))
    result = []
    for value in sorted(set(labels.tolist()), key=lambda item: str(item)):
        rows = labels == value
        signal = float(np.sum(row_signal[rows]))
        entry = {
            "value": value.item() if isinstance(value, np.generic) else value,
            "raw_count": int(np.sum(rows)),
            "raw_fraction": float(np.mean(rows)),
            "deduplicated_equivalent_count": float(np.sum(dedup_weight[rows])),
            "deduplicated_equivalent_fraction": float(
                np.sum(dedup_weight[rows]) / total_dedup
            ),
            "signal_mass": signal,
            "signal_mass_prevalence": signal / total_signal if total_signal else 0.0,
        }
        if catalog_numbers is not None:
            masses = np.sum(row_catalog_mass[rows], axis=0)
            entry["catalog_contributions"] = [
                {
                    "catalog_number": int(number),
                    "signal_mass": float(mass),
                    "fraction_of_class_signal_mass": float(mass / signal) if signal else 0.0,
                }
                for number, mass in zip(catalog_numbers, masses, strict=True)
            ]
        result.append(entry)
    return result


def aggregate_prevalence(
    dimensions,
    original_to_unique,
    row_catalog_mass,
    catalog_numbers,
):
    """Aggregate raw, deduplicated-equivalent, and posterior signal prevalence."""

    original_to_unique = np.asarray(original_to_unique, dtype=int)
    row_catalog_mass = np.asarray(row_catalog_mass, dtype=float)
    catalog_numbers = np.asarray(catalog_numbers, dtype=int)
    row_count = len(original_to_unique)
    if row_catalog_mass.shape != (row_count, len(catalog_numbers)):
        raise ValueError("row catalog mass shape differs from rows and selected catalog")
    if any(len(np.asarray(values)) != row_count for values in dimensions.values()):
        raise ValueError("prevalence dimensions must align with rows")
    cluster_size = np.bincount(original_to_unique)
    if np.any(cluster_size <= 0):
        raise ValueError("unique peak mapping contains an empty index")
    dedup_weight = 1.0 / cluster_size[original_to_unique]
    row_signal = np.sum(row_catalog_mass, axis=1)
    tables = {}
    for name, labels in dimensions.items():
        tables[name] = _dimension_table(
            labels,
            dedup_weight,
            row_signal,
            row_catalog_mass,
            catalog_numbers=catalog_numbers if name == "residual_class" else None,
        )
    joint = defaultdict(lambda: [0, 0.0, 0.0])
    names = tuple(dimensions)
    arrays = [np.asarray(dimensions[name]) for name in names]
    for row in range(row_count):
        key = tuple(array[row].item() if isinstance(array[row], np.generic) else array[row] for array in arrays)
        values = joint[key]
        values[0] += 1
        values[1] += float(dedup_weight[row])
        values[2] += float(row_signal[row])
    total_signal = float(np.sum(row_signal))
    joint_rows = []
    for key, values in sorted(joint.items(), key=lambda item: tuple(map(str, item[0]))):
        joint_rows.append(
            {
                **dict(zip(names, key, strict=True)),
                "raw_count": values[0],
                "deduplicated_equivalent_count": values[1],
                "signal_mass": values[2],
                "signal_mass_prevalence": values[2] / total_signal if total_signal else 0.0,
            }
        )
    return {
        "row_count": row_count,
        "unique_peak_count": int(len(cluster_size)),
        "deduplicated_equivalent_count": float(np.sum(dedup_weight)),
        "total_signal_mass": total_signal,
        "tables": tables,
        "joint_dimension_order": list(names),
        "joint_strata": joint_rows,
    }


def _metadata_and_projection(root, session_id, expected_input, expected_analysis):
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
    if source.input_manifest_sha256 != expected_input:
        raise ValueError("tracking source input manifest differs from frozen bundle")
    if source.analysis_manifest_sha256 != expected_analysis:
        raise ValueError("tracking source analysis manifest differs from frozen bundle")
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
                raise ValueError("full analysis metadata differs from frozen bundle")
            for product in job.published_visits():
                for probe in product.probes:
                    for candidate in probe.candidates:
                        if not candidate.passed_fractional_margin_gate:
                            continue
                        metadata.append(
                            {
                                "key": [
                                    int(product.visit_index),
                                    int(probe.receiver_id),
                                    int(probe.probe_index),
                                    int(candidate.candidate_rank),
                                ],
                                "acquired_cfo_hz": float(candidate.acquired_cfo_hz),
                                "native_residual_cfo_hz": float(
                                    candidate.fractional_residual_cfo_hz
                                ),
                                "tracking_cfo_hz": float(candidate.fractional_tracking_cfo_hz),
                                "fractional_margin": float(candidate.fractional_margin),
                            }
                        )
    finally:
        analysis_store.close()
        iq_store.close()
    projected_keys = [
        [point.visit_index, point.receiver_id, point.probe_index, point.candidate_rank]
        for point in projected
    ]
    joined, accounting = join_projected_metadata(projected_keys, metadata)
    return source, projected, joined, accounting


def _verify_bundle_rows(data, manifest, projected):
    origin = int(manifest["origin_utc_ns"])
    groups = sorted({point.source_group_id for point in projected})
    group_index = {value: index for index, value in enumerate(groups)}
    expected = {
        "times": np.asarray(
            [(point.support_center_utc_ns - origin) / 1e9 for point in projected]
        ),
        "measured": np.asarray([point.measured_cfo_hz for point in projected]),
        "rf": np.asarray([point.actual_rf_hz for point in projected]),
        "receiver": np.asarray([point.receiver_id for point in projected], dtype=int),
        "channel": np.asarray([point.channel for point in projected], dtype=int),
        "group": np.asarray([group_index[point.source_group_id] for point in projected]),
        "margin": np.asarray([point.margin for point in projected]),
    }
    equality = {name: bool(np.array_equal(getattr(data, name), values)) for name, values in expected.items()}
    candidate_ids = [point.candidate_id for point in projected]
    candidate_digest = canonical_digest(candidate_ids)
    group_digest = canonical_digest(groups)
    receipt = manifest["raw_observations"]
    if not all(equality.values()):
        raise ValueError("projected public rows differ from frozen bundle arrays")
    if candidate_digest != receipt["candidate_ids_sha256"] or group_digest != receipt["source_group_ids_sha256"]:
        raise ValueError("projected public row identity differs from frozen bundle digest")
    return {
        "row_arrays_exact": equality,
        "candidate_ids_sha256": candidate_digest,
        "candidate_ids_match_frozen_bundle": True,
        "source_group_ids_sha256": group_digest,
        "source_group_ids_match_frozen_bundle": True,
    }


def _bins(values, count):
    values = np.asarray(values, dtype=float)
    edges = np.quantile(values, np.linspace(0.0, 1.0, count + 1))
    labels = np.searchsorted(edges[1:-1], values, side="right")
    return labels.astype(int), edges


def run_case(unit_id, *, bulk_root=DEFAULT_BULK_ROOT):
    if unit_id not in UNITS:
        raise ValueError("unsupported prevalence unit")
    dataset, session_id, expected_k = UNITS[unit_id]
    fit_path = ROOT / "runs" / SOURCE_RUN_ID / unit_id / "fit.json"
    bundle_dir = ROOT / "scans" / session_id
    bundle_json = bundle_dir / "bundle.json"
    bundle_npz = bundle_dir / "bundle.npz"
    source = json.loads(fit_path.read_text())
    manifest = json.loads(bundle_json.read_text())
    if source.get("reference_read_before_seal") is not False or source.get("evaluation_written") is not False:
        raise ValueError("finite-set source is not a sealed truth-free fit")
    leader = source["fit"]["finite_set_selection"]["score_leader"]
    satellites = np.asarray(leader["satellite_indices"], dtype=int)
    if len(satellites) != expected_k:
        raise ValueError("sealed finite-set leader cardinality changed")

    bundle = load_module(
        f"candidate_prevalence_bundle_{unit_id}",
        ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py",
    )
    data = bundle.Data(bundle_dir)
    tracking, projected, joined, join_accounting = _metadata_and_projection(
        Path(bulk_root),
        session_id,
        manifest["provenance"]["input_manifest_sha256"],
        manifest["provenance"]["persisted_analysis_manifest_sha256"],
    )
    row_binding = _verify_bundle_rows(data, manifest, projected)
    if any(row is None for row in joined):
        raise ValueError("exact metadata join is incomplete; no posterior rows were forced")

    geometry = GroupMedianGeometryData(data)
    likelihood = build_likelihood_arms(
        geometry,
        len(satellites),
        len(source["fit"]["full_bank"]),
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
        raise ValueError("sealed finite-set leader objective does not reproduce")
    result = state["result"]
    row_catalog_mass = np.asarray(result["row_association_probability"], dtype=float)
    original_to_unique = np.asarray(result["original_to_unique"], dtype=int)
    catalog_numbers = np.asarray(data.numbers)[satellites]
    if not np.allclose(
        np.sum(row_catalog_mass, axis=0),
        np.asarray(leader["satellite_support"], dtype=float),
        rtol=0,
        atol=1e-8,
    ):
        raise ValueError("reevaluated row posterior does not close to sealed satellite support")

    residual_class = []
    native_bin = []
    canonical_residual = []
    ranks = []
    closure_error = []
    for point, metadata in zip(projected, joined, strict=True):
        label, bin_value, canonical = classify_residual(metadata["native_residual_cfo_hz"])
        residual_class.append(label)
        native_bin.append(bin_value)
        canonical_residual.append(canonical)
        ranks.append(int(point.candidate_rank))
        closure_error.append(
            float(
                circular_residual(
                    metadata["acquired_cfo_hz"] + metadata["native_residual_cfo_hz"],
                    metadata["tracking_cfo_hz"],
                    DEFAULT_ALIAS_HZ,
                )
            )
        )
    if max(map(abs, closure_error), default=0.0) > 1e-6:
        raise ValueError("acquired plus native residual does not close to tracking CFO")
    time_bin, time_edges = _bins(data.times, 4)
    margin_bin, margin_edges = _bins(data.margin, 4)
    dimensions = {
        "receiver": np.asarray(data.receiver, dtype=int),
        "channel": np.asarray(data.channel, dtype=int),
        "time_bin": time_bin,
        "margin_bin": margin_bin,
        "rank": np.asarray(ranks, dtype=int),
        "residual_class": np.asarray(residual_class),
    }
    prevalence = aggregate_prevalence(
        dimensions,
        original_to_unique,
        row_catalog_mass,
        catalog_numbers,
    )
    clusters = likelihood.prepared.clusters
    duplicate_clusters = []
    mixed_class_clusters = 0
    for unique_index, members in enumerate(clusters):
        if len(members) == 1:
            continue
        classes = sorted({residual_class[index] for index in members})
        mixed_class_clusters += int(len(classes) > 1)
        duplicate_clusters.append(
            {
                "unique_peak_index": unique_index,
                "raw_rows": [int(index) for index in members],
                "candidate_ids": [projected[index].candidate_id for index in members],
                "residual_classes": classes,
                "ranks": [int(ranks[index]) for index in members],
            }
        )
    source_paths = [
        Path(__file__),
        fit_path,
        bundle_json,
        bundle_npz,
        Path(sys.modules["finite_set_likelihood"].__file__),
        Path(sys.modules["finite_set_fit"].__file__),
        Path(sys.modules["prediction_plan"].__file__),
    ]
    source_hashes = {str(path.resolve()): digest(path) for path in source_paths}
    return {
        "schema": "candidate-native-residual-prevalence/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "unit_id": unit_id,
        "dataset": dataset,
        "session_id": session_id,
        "source_run_id": SOURCE_RUN_ID,
        "source_fit": str(fit_path),
        "source_fit_sha256": digest(fit_path),
        "sealed_free_parameters_sha256": array_digest(
            np.asarray(leader["parameters"], dtype=float)
        ),
        "selection_conditioning": {
            "selected_finite_set_bank_size": len(satellites),
            "selected_satellite_indices": satellites,
            "selected_catalog_numbers": catalog_numbers,
            "selection_resolved": bool(source["fit"]["finite_set_selection"]["selection_resolved"]),
            "leader_success": bool(leader["success"]),
            "leader_status": str(leader["status"]),
            "interpretation": (
                "All signal-mass prevalence is conditional on this sealed finite-set-linear-v2 "
                "score-leader bank and free parameter state; it is not full-catalog posterior support."
            ),
        },
        "join": {
            **join_accounting,
            **row_binding,
            "key": "(visit_index, receiver_id, probe_index, candidate_rank)",
            "bundle_row_order_authority": "frozen projected candidate-ID sequence digest",
        },
        "duplicate_mapping": {
            "semantics": (
                "Exact-period copies within one source group map through raw_to_unique_peak. "
                "Deduplicated-equivalent counts allocate one unique peak equally across its raw "
                "members and therefore sum exactly to unique_peak_count. Posterior row signal "
                "mass uses the likelihood's member probabilities, not this accounting weight."
            ),
            "raw_to_unique_peak": original_to_unique,
            "raw_to_unique_peak_sha256": array_digest(original_to_unique),
            "raw_peak_count": len(original_to_unique),
            "unique_peak_count": len(clusters),
            "duplicate_cluster_count": len(duplicate_clusters),
            "duplicate_raw_row_count": int(sum(len(cluster["raw_rows"]) for cluster in duplicate_clusters)),
            "mixed_residual_class_duplicate_cluster_count": mixed_class_clusters,
            "duplicate_clusters": duplicate_clusters,
        },
        "binning": {
            "time_policy": "four empirical row-time quartiles; no truth or support used",
            "time_edges_s": time_edges,
            "margin_policy": "four empirical persisted-margin quartiles; no posterior used",
            "margin_edges": margin_edges,
            "native_residual_bin_hz_for_classification_only": NATIVE_RESIDUAL_BIN_HZ,
            "full_alias_hz": DEFAULT_ALIAS_HZ,
        },
        "posterior_reproduction": {
            "sealed_objective": float(leader["objective"]),
            "reevaluated_objective": float(state["objective"]),
            "objective_absolute_difference": float(abs(state["objective"] - leader["objective"])),
            "total_signal_mass": float(np.sum(row_catalog_mass)),
            "expected_clutter_peak_count": float(np.sum(result["expected_clutter_count"])),
            "group_count": len(result["group_values"]),
            "row_catalog_mass_sha256": array_digest(row_catalog_mass),
            "satellite_support": np.sum(row_catalog_mass, axis=0),
            "catalog_numbers": catalog_numbers,
        },
        "prevalence": prevalence,
        "native_residual_inventory": {
            "class_counts": dict(sorted(Counter(residual_class).items())),
            "native_bin_counts": dict(sorted(Counter(map(str, native_bin)).items())),
            "canonical_residual_sha256": array_digest(np.asarray(canonical_residual)),
            "maximum_cfo_closure_error_hz": max(map(abs, closure_error), default=0.0),
        },
        "provenance": {
            "source_hashes": source_hashes,
            "input_manifest_sha256": tracking.input_manifest_sha256,
            "analysis_manifest_sha256": tracking.analysis_manifest_sha256,
            "python_executable": sys.executable,
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
    parser.add_argument("unit_id", choices=tuple(UNITS))
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
    current_hashes = {
        path: digest(path) for path in receipt["provenance"]["source_hashes"]
    }
    if current_hashes != receipt["provenance"]["source_hashes"]:
        raise RuntimeError("diagnostic provenance changed before seal")
    output_dir.mkdir(parents=True, exist_ok=False)
    output = output_dir / "diagnostic.json"
    output.write_text(json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "unit_id": args.unit_id,
                "output": str(output),
                "sha256": digest(output),
                "elapsed_s": receipt["elapsed_s"],
                "rows": receipt["prevalence"]["row_count"],
                "unique_peaks": receipt["prevalence"]["unique_peak_count"],
                "signal_mass": receipt["prevalence"]["total_signal_mass"],
            }
        )
    )


if __name__ == "__main__":
    main()
