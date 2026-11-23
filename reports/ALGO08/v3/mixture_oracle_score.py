"""Summarize rejected membership oracles and their complete numerical cost."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from leo.analysis.position_grid import sample_position_grid

from aperture_score import face_clearance_km, references
from mixture_oracle_trial import WITNESS, WITNESS_SHA256
from mixture_score import BUDGET_CPU_S, section
from mixture_trial import CASES


def blind_agreement(proposal, exact):
    original = {oid: track for track in proposal["arms"]["c0"]["tracks"] for oid in track["observations"]}
    overlap = [(original[oid], label) for oid, label in exact.items()
               if oid in original and original[oid]["retained"]]
    owner_labels = [(track, label) for track, label in overlap if track["norad"] == label[0]]
    return dict(
        retained_stock_conditional=len(overlap), different_owner=len(overlap) - len(owner_labels),
        same_owner_different_alias=sum(track["alias"] != label[1] for track, label in owner_labels),
        same_owner_and_alias=sum(track["alias"] == label[1] for track, label in owner_labels),
    )


def compare(case, receipt, truth, proposal, exact):
    terminal = receipt["control"]
    contained = face_clearance_km(receipt["identity"]["offer"], truth) >= 0.
    baseline = section(terminal["arms"], truth, terminal["arms"])
    cost_to_label = receipt["stock_inference_and_label_capture_clocks"]["cpu_s"]
    prepare = receipt["imported_blind_shared_prep_other_cpu_s"]
    cold = receipt["imported_blind_proposal_clocks"]["cpu_s"]
    reconstruct = receipt["frozen_endpoint_clocks"]["cpu_s"]
    stages = {}
    for mode, result in receipt["oracle"].items():
        row = result["finish"]
        scored = section(row.get("arms", {}), truth, terminal["arms"])
        evidence = result["numerical_evidence"] or {}
        observed = evidence.get("grid_calls", [])
        plan = None if not row.get("arms") else sample_position_grid(
            lambda _arm, _point: 0., {arm: r["east_north_km"] for arm, r in row["arms"].items()},
            box_width_km=receipt["identity"]["offer"]["width_km"],
        )["planned_points"]
        grid_complete = len(observed) == 1 and observed[0]["evaluated_points"] == plan
        numerical_cost = sum(v["cpu_s"] for key, v in evidence.items() if key.endswith("_clocks"))
        minimum_total = prepare + cold + reconstruct + result["assignment_clocks"]["cpu_s"] + result["finish_clocks"]["cpu_s"] + numerical_cost
        terminal_possible = contained and row["decision"] == "complete" and evidence.get("status") == "complete" and grid_complete
        error_pass = contained and all(r["delta_error_km"] is not None and r["delta_error_km"] <= .25
                                       for r in scored["arms"].values())
        stages[mode] = dict(
            counts=result["counts"], rejection_reasons=row["reasons"], score=scored,
            validation_arms=row.get("arms", {}), validation_clocks=result["finish_clocks"],
            assignment_clocks=result["assignment_clocks"], evidence=evidence, planned_grid_points=plan,
            grid_complete=grid_complete, terminal_possible=terminal_possible, error_pass=error_pass,
            free_label_cpu_s=minimum_total,
            cpu_s_with_full_stock_inference=minimum_total + cost_to_label,
            under_24s_dense_budget=None if case != "DS30-0008" else minimum_total <= BUDGET_CPU_S,
        )
    return dict(contained=contained, baseline=baseline, baseline_status=terminal["status"], modes=stages,
                blind_agreement=blind_agreement(proposal, exact),
                frozen_endpoint_clocks=receipt["frozen_endpoint_clocks"], cold_proposal_clocks=receipt["imported_blind_proposal_clocks"],
                stock_inference_and_label_capture_clocks=receipt["stock_inference_and_label_capture_clocks"],
                entire_diagnostic_clocks=receipt["entire_diagnostic_clocks"],
                transferred=receipt.get("label_transfer"), stock_roles=receipt.get("labels", {}).get("roles"))


def score(directory, summary, full):
    truth = references()
    frozen = WITNESS.read_bytes()
    if sha256(frozen).hexdigest() != WITNESS_SHA256:
        raise ValueError("The frozen mixture receipt changed")
    previous = json.loads(gzip.decompress(frozen))["receipts"]
    receipts, pins, comparison = {}, {}, {}
    for case in CASES:
        raw = (directory / f"{case}.json").read_bytes()
        receipt = json.loads(raw)
        receipts[case], pins[case] = receipt, sha256(raw).hexdigest()
    for case, receipt in receipts.items():
        exact = receipts["south-containing" if case == "south-far" else case]["labels"]["curved"]
        comparison[case] = compare(case, receipt, truth[case], previous[case]["attempts"][0]["proposal"], exact)
    with summary.open("x") as stream:
        json.dump(dict(cases=comparison, receipt_sha256=pins), stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(cases=receipts, receipt_sha256=pins), allow_nan=False,
                                             sort_keys=True, separators=(",", ":")).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "summary", "full"):
        parser.add_argument(name, type=Path)
    score(**vars(parser.parse_args()))
