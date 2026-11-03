"""Truth-free margin-weighted row-alternative likelihood ablation."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood, frozen_identity_masses
from gauss_newton import refine_gauss_newton
from grouped_likelihood import DEFAULT_ALIAS_HZ
from profile_seed import _validate_source_provenance
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import candidate_ladder, frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def observed_features(data, *, alias_hz=DEFAULT_ALIAS_HZ):
    if not np.isfinite(alias_hz) or alias_hz <= 0:
        raise ValueError("alias_hz must be positive and finite")
    return np.column_stack(
        [
            data.group,
            data.times,
            data.rf,
            data.receiver,
            data.channel,
            np.mod(data.measured, alias_hz),
        ]
    )


def margin_row_weights(data, *, alias_hz=DEFAULT_ALIAS_HZ):
    """Freeze positive linear margin mass per unique observed alternative.

    Every retained duplicate row receives the feature's maximum margin divided
    by its duplicate count. Grouped likelihood construction subsequently
    normalizes these masses within each raw source group.
    """

    margins = np.asarray(data.margin, dtype=float)
    if margins.shape != np.asarray(data.measured).shape:
        raise ValueError("margin must match measured rows")
    if np.any(~np.isfinite(margins)) or np.any(margins <= 0):
        raise ValueError("all GLRT margins must be positive and finite")
    features = observed_features(data, alias_hz=alias_hz)
    _, inverse, counts = np.unique(
        features, axis=0, return_inverse=True, return_counts=True
    )
    order = np.argsort(inverse, kind="stable")
    starts = np.r_[0, np.cumsum(counts[:-1])]
    maximum_margin = np.maximum.reduceat(margins[order], starts)
    return maximum_margin[inverse] / counts[inverse]


def margin_weight_diagnostics(data, weights):
    features = observed_features(data)
    unique_features, inverse, counts = np.unique(
        features, axis=0, return_inverse=True, return_counts=True
    )
    margins = np.asarray(data.margin, dtype=float)
    order = np.argsort(inverse, kind="stable")
    starts = np.r_[0, np.cumsum(counts[:-1])]
    feature_margin = np.maximum.reduceat(margins[order], starts)
    groups = unique_features[:, 0]
    group_values, group_inverse = np.unique(groups, return_inverse=True)
    group_min = np.full(len(group_values), np.inf)
    group_max = np.full(len(group_values), -np.inf)
    np.minimum.at(group_min, group_inverse, feature_margin)
    np.maximum.at(group_max, group_inverse, feature_margin)
    return {
        "row_count": len(margins),
        "unique_feature_count": len(unique_features),
        "duplicate_row_count": int(len(margins) - len(unique_features)),
        "group_count": len(group_values),
        "groups_with_margin_range": int(np.sum(group_max > group_min)),
        "feature_margin_min": float(np.min(feature_margin)),
        "feature_margin_median": float(np.median(feature_margin)),
        "feature_margin_max": float(np.max(feature_margin)),
        "row_weight_sum": float(np.sum(weights)),
    }


def fit_margin_weighted(data, source, *, budget_s=20.0):
    """Refit frozen dense-anchor banks with only row-alternative masses changed."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= 20:
        raise ValueError("budget_s must lie in (0, 20]")
    source_fit = source["fit"] if "fit" in source else source
    anchors = source_fit["anchors"]
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    capture_count = len(getattr(data, "child_sessions", [getattr(data, "session_id", None)]))
    ladder = candidate_ladder(
        source_fit["rough"]["assignments"],
        sizes=tuple(size * capture_count for size in (4, 8, 12)),
    )
    if not np.array_equal(ladder[-1][0], full_bank):
        raise ValueError("source full bank differs from its frozen rough ladder")
    weights = margin_row_weights(data)
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=weights,
        anchors=[anchor["groups"] for anchor in anchors],
    )
    source_trials = source_fit["trials"]
    trials = []
    for satellites, support in ladder:
        matches = [
            trial
            for trial in source_trials
            if np.array_equal(np.asarray(trial["satellite_indices"]), satellites)
        ]
        if len(matches) != 1:
            raise ValueError("source must contain exactly one sealed trial per frozen bank")
        source_trial = matches[0]
        initial = np.asarray(source_trial["parameters"], dtype=float).copy()
        if initial.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(initial)):
            raise ValueError("sealed dense parameters do not match the candidate pool")
        masses = frozen_identity_masses(anchors, full_bank, satellites)
        sealed_masses = source_trial["identity_masses"]
        if set(masses) != set(sealed_masses):
            raise ValueError("source identity-mass fields are incomplete")
        for key, value in masses.items():
            if not np.array_equal(np.asarray(value), np.asarray(sealed_masses[key])):
                raise ValueError(f"source {key} differs from frozen identity masses")
        likelihood = FixedBankLikelihood(prepared, masses)
        trial = refine_gauss_newton(
            data,
            initial,
            satellites,
            support,
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            budget_s=float(budget_s),
        )
        trial.pop("satellite_weights")
        trial["identity_masses"] = masses
        trial["source_objective"] = source_trial["objective"]
        trial["source_status"] = source_trial["status"]
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    baseline_weights = frozen_row_weights(data)
    return {
        "rough": source_fit["rough"],
        "anchors": anchors,
        "full_bank": full_bank,
        "trials": trials,
        **select_trials(trials),
        "row_weight_diagnostics": margin_weight_diagnostics(data, weights),
        "baseline_weight_sum": float(np.sum(baseline_weights)),
        "bank_branches_independent": True,
        "bank_selection_reevaluated": True,
        "scope": (
            "Truth-free heuristic margin-weighted likelihood proxy. All raw rows remain and "
            "each unique observed alternative receives linear positive mass equal to its "
            "maximum stored GLRT margin; duplicate rows divide that mass equally. Group "
            "normalization, dense anchors, candidate banks, identity masses, sigma, tau prior, "
            "bounds, and sealed dense starts remain fixed. Stored GLRT margins are correlated "
            "and uncalibrated, so these masses are not posterior probabilities."
        ),
    }


def run_case(source_path, run_id, budget_s):
    source_path = Path(source_path)
    source = json.loads(source_path.read_text())
    if source.get("stage") != "dense_anchor":
        raise ValueError("source must be a sealed dense-anchor fit")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    _validate_source_provenance(source)
    unit = source["unit"]
    if unit["size"] != 1 or unit["unit_id"] not in ("DS10-S01", "DS11-S02"):
        raise ValueError("margin-weighted v1 is restricted to the two frozen pilots")
    output = ROOT / "runs" / run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        path.name: digest(path)
        for path in sorted(ROOT.glob("*.py"))
        if not path.name.startswith("test_")
    }
    bundle = load_module(
        "margin_weighted_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / unit["session_ids"][0])
    started = time.monotonic()
    fitted = fit_margin_weighted(data, source, budget_s=budget_s)
    receipt = {
        "schema": "multiscan-margin-weighted-fit/v1",
        "stage": "margin_weighted",
        "unit": unit,
        "dataset": source["dataset"],
        "run_id": run_id,
        "source_fit": str(source_path),
        "source_fit_sha256": digest(source_path),
        "selection_sha256": source["selection_sha256"],
        "inputs": source["inputs"],
        "source_hashes": sources,
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "bank_sizes": [4, 8, 12],
            "budget_s_per_bank": float(budget_s),
            "weighting": "linear-max-margin-per-unique-observed-feature",
            "optimizer": "complete-data-fisher-gn/v2",
        },
        "reference_read_before_seal": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    fit_sha256 = digest(fit_path)
    reference = json.loads(
        (ROOT / "scans" / unit["session_ids"][0] / "evaluation.json").read_text()
    )["reference_site"]
    expected = bundle._COMMON.ecef(reference["latitude_deg"], reference["longitude_deg"])
    errors = []
    for trial in fitted["trials"]:
        estimated = bundle._COMMON.ecef(*bundle._COMMON.coordinates(trial["parameters"][:2]))
        errors.append(
            {
                "satellite_count": trial["satellite_count"],
                "objective": trial["objective"],
                "selection_score": trial["selection_score"],
                "success": trial["success"],
                "status": trial["status"],
                "convergence_reason": trial["convergence_reason"],
                "reference_error_km": float(np.linalg.norm(estimated - expected)),
            }
        )
    evaluation = {
        "schema": "multiscan-margin-weighted-evaluation/v1",
        "unit_id": unit["unit_id"],
        "fit_sha256": fit_sha256,
        "trial_reference_errors": errors,
        "objective_selected_satellite_count": fitted["score_leader"]["satellite_count"],
        "selection_resolved": fitted["selection_resolved"],
        "eligible_for_cohort": False,
        "scope": "Post-seal reference evaluation only; no reference-derived fitting or selection.",
    }
    (output / "evaluation.json").write_text(json.dumps(serializable(evaluation), indent=2) + "\n")
    return receipt, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--budget-s", type=float, default=20.0)
    args = parser.parse_args()
    receipt, evaluation = run_case(args.source_fit, args.run_id, args.budget_s)
    print(
        json.dumps(
            serializable(
                {
                    "unit_id": receipt["unit"]["unit_id"],
                    "fit_sha256": evaluation["fit_sha256"],
                    "row_weight_diagnostics": receipt["fit"]["row_weight_diagnostics"],
                    "trial_reference_errors": evaluation["trial_reference_errors"],
                }
            )
        )
    )


if __name__ == "__main__":
    main()
