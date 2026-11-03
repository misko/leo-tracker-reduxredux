"""Independent frozen-bank refinements with broader whole-track coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood, anchor_partition, frozen_identity_masses
from gauss_newton import refine_gauss_newton
from profile_seed import _validate_source_provenance
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import candidate_ladder, frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fit_payload(receipt):
    return receipt["fit"] if "fit" in receipt else receipt


def seed_trial(receipt):
    fit = _fit_payload(receipt)
    stage = receipt.get("stage") if isinstance(receipt, dict) else None
    if stage == "profile_zoom" or "selected" in fit:
        return fit["selected"]["fit"]
    if stage == "annealed" or "score_leader" in fit:
        return fit["score_leader"]
    raise ValueError("seed receipt has no supported sealed trial")


def anchor_coverage(data, anchors):
    groups = np.unique(data.group)
    anchored = np.concatenate([np.asarray(anchor["groups"]) for anchor in anchors]) if anchors else []
    anchored_count = len(np.unique(anchored))
    return {
        "anchor_count": len(anchors),
        "total_group_count": len(groups),
        "anchored_group_count": anchored_count,
        "raw_group_count": len(groups) - anchored_count,
        "anchored_group_fraction": anchored_count / len(groups),
    }


def fit_dense_anchors(data, proposal, seed, *, budget_s=20.0):
    """Fit all frozen candidate prefixes with only anchor coverage changed."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= 20:
        raise ValueError("budget_s must lie in (0, 20]")
    proposal = _fit_payload(proposal)
    seed = seed_trial(seed) if isinstance(seed, dict) else seed
    seed_parameters = np.asarray(seed["parameters"], dtype=float)
    if seed_parameters.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(seed_parameters)):
        raise ValueError("seed parameters do not match the candidate bank")
    capture_count = len(getattr(data, "child_sessions", [getattr(data, "session_id", None)]))
    ladder = candidate_ladder(
        proposal["rough"]["assignments"],
        sizes=tuple(size * capture_count for size in (4, 8, 12)),
    )
    full_bank = ladder[-1][0]
    seed_satellites = np.asarray(seed["satellite_indices"], dtype=int)
    if not np.array_equal(seed_satellites, full_bank):
        raise ValueError("sealed seed bank differs from the frozen rough ladder")
    sparse_anchors = anchor_partition(data, max_anchors=12 * capture_count)
    dense_anchors = anchor_partition(data, max_anchors=48 * capture_count)
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in dense_anchors],
    )
    trials = []
    for satellites, support in ladder:
        initial = seed_parameters.copy()
        initial[6:] = 0.0
        initial[6 + satellites] = seed_parameters[6 + satellites]
        masses = frozen_identity_masses(dense_anchors, full_bank, satellites)
        likelihood = FixedBankLikelihood(prepared, masses)
        trial = refine_gauss_newton(
            data,
            initial,
            satellites,
            support,
            likelihood,
            sigma_hz=200.0,
            budget_s=float(budget_s),
        )
        trial.pop("satellite_weights")
        trial["identity_masses"] = masses
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    return {
        "rough": proposal["rough"],
        "seed_parameters": seed_parameters,
        "seed_satellite_indices": seed_satellites,
        "full_bank": full_bank,
        "anchors": dense_anchors,
        "anchor_cap_per_capture": 48,
        "coverage_before": anchor_coverage(data, sparse_anchors),
        "coverage_after": anchor_coverage(data, dense_anchors),
        "trials": trials,
        **select_trials(trials),
        "bank_branches_independent": True,
        "bank_selection_reevaluated": True,
        "scope": (
            "Truth-free conditional dense-anchor comparison. Rough candidate proposals and one "
            "sealed nuisance seed are frozen before all independent K4/K8/K12 branches. Only "
            "the disjoint whole-track anchor cap changes from 12 to 48 per capture. All source "
            "groups remain represented exactly once."
        ),
    }


def run_case(proposal_path, seed_path, run_id, budget_s):
    proposal_path = Path(proposal_path)
    seed_path = Path(seed_path)
    proposal_receipt = json.loads(proposal_path.read_text())
    seed_receipt = json.loads(seed_path.read_text())
    if proposal_receipt.get("stage") not in ("coherent", "annealed"):
        raise ValueError("proposal must contain a sealed coherent rough ladder")
    if seed_receipt.get("stage") not in ("profile_zoom", "annealed"):
        raise ValueError("seed must be a sealed profile-zoom or annealed fit")
    if proposal_receipt["unit"] != seed_receipt["unit"]:
        raise ValueError("proposal and seed units differ")
    if seed_receipt.get("stage") == "profile_zoom":
        if seed_receipt["source_fit_sha256"] != digest(proposal_path):
            raise ValueError("profile-zoom seed does not bind the proposal fit")
    elif seed_path.resolve() != proposal_path.resolve():
        raise ValueError("annealed seed must also supply its own frozen proposal")
    _validate_source_provenance(proposal_receipt)
    unit = proposal_receipt["unit"]
    if unit["size"] != 1 or unit["unit_id"] not in ("DS10-S01", "DS11-S02"):
        raise ValueError("dense-anchor v1 is restricted to the two frozen single-scan pilots")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    output = ROOT / "runs" / run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        path.name: digest(path)
        for path in sorted(ROOT.glob("*.py"))
        if not path.name.startswith("test_")
    }
    bundle = load_module(
        "dense_anchor_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / unit["session_ids"][0])
    started = time.monotonic()
    fitted = fit_dense_anchors(data, proposal_receipt, seed_receipt, budget_s=budget_s)
    receipt = {
        "schema": "multiscan-dense-anchor-fit/v1",
        "stage": "dense_anchor",
        "unit": unit,
        "dataset": proposal_receipt["dataset"],
        "run_id": run_id,
        "proposal_fit": str(proposal_path),
        "proposal_fit_sha256": digest(proposal_path),
        "seed_fit": str(seed_path),
        "seed_fit_sha256": digest(seed_path),
        "selection_sha256": proposal_receipt["selection_sha256"],
        "inputs": proposal_receipt["inputs"],
        "source_hashes": sources,
        "configuration": {
            "sigma_hz": 200.0,
            "bank_sizes": [4, 8, 12],
            "budget_s_per_bank": float(budget_s),
            "sparse_anchor_cap_per_capture": 12,
            "dense_anchor_cap_per_capture": 48,
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

    reference_path = ROOT / "scans" / unit["session_ids"][0] / "evaluation.json"
    reference = json.loads(reference_path.read_text())["reference_site"]
    trial_errors = []
    for trial in fitted["trials"]:
        estimated = bundle._COMMON.ecef(*bundle._COMMON.coordinates(trial["parameters"][:2]))
        expected = bundle._COMMON.ecef(reference["latitude_deg"], reference["longitude_deg"])
        trial_errors.append(
            {
                "satellite_count": trial["satellite_count"],
                "objective": trial["objective"],
                "success": trial["success"],
                "status": trial["status"],
                "convergence_reason": trial["convergence_reason"],
                "reference_error_km": float(np.linalg.norm(estimated - expected)),
            }
        )
    evaluation = {
        "schema": "multiscan-dense-anchor-evaluation/v1",
        "unit_id": unit["unit_id"],
        "fit_sha256": fit_sha256,
        "trial_reference_errors": trial_errors,
        "objective_selected_satellite_count": fitted["score_leader"]["satellite_count"],
        "selection_resolved": fitted["selection_resolved"],
        "eligible_for_cohort": False,
        "scope": (
            "Post-seal reference evaluation only. Reference errors did not select anchors, "
            "candidate banks, starts, hyperparameters, or the objective leader."
        ),
    }
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    return receipt, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal-fit", required=True, type=Path)
    parser.add_argument("--seed-fit", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--budget-s", type=float, default=20.0)
    args = parser.parse_args()
    receipt, evaluation = run_case(
        args.proposal_fit, args.seed_fit, args.run_id, args.budget_s
    )
    print(
        json.dumps(
            {
                "unit_id": receipt["unit"]["unit_id"],
                "fit_sha256": evaluation["fit_sha256"],
                "coverage_before": receipt["fit"]["coverage_before"],
                "coverage_after": receipt["fit"]["coverage_after"],
                "trial_reference_errors": evaluation["trial_reference_errors"],
            }
        )
    )


if __name__ == "__main__":
    main()
