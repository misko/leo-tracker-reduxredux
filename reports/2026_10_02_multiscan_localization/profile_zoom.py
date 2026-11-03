"""Refine a likelihood-selected coarse cell without reading reference coordinates."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood
from gauss_newton import refine_gauss_newton
from profile_seed import _validate_source_provenance
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import frozen_row_weights
from track_likelihood import prepare_track_grouped_likelihood


def zoom_center(coarse):
    finite = [
        node
        for node in coarse["nodes"]
        if node.get("fit") is not None and np.isfinite(node["fit"]["objective"])
    ]
    if not finite:
        raise ValueError("No finite coarse-grid objectives")
    selected = min(finite, key=lambda node: (node["fit"]["objective"], node["node_index"]))
    return np.asarray(selected["position_km"], dtype=float), selected["node_index"]


def fit_zoom(data, source, coarse):
    center, source_node = zoom_center(coarse)
    leader = source["score_leader"]
    satellites = np.asarray(leader["satellite_indices"], dtype=int)
    initial = np.asarray(leader["parameters"], dtype=float)
    masses = leader["identity_masses"]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in source["anchors"]],
    )
    nodes = []
    offsets = np.linspace(-2.5, 2.5, 5)
    for east in offsets:
        for north in offsets:
            point = center + [east, north]
            fitted = refine_gauss_newton(
                data,
                initial.copy(),
                satellites,
                np.ones(len(satellites)),
                FixedBankLikelihood(prepared, masses),
                sigma_hz=200,
                budget_s=3,
                fixed_position_km=point,
            )
            nodes.append({"node_index": len(nodes), "position_km": point, "fit": fitted})
    finite = [node for node in nodes if np.isfinite(node["fit"]["objective"])]
    finalists = sorted(finite, key=lambda node: (node["fit"]["objective"], node["node_index"]))[:3]
    if len(finalists) != 3:
        raise ValueError("Fewer than three finite zoom nodes")
    trials = []
    for node in finalists:
        fitted = refine_gauss_newton(
            data,
            node["fit"]["parameters"].copy(),
            satellites,
            np.ones(len(satellites)),
            FixedBankLikelihood(prepared, masses),
            sigma_hz=200,
            budget_s=15,
        )
        trials.append({"seed_node_index": node["node_index"], "fit": fitted})
    incumbent = {"seed_node_index": None, "fit": leader}
    selected = min([incumbent, *trials], key=lambda trial: trial["fit"]["objective"])
    return {
        "center_km": center,
        "coarse_node_index": source_node,
        "offsets_km": offsets,
        "nodes": nodes,
        "final_trials": trials,
        "selected": selected,
        "selected_trial_converged": bool(selected["fit"]["success"]),
        "local_search_resolved": all(trial["fit"]["success"] for trial in trials),
        "bank_selection_reevaluated": False,
        "incumbent_retained": selected is incumbent,
        "scope": "One frozen bank. Fine grid centered on minimum coarse profile objective, "
        "not on reference coordinates or free-position output. All 25 nodes share identical "
        "source RX/tau initialization. Objective selects three free refinements and incumbent.",
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fit", type=Path, required=True)
    parser.add_argument("--coarse-fit", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
        parser.error("run-id must be one path component")
    source = json.loads(args.source_fit.read_text())
    coarse = json.loads(args.coarse_fit.read_text())
    if coarse["source_fit_sha256"] != digest(args.source_fit) or coarse["unit"] != source["unit"]:
        raise ValueError("Coarse fit is not bound to this source fit and unit")
    _validate_source_provenance(source)
    unit = source["unit"]
    if unit["size"] != 1:
        raise ValueError("Zoom pilot currently requires a single scan")
    output = ROOT / "runs" / args.run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        path.name: digest(path) for path in ROOT.glob("*.py") if not path.name.startswith("test_")
    }
    bundle = load_module("zoom_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py")
    session = unit["session_ids"][0]
    data = bundle.Data(ROOT / "scans" / session)
    started = time.monotonic()
    fitted = fit_zoom(data, source["fit"], coarse["fit"])
    receipt = {
        "stage": "profile_zoom",
        "unit": unit,
        "dataset": source["dataset"],
        "source_fit_sha256": digest(args.source_fit),
        "coarse_fit_sha256": digest(args.coarse_fit),
        "source_hashes": sources,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "eligible_for_cohort": False,
        "reference_read_before_seal": False,
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    truth = json.loads((ROOT / "scans" / session / "evaluation.json").read_text())["reference_site"]
    position = fitted["selected"]["fit"]["parameters"][:2]
    error = float(
        np.linalg.norm(
            bundle._COMMON.ecef(*bundle._COMMON.coordinates(position))
            - bundle._COMMON.ecef(truth["latitude_deg"], truth["longitude_deg"])
        )
    )
    evaluation = {
        "unit_id": unit["unit_id"],
        "fit_sha256": digest(fit_path),
        "reference_error_km": error,
        "objective": fitted["selected"]["fit"]["objective"],
        "selected_trial_converged": fitted["selected_trial_converged"],
        "local_search_resolved": fitted["local_search_resolved"],
        "elapsed_s": receipt["elapsed_s"],
        "eligible_for_cohort": False,
    }
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    print(json.dumps(evaluation))


if __name__ == "__main__":
    main()
