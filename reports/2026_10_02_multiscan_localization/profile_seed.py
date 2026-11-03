"""Truth-free profiled position grid followed by bounded free local refinements."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from coherent_fit import FixedBankLikelihood
from fixed_position_diagnostic import fit_nuisance_at_position
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import frozen_row_weights, refine_bank
from track_likelihood import prepare_track_grouped_likelihood


GRID_OFFSETS_KM = (-10.0, -5.0, 0.0, 5.0, 10.0)


def _fit_payload(sourcefit):
    if not isinstance(sourcefit, dict):
        raise TypeError("sourcefit must be a decoded fit receipt")
    return sourcefit["fit"] if "fit" in sourcefit else sourcefit


def _sha256_bytes(values):
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def _selected_support(fit, satellites):
    support = {int(satellite): 0.0 for satellite in satellites}
    for assignment in fit["rough"]["assignments"]:
        if (
            assignment["accepted"]
            and assignment["source_groups"] >= 15
            and assignment["span_s"] >= 15
        ):
            satellite = int(assignment["satellite_index"])
            if satellite in support:
                support[satellite] += float(assignment["source_groups"])
    values = np.asarray([support[int(satellite)] for satellite in satellites])
    if np.any(values <= 0):
        raise ValueError("selected bank lacks frozen positive rough support")
    return values


def run_profile_seed(
    data,
    sourcefit,
    *,
    offsets_km=GRID_OFFSETS_KM,
    node_budget_s=3.0,
    finalist_count=3,
    refine_budget_s=20.0,
):
    """Profile one frozen grid and refine the best finite nodes without truth."""

    fit = _fit_payload(sourcefit)
    if not fit.get("keep_track_identity", False):
        raise ValueError("sourcefit must retain coherent track identity")
    offsets = np.asarray(offsets_km, dtype=float)
    if offsets.shape != (5,) or not np.array_equal(offsets, np.asarray(GRID_OFFSETS_KM)):
        raise ValueError("offsets_km must be the frozen five-point grid")
    if not np.isfinite(node_budget_s) or not 0 < node_budget_s <= 3:
        raise ValueError("node_budget_s must lie in (0, 3]")
    if finalist_count != 3:
        raise ValueError("finalist_count must remain frozen at three")
    if not np.isfinite(refine_budget_s) or not 0 < refine_budget_s <= 20:
        raise ValueError("refine_budget_s must lie in (0, 20]")

    rough_center = np.asarray(fit["rough"]["position_km"], dtype=float)
    if rough_center.shape != (2,) or np.any(~np.isfinite(rough_center)):
        raise ValueError("source rough center is invalid")
    leader = fit["score_leader"]
    satellites = np.asarray(leader["satellite_indices"], dtype=int)
    source_parameters = np.asarray(leader["parameters"], dtype=float)
    if source_parameters.shape != (6 + len(data.numbers),):
        raise ValueError("source leader parameters do not match data")
    common_initial = source_parameters.copy()
    common_initial[6:] = 0.0
    common_initial[6 + satellites] = source_parameters[6 + satellites]
    common_nuisance = np.r_[common_initial[2:6], common_initial[6 + satellites]]
    common_nuisance_sha256 = _sha256_bytes(common_nuisance)

    nodes = []
    node_index = 0
    for east_offset in offsets:
        for north_offset in offsets:
            position = rough_center + [east_offset, north_offset]
            started = time.monotonic()
            try:
                fitted = fit_nuisance_at_position(
                    data,
                    sourcefit,
                    position,
                    budget_s=float(node_budget_s),
                )
                node = {
                    "node_index": node_index,
                    "offset_km": [float(east_offset), float(north_offset)],
                    "position_km": position,
                    "attempted": True,
                    "common_nuisance_initial_sha256": common_nuisance_sha256,
                    "fit": fitted,
                }
            except Exception as error:
                node = {
                    "node_index": node_index,
                    "offset_km": [float(east_offset), float(north_offset)],
                    "position_km": position,
                    "attempted": True,
                    "common_nuisance_initial_sha256": common_nuisance_sha256,
                    "fit": None,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "elapsed_s": time.monotonic() - started,
                }
            nodes.append(node)
            node_index += 1

    finite_nodes = [
        node
        for node in nodes
        if node["fit"] is not None and np.isfinite(node["fit"].get("objective", np.nan))
    ]
    if len(finite_nodes) < finalist_count:
        raise RuntimeError("fewer than three grid nodes produced finite objectives")
    finalists = sorted(finite_nodes, key=lambda node: (node["fit"]["objective"], node["node_index"]))[
        :finalist_count
    ]

    anchors = fit["anchors"]
    masses = leader["identity_masses"]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[np.asarray(anchor["groups"]) for anchor in anchors],
    )
    support = _selected_support(fit, satellites)
    final_trials = []
    for seed_rank, node in enumerate(finalists):
        likelihood = FixedBankLikelihood(prepared, masses)
        try:
            trial = refine_bank(
                data,
                np.asarray(node["fit"]["parameters"], dtype=float).copy(),
                satellites,
                support,
                likelihood,
                sigma_hz=200.0,
                budget_s=float(refine_budget_s),
            )
            trial.pop("satellite_weights")
            trial["identity_masses"] = masses
            trial["likelihood_diagnostics"] = {
                key: value
                for key, value in likelihood.last_result.items()
                if "track" in key or key.endswith("group_count")
            }
            final_trials.append(
                {
                    "seed_rank": seed_rank,
                    "seed_node_index": node["node_index"],
                    "seed_profile_objective": float(node["fit"]["objective"]),
                    "attempted": True,
                    "fit": trial,
                }
            )
        except Exception as error:
            final_trials.append(
                {
                    "seed_rank": seed_rank,
                    "seed_node_index": node["node_index"],
                    "seed_profile_objective": float(node["fit"]["objective"]),
                    "attempted": True,
                    "fit": None,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )

    finite_trials = [
        trial
        for trial in final_trials
        if trial["fit"] is not None and np.isfinite(trial["fit"].get("objective", np.nan))
    ]
    if not finite_trials:
        raise RuntimeError("no final local refinement produced a finite objective")
    best_trial = min(
        finite_trials,
        key=lambda trial: (trial["fit"]["objective"], trial["seed_rank"]),
    )
    converged = [trial for trial in finite_trials if trial["fit"]["success"]]
    converged_leader = (
        min(converged, key=lambda trial: (trial["fit"]["objective"], trial["seed_rank"]))
        if converged
        else None
    )
    selected_trial_converged = bool(best_trial["fit"]["success"])
    local_search_resolved = len(finite_trials) == finalist_count and all(
        trial["fit"]["success"] for trial in finite_trials
    )
    return {
        "rough_center_km": rough_center,
        "grid_offsets_km": offsets,
        "common_nuisance_initial_sha256": common_nuisance_sha256,
        "nodes": nodes,
        "finalists": [
            {
                "seed_rank": rank,
                "node_index": node["node_index"],
                "profile_objective": float(node["fit"]["objective"]),
            }
            for rank, node in enumerate(finalists)
        ],
        "final_trials": final_trials,
        "best_trial": best_trial,
        "converged_leader": converged_leader,
        "selected_satellite_indices": satellites,
        "selected_catalog_numbers": np.asarray(data.numbers)[satellites],
        "bank_selection_reevaluated": False,
        "bank_selection_rule": "sealed source score_leader",
        "selected_trial_converged": selected_trial_converged,
        "local_search_resolved": local_search_resolved,
        "success": local_search_resolved,
        "scope": (
            "Truth-free conditional local search over one bank selected by the sealed source fit. "
            "All grid nodes use identical source-leader RX/tau initialization; omitted taus are "
            "zero. Grid and final choices use finite objective only, never reference error."
        ),
    }


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_source_provenance(source_receipt):
    selection_sha256 = _digest(ROOT / "selection.json")
    if selection_sha256 != source_receipt["selection_sha256"]:
        raise ValueError("current selection digest does not match source receipt")
    unit = source_receipt["unit"]
    session_ids = set(unit["session_ids"])
    input_validation = {}
    for input_id, expected_sha256 in source_receipt["inputs"].items():
        if input_id in session_ids:
            folder = ROOT / "scans" / input_id
        elif input_id == unit["unit_id"]:
            folder = ROOT / "units" / input_id
        else:
            raise ValueError(f"source receipt contains unknown input {input_id!r}")
        manifest_path = folder / "bundle.json"
        manifest_sha256 = _digest(manifest_path)
        if manifest_sha256 != expected_sha256:
            raise ValueError(f"current bundle manifest digest mismatch for {input_id}")
        manifest = json.loads(manifest_path.read_text())
        bundle_sha256 = _digest(folder / "bundle.npz")
        expected_bundle_sha256 = manifest["artifacts"]["bundle_npz_sha256"]
        if bundle_sha256 != expected_bundle_sha256:
            raise ValueError(f"current bundle payload digest mismatch for {input_id}")
        input_validation[input_id] = {
            "bundle_manifest_sha256": manifest_sha256,
            "bundle_npz_sha256": bundle_sha256,
        }
    return {
        "selection_sha256": selection_sha256,
        "inputs": input_validation,
    }


def _position_error_km(common, point, reference):
    estimated = common.ecef(*common.coordinates(np.asarray(point, dtype=float)))
    expected = common.ecef(reference["latitude_deg"], reference["longitude_deg"])
    return float(np.linalg.norm(estimated - expected))


def run_unit(source_fit_path, run_id):
    source_fit_path = Path(source_fit_path)
    source_fit_sha256 = _digest(source_fit_path)
    source_receipt = json.loads(source_fit_path.read_text())
    if source_receipt.get("stage") != "coherent":
        raise ValueError("source must be one sealed coherent fit")
    unit = source_receipt["unit"]
    if unit.get("unit_id") != "DS10-S01" or unit.get("size") != 1:
        raise ValueError("this bounded diagnostic is restricted to DS10-S01")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one nonempty path component")
    source_validation = _validate_source_provenance(source_receipt)
    output = ROOT / "runs" / run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)

    session_id = unit["session_ids"][0]
    bundle = load_module(
        "profile_seed_bundle",
        ROOT.parent / "2026_10_02_localization_benchmark/bundle.py",
    )
    data = bundle.Data(ROOT / "scans" / session_id)
    started = time.monotonic()
    fitted = run_profile_seed(data, source_receipt)
    receipt = {
        "schema": "multiscan-profile-seed-fit/v1",
        "stage": "profile_seed",
        "dataset": source_receipt["dataset"],
        "unit": unit,
        "run_id": run_id,
        "source_fit": str(source_fit_path),
        "source_fit_sha256": source_fit_sha256,
        "source_selection_sha256": source_receipt["selection_sha256"],
        "source_inputs": source_receipt["inputs"],
        "source_validation": source_validation,
        "configuration": {
            "grid_offsets_km": list(GRID_OFFSETS_KM),
            "grid_shape": [5, 5],
            "node_budget_s": 3.0,
            "finalist_count": 3,
            "final_refine_budget_s": 20.0,
            "sigma_hz": 200.0,
            "track_contamination": 0.2,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
        },
        "source_hashes": {
            path.name: _digest(path)
            for path in sorted(ROOT.glob("*.py"))
            if not path.name.startswith("test_")
        },
        "truth_read_before_fit_seal": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    fit_sha256 = _digest(fit_path)

    reference_path = ROOT / "scans" / session_id / "evaluation.json"
    reference = json.loads(reference_path.read_text())["reference_site"]
    trial_errors = []
    for trial in fitted["final_trials"]:
        error = None
        if trial["fit"] is not None:
            error = _position_error_km(
                bundle._COMMON, trial["fit"]["parameters"][:2], reference
            )
        trial_errors.append(
            {
                "seed_rank": trial["seed_rank"],
                "seed_node_index": trial["seed_node_index"],
                "objective": None if trial["fit"] is None else trial["fit"]["objective"],
                "success": False if trial["fit"] is None else trial["fit"]["success"],
                "reference_error_km": error,
            }
        )
    evaluation = {
        "schema": "multiscan-profile-seed-evaluation/v1",
        "unit_id": unit["unit_id"],
        "dataset": source_receipt["dataset"],
        "fit_sha256": fit_sha256,
        "reference_evaluation_sha256": _digest(reference_path),
        "objective_selected_seed_rank": fitted["best_trial"]["seed_rank"],
        "trial_reference_errors": trial_errors,
        "scope": (
            "Post-seal reference evaluation only. Reference errors did not select the bank, grid "
            "nodes, finalists, or objective leader; all fits are conditional local searches."
        ),
    }
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    return receipt, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt, evaluation = run_unit(args.source_fit, args.run_id)
    print(
        json.dumps(
            {
                "run_id": receipt["run_id"],
                "unit_id": receipt["unit"]["unit_id"],
                "source_fit_sha256": receipt["source_fit_sha256"],
                "fit_sha256": evaluation["fit_sha256"],
                "elapsed_s": receipt["elapsed_s"],
                "best_objective": receipt["fit"]["best_trial"]["fit"]["objective"],
                "trial_reference_errors": evaluation["trial_reference_errors"],
            }
        )
    )


if __name__ == "__main__":
    main()
