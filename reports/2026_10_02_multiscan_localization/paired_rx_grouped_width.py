#!/usr/bin/env python3
"""Estimate one paired-RX width after frozen alias-family grouping."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import alias_family_joint
import numpy as np
import paired_rx_width_diagnostic as original_width
import rx_difference

ROOT = Path(__file__).resolve().parent
DEFAULT_SELECTION = ROOT / "selection.json"
DEFAULT_EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
DEFAULT_RUN_ROOT = ROOT / "runs" / "rx-difference-cohort-v1"
DEFAULT_SCANS_ROOT = ROOT / "scans"
DEFAULT_ORIGINAL = ROOT / "paired-rx-width-diagnostic-v2.json"
DEFAULT_OUTPUT = ROOT / "paired-rx-grouped-width-v1.json"
ROW_ARRAYS = ("times", "measured", "rf", "receiver", "channel", "group", "margin")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _snapshot(paths):
    return {str(Path(path).resolve()): digest(path) for path in paths}


def _load_layout(directory):
    directory = Path(directory)
    manifest_path = directory / "bundle.json"
    archive_path = directory / "bundle.npz"
    manifest = json.loads(manifest_path.read_text())
    expected = manifest.get("artifacts", {}).get("bundle_npz_sha256")
    if not isinstance(expected, str) or digest(archive_path) != expected:
        raise ValueError("bundle.npz digest differs from bundle manifest")
    with np.load(archive_path, allow_pickle=False) as arrays:
        missing = sorted(set(ROW_ARRAYS) - set(arrays.files))
        if missing:
            raise ValueError(f"bundle lacks grouped-width arrays: {', '.join(missing)}")
        layout = SimpleNamespace(
            **{name: arrays[name].copy() for name in ROW_ARRAYS},
            session_id=manifest.get("session_id"),
            dataset=manifest.get("dataset"),
        )
    return layout, manifest


def grouped_layout(source, export_receipt):
    """Freeze full-group median times, then select alias-family representatives."""

    mapping = alias_family_joint.resolve_representative_rows(source, [export_receipt])
    representatives = mapping["representative_original_rows"]
    median_times = np.asarray(source.times, dtype=float).copy()
    groups = np.asarray(source.group)
    for group_value in np.unique(groups):
        rows = groups == group_value
        median_times[rows] = np.median(median_times[rows])
    arrays = {}
    for name in ROW_ARRAYS:
        values = median_times if name == "times" else np.asarray(getattr(source, name))
        arrays[name] = values[representatives].copy()
    result = SimpleNamespace(**arrays)
    if not np.array_equal(np.unique(result.group), np.unique(source.group)):
        raise ValueError("alias-family representatives dropped a source group")
    return result, representatives


def fit_scalar_width(cases, *, initial_sigma_hz, deadline):
    """Fit exactly one shared log-width with the frozen normalized likelihood."""

    from scipy.optimize import Bounds, minimize

    if not cases:
        raise ValueError("at least one grouped paired-RX case is required")
    if not original_width.SIGMA_MIN_HZ <= initial_sigma_hz <= original_width.SIGMA_MAX_HZ:
        raise ValueError("initial width lies outside frozen bounds")
    pair_count = sum(case.pair_count for case in cases)
    evaluations = 0

    def objective(log_sigma):
        nonlocal evaluations
        if time.monotonic() > deadline:
            raise TimeoutError("grouped width diagnostic budget exhausted")
        evaluations += 1
        value, gradient = original_width.total_nll_gradient(
            cases,
            "constant",
            np.asarray(log_sigma, dtype=float),
            0.0,
            1.0,
        )
        return value / pair_count, gradient / pair_count

    log_bounds = (
        math.log(original_width.SIGMA_MIN_HZ),
        math.log(original_width.SIGMA_MAX_HZ),
    )
    fitted = minimize(
        objective,
        np.array([math.log(initial_sigma_hz)]),
        jac=True,
        bounds=Bounds([log_bounds[0]], [log_bounds[1]]),
        method="L-BFGS-B",
        options={"ftol": 1e-12, "maxiter": 100},
    )
    sigma_hz = float(np.exp(np.asarray(fitted.x, dtype=float)[0]))
    negative_log_likelihood = original_width.total_nll(
        cases, "constant", [math.log(sigma_hz)], 0.0, 1.0
    )
    return {
        "model": "one_global_constant_sigma_after_alias_family_grouping",
        "parameter_count": 1,
        "sigma_difference_hz": sigma_hz,
        "implied_equal_independent_per_receiver_sigma_hz": sigma_hz / math.sqrt(2.0),
        "negative_log_likelihood": float(negative_log_likelihood),
        "success": bool(fitted.success),
        "status": int(fitted.status),
        "message": str(fitted.message),
        "evaluations": evaluations,
        "at_lower_bound": bool(
            np.isclose(sigma_hz, original_width.SIGMA_MIN_HZ, rtol=0.0, atol=1e-7)
        ),
        "bounds_hz": [original_width.SIGMA_MIN_HZ, original_width.SIGMA_MAX_HZ],
    }


def _load_export_receipt(cohort, session_id):
    record = cohort["records_by_session"].get(session_id)
    if record is None:
        raise ValueError(f"{session_id}: capture absent from alias-family manifest")
    path = cohort["receipt_paths"][session_id]
    actual = digest(path)
    if actual != record.get("sha256"):
        raise ValueError(f"{session_id}: alias-family receipt digest mismatch")
    receipt = json.loads(path.read_text())
    if (
        receipt.get("schema") != "alias-family-capture-export/v1"
        or receipt.get("sealed") is not True
        or receipt.get("session_id") != session_id
        or receipt.get("dataset") != record.get("dataset")
        or receipt.get("accounting", {}).get("raw_row_count")
        != record.get("raw_row_count")
        or receipt.get("accounting", {}).get("grouped_family_count")
        != record.get("grouped_family_count")
    ):
        raise ValueError(f"{session_id}: alias-family receipt disagrees with manifest")
    return receipt, path, actual


def load_grouped_case(dataset, unit, cohort, *, run_root, scans_root):
    """Load one receipt, construct its case, and release receipt-scale state."""

    unit_id = unit["unit_id"]
    sessions = unit.get("session_ids")
    if unit.get("size") != 1 or not isinstance(sessions, list) or len(sessions) != 1:
        raise ValueError("grouped width calibration accepts selected single captures only")
    session_id = sessions[0]
    receipt, receipt_path, receipt_sha256 = _load_export_receipt(cohort, session_id)
    provenance = receipt.get("provenance", {})
    if unit_id not in receipt.get("selected_unit_ids", ()):
        raise ValueError("alias-family receipt is not bound to selected single unit")
    if (
        provenance.get("reference_accessed") is not False
        or provenance.get("tle_queried") is not False
        or provenance.get("iq_read") is not False
        or provenance.get("fit_performed") is not False
    ):
        raise ValueError("alias-family receipt is not metadata-only and truth-free")
    scan_directory = Path(scans_root) / session_id
    fit_path = Path(run_root) / unit_id / "fit.json"
    input_paths = [
        receipt_path,
        scan_directory / "bundle.json",
        scan_directory / "bundle.npz",
        fit_path,
    ]
    before = _snapshot(input_paths)
    if (
        before[str((scan_directory / "bundle.json").resolve())]
        != receipt.get("input_digests", {}).get("bundle_json")
        or before[str((scan_directory / "bundle.npz").resolve())]
        != receipt.get("input_digests", {}).get("bundle_npz")
    ):
        raise ValueError(f"{session_id}: alias-family export does not bind scan bundle")
    fit_receipt = json.loads(fit_path.read_text())
    if (
        fit_receipt.get("reference_read") is not False
        or fit_receipt.get("ephemeris_read") is not False
    ):
        raise ValueError("RX-difference fit is not truth-free and TLE-free")
    if fit_receipt.get("unit", {}).get("unit_id") != unit_id or fit_receipt.get(
        "unit", {}
    ).get("session_ids") != [session_id]:
        raise ValueError("RX-difference fit unit identity differs")
    source, manifest = _load_layout(scan_directory)
    if manifest.get("dataset") != dataset or manifest.get("session_id") != session_id:
        raise ValueError("scan bundle identity differs from frozen selection")
    if fit_receipt.get("bundle_npz_sha256") != before[
        str((scan_directory / "bundle.npz").resolve())
    ] or fit_receipt.get("bundle_manifest_sha256") != before[
        str((scan_directory / "bundle.json").resolve())
    ]:
        raise ValueError("RX-difference fit does not bind scan bundle")
    if fit_receipt.get("source_sha256") != digest(Path(rx_difference.__file__).resolve()):
        raise ValueError("RX-difference fit does not bind current numerical helper")
    original_pairing = rx_difference.pair_receiver_groups(source)
    reduced, representatives = grouped_layout(source, receipt)
    paired = rx_difference.pair_receiver_groups(reduced)
    if (
        not np.array_equal(original_pairing.rx0_groups, paired.rx0_groups)
        or not np.array_equal(original_pairing.rx1_groups, paired.rx1_groups)
        or not np.array_equal(original_pairing.rf, paired.rf)
        or not np.allclose(original_pairing.times, paired.times, rtol=0.0, atol=1e-12)
    ):
        raise ValueError("alias-family grouping changed frozen RX group pairing")
    frozen_mean = original_width.frozen_model(paired, fit_receipt)
    case = original_width._scored_groups(
        reduced, paired, unit_id, dataset, frozen_mean
    )
    after = _snapshot(input_paths)
    if before != after:
        raise RuntimeError(f"{session_id}: grouped-width inputs changed during loading")
    status = {
        "unit_id": unit_id,
        "dataset": dataset,
        "session_id": session_id,
        "status": "ready",
        "selected_drift_model": fit_receipt["selected_model"],
        "raw_row_count": len(source.times),
        "grouped_representative_count": len(representatives),
        "collapsed_row_count": len(source.times) - len(representatives),
        "paired_group_count": case.pair_count,
        "paired_group_identity_unchanged": True,
        "difference_alternative_count": len(case.differences),
        "receipt_sha256": receipt_sha256,
        "input_sha256_pre": before,
        "input_sha256_post": after,
        "inputs_unchanged_during_case": True,
    }
    del receipt, source, reduced, original_pairing, paired, fit_receipt
    return case, status


def _selected_captures(selection, cohort):
    selected = original_width.selected_single_units(selection)
    if len(selected) != 32 or Counter(dataset for dataset, _ in selected) != Counter(
        {"DS10": 16, "DS11": 16}
    ):
        raise ValueError("frozen selection must contain 16 singles per dataset")
    expected = {
        unit["session_ids"][0]: dataset for dataset, unit in selected
    }
    if set(expected) != set(cohort["records_by_session"]):
        raise ValueError("selection and alias-family manifest cover different captures")
    for session_id, dataset in expected.items():
        if cohort["records_by_session"][session_id].get("dataset") != dataset:
            raise ValueError(f"{session_id}: alias-family manifest dataset differs")
    return selected


def _original_contract(original, selection_sha256):
    if (
        original.get("schema") != "paired-rx-score-width-diagnostic/v1"
        or original.get("selection_sha256") != selection_sha256
        or original.get("source_unchanged_during_run") is not True
    ):
        raise ValueError("original width diagnostic does not bind frozen selection")
    cases = original.get("cases")
    if not isinstance(cases, list) or len(cases) != 32:
        raise ValueError("original width diagnostic must contain all 32 singles")
    by_unit = {case.get("unit_id"): case for case in cases}
    if len(by_unit) != 32 or any(case.get("status") != "complete" for case in cases):
        raise ValueError("original width diagnostic cases are incomplete or duplicated")
    sigma = original.get("models", {}).get("learned_constant", {}).get("sigma_hz")
    if not isinstance(sigma, (int, float)) or not math.isfinite(sigma):
        raise ValueError("original diagnostic lacks a finite constant width")
    return by_unit, float(sigma)


def comparison_receipt(cases, statuses, original_by_unit, original_sigma_hz, fitted):
    for status in statuses:
        original_case = original_by_unit.get(status["unit_id"])
        if original_case is None or original_case.get("pair_count") != status[
            "paired_group_count"
        ]:
            raise ValueError(
                f"{status['unit_id']}: grouped and original paired-group counts differ"
            )
        status["original_paired_group_count"] = original_case["pair_count"]
        status["paired_group_count_unchanged"] = True
        status["original_difference_alternative_count"] = original_case[
            "difference_alternative_count"
        ]
    original_sigma_nll_on_grouped = original_width.total_nll(
        cases, "constant", [math.log(original_sigma_hz)], 0.0, 1.0
    )
    return {
        "original_ungrouped": {
            "pair_count": sum(row["pair_count"] for row in original_by_unit.values()),
            "difference_alternative_count": sum(
                row["difference_alternative_count"] for row in original_by_unit.values()
            ),
            "sigma_difference_hz": original_sigma_hz,
            "implied_equal_independent_per_receiver_sigma_hz": original_sigma_hz
            / math.sqrt(2.0),
        },
        "alias_grouped": {
            "pair_count": sum(case.pair_count for case in cases),
            "difference_alternative_count": sum(
                row["difference_alternative_count"] for row in statuses
            ),
            "sigma_difference_hz": fitted["sigma_difference_hz"],
            "implied_equal_independent_per_receiver_sigma_hz": fitted[
                "implied_equal_independent_per_receiver_sigma_hz"
            ],
        },
        "sigma_difference_change_hz": fitted["sigma_difference_hz"]
        - original_sigma_hz,
        "sigma_difference_ratio_grouped_to_original": fitted["sigma_difference_hz"]
        / original_sigma_hz,
        "grouped_input_nll_at_original_sigma": float(original_sigma_nll_on_grouped),
        "grouped_input_nll_at_grouped_sigma": fitted["negative_log_likelihood"],
        "paired_group_counts_unchanged": True,
        "cross_input_nll_comparison_valid": False,
    }


def run(
    selection_path,
    export_directory,
    run_root,
    scans_root,
    original_path,
    *,
    budget_s=120.0,
    expected_export_manifest_sha256=None,
    case_loader=load_grouped_case,
):
    if not 0 < budget_s <= 180:
        raise ValueError("total grouped-width budget must be in (0, 180] seconds")
    started = time.monotonic()
    deadline = started + budget_s
    selection_path = Path(selection_path)
    original_path = Path(original_path)
    selection_sha256 = digest(selection_path)
    selection = json.loads(selection_path.read_text())
    cohort = alias_family_joint.load_cohort_manifest(
        export_directory,
        expected_manifest_sha256=expected_export_manifest_sha256,
    )
    if cohort["manifest"].get("selection_sha256") != selection_sha256:
        raise ValueError("alias-family export and frozen selection digests differ")
    if cohort["manifest"].get("provenance") != {
        "reference_accessed": False,
        "tle_queried": False,
        "iq_read": False,
        "fit_performed": False,
    }:
        raise ValueError("alias-family cohort manifest is not metadata-only and truth-free")
    selected = _selected_captures(selection, cohort)
    original = json.loads(original_path.read_text())
    original_by_unit, original_sigma_hz = _original_contract(
        original, selection_sha256
    )
    source_paths = [
        Path(__file__).resolve(),
        Path(original_width.__file__).resolve(),
        Path(rx_difference.__file__).resolve(),
        Path(alias_family_joint.__file__).resolve(),
    ]
    source_before = _snapshot(source_paths)
    fixed_before = _snapshot(
        [selection_path, cohort["manifest_path"], original_path]
    )
    cases = []
    statuses = []
    for dataset, unit in selected:
        if time.monotonic() > deadline:
            raise TimeoutError("budget exhausted before all 32 grouped cases loaded")
        case, status = case_loader(
            dataset,
            unit,
            cohort,
            run_root=run_root,
            scans_root=scans_root,
        )
        cases.append(case)
        statuses.append(status)
    fitted = fit_scalar_width(
        cases, initial_sigma_hz=original_sigma_hz, deadline=deadline
    )
    comparison = comparison_receipt(
        cases, statuses, original_by_unit, original_sigma_hz, fitted
    )
    dataset_summary = {}
    for dataset in ("DS10", "DS11"):
        rows = [row for row in statuses if row["dataset"] == dataset]
        dataset_summary[dataset] = {
            "capture_count": len(rows),
            "paired_group_count": sum(row["paired_group_count"] for row in rows),
            "raw_row_count": sum(row["raw_row_count"] for row in rows),
            "grouped_representative_count": sum(
                row["grouped_representative_count"] for row in rows
            ),
            "difference_alternative_count": sum(
                row["difference_alternative_count"] for row in rows
            ),
        }
    source_after = _snapshot(source_paths)
    fixed_after = _snapshot(
        [selection_path, cohort["manifest_path"], original_path]
    )
    if source_before != source_after or fixed_before != fixed_after:
        raise RuntimeError("grouped-width sources or fixed manifests changed before seal")
    return {
        "schema": "paired-rx-alias-grouped-width/v1",
        "scope": (
            "All 32 selected single captures are training data. One global paired-RX "
            "difference width is fitted after frozen candidate-independent alias-family "
            "grouping. Frozen RX1-RX0 means are not reoptimized. This is descriptive, not "
            "held-out validation or a geolocation result."
        ),
        "configuration": {
            "signal_mass": original_width.SIGNAL_MASS,
            "uniform_null_mass": 1.0 - original_width.SIGNAL_MASS,
            "alias_hz": rx_difference.ALIAS_HZ,
            "sigma_bounds_hz": [
                original_width.SIGMA_MIN_HZ,
                original_width.SIGMA_MAX_HZ,
            ],
            "width_model": "one global scalar; no margin or row dependence",
            "likelihood": (
                "normalized wrapped Gaussian signal density plus explicit uniform null; one "
                "normalized categorical term per paired source-group pair"
            ),
            "geometry_order": "full-source-group median time before representative filtering",
        },
        "selection_sha256": selection_sha256,
        "alias_family_manifest_sha256": cohort["manifest_sha256"],
        "original_width_receipt_sha256": digest(original_path),
        "source_sha256_pre": source_before,
        "source_sha256_post": source_after,
        "fixed_inputs_sha256_pre": fixed_before,
        "fixed_inputs_sha256_post": fixed_after,
        "sources_and_fixed_inputs_unchanged_before_seal": True,
        "fit": fitted,
        "comparison": comparison,
        "datasets": dataset_summary,
        "cases": statuses,
        "elapsed_s": time.monotonic() - started,
        "budget_s": float(budget_s),
        "limitations": [
            (
                "The fitted width describes RX1-RX0 differences; dividing by sqrt(2) is only "
                "an equal-independent receiver heuristic."
            ),
            (
                "Common-mode detector error, source Doppler, orbital error, and absolute "
                "frequency error remain unidentified."
            ),
            (
                "Alternative families form a normalized categorical proxy and are not "
                "independent physical samples."
            ),
            "Likelihood values are not compared across grouped and ungrouped inputs.",
            "No fitted width is promoted into a geolocation model by this diagnostic.",
        ],
        "provenance": {
            "reference_accessed": False,
            "tle_accessed": False,
            "ephemeris_accessed": False,
            "geolocation_fit_accessed": False,
            "iq_read": False,
            "rf_collection_performed": False,
            "all_samples_training": True,
            "one_export_receipt_loaded_at_a_time": True,
        },
        "sealed": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--exports", type=Path, default=DEFAULT_EXPORTS)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--scans-root", type=Path, default=DEFAULT_SCANS_ROOT)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--budget-s", type=float, default=120.0)
    parser.add_argument("--expected-export-manifest-sha256")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    receipt = run(
        args.selection,
        args.exports,
        args.run_root,
        args.scans_root,
        args.original,
        budget_s=args.budget_s,
        expected_export_manifest_sha256=args.expected_export_manifest_sha256,
    )
    args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "captures": len(receipt["cases"]),
                "paired_groups": receipt["comparison"]["alias_grouped"]["pair_count"],
                "sigma_difference_hz": receipt["fit"]["sigma_difference_hz"],
                "implied_equal_independent_per_receiver_sigma_hz": receipt["fit"][
                    "implied_equal_independent_per_receiver_sigma_hz"
                ],
                "success": receipt["fit"]["success"],
                "elapsed_s": receipt["elapsed_s"],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "comparison_receipt",
    "fit_scalar_width",
    "grouped_layout",
    "load_grouped_case",
    "run",
]
