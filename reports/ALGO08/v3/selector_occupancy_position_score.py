"""Independently read the two sealed private outcomes before scoring positions."""

import argparse
import json
from pathlib import Path

from aperture_trial import read, write
from dense_full_short_raw import checked
from joint_publication import artifacts
from leo.contracts.digests import canonical_digest
from leo.presentation.localization_v3 import owner_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from mixture_score import section
from north_interlaced_raw import NORTH, TRUTH_SHA
from selector_occupancy_position import ARMS, HERE, ORDER, REFERENCE_ROOTS, REFERENCE_SHA
from signed_0374_transfer import owner_changes
from tools.pipeline_eval.qualification.paired_publication import evidence


def read_arm(root, mode, binding):
    output = root / mode
    proof = read(output / "joint-research-receipt.json")
    marker = read(output / "RESEARCH-ONLY.json")
    seal = read(output / "occupancy-analysis.json")
    receipt = proof["receipt"]
    roster = binding["study"]["arms"][mode]
    source = binding["study"]["native"]
    selected = {oid for oid, state in roster["ledger"].items() if state["state"] == "observed"}
    native_path, = (output / "fast-scan-automatic-work").glob("*/detections.json")
    terminal = read(FastScanStore(output).automatic_workspace(receipt["run_id"], create=False) / "terminal.json")
    clock = read(root / f"{mode}-clock.json")
    verified = evidence(output, receipt, 0, read_only=True)
    media = json.loads(json.dumps(artifacts(output, receipt)))
    if (clock["status"] != 0 or any([marker["production"], marker["raw_reads"]])
            or receipt["region"] != binding["request"]["offered_region"]
            or verified["raw_authority"] != binding["request"]["raw_authority"]
            or proof["saved_handoff_manifest"] != binding["inventory"] or marker["route_requested"] != mode
            or native_path.read_bytes() != Path(binding["packet"]).read_bytes()
            or not (marker["native_input"] == source == proof["saved_digest"] == canonical_digest(read(native_path))
                    == seal["original_handoff"] == terminal["native_sha256"])
            or not (marker["analysis_projection"] == seal["projection"] == roster["projection"])
            or marker["states"] != roster["states"] or marker["mask"] != binding["study"]["mask"]
            or seal["observed_ids"] != canonical_digest(sorted(selected)) or seal["terminal"] != receipt["terminal_sha256"]
            or not (proof["evidence"] == seal["evidence"] == media)):
        raise ValueError("Private science or intact native source failed its readback")
    if receipt["decision"] == "complete":
        grid = FastStandardAnalysisStore(output).position_grid(receipt["run_id"])
        if not grid["complete"] or grid["evaluated_points"] != proof["solve"]["grid_points"] or len(media["images"]) != 8:
            raise ValueError("A successful arm must publish its complete grid and eight figures")
        for arm, rows in proof["selected_rows"].items():
            owners = {oid: sat for oid, sat, _ in rows}
            if len(owners) != len(rows) or not owners.keys() <= selected or owner_digest(owners) != verified["owners"][arm]:
                raise ValueError("A published owner did not correspond to a retained native observation")
    return dict(decision=receipt["decision"], terminal=receipt["terminal_sha256"], observation_states=roster["states"],
                original_detector_bytes_match=True,
                arms=verified["arms"], owner_digests=verified["owners"], owner_roles=proof["selected_roles"],
                selected_rows=proof["selected_rows"], science=verified["scientific_digests"], path_grid_images=media,
                early_geography=[row["result"] for row in proof["early_regional"]],
                exterior=proof["route_details"]["exterior"] if proof["route_details"] else None,
                route=proof["route"], process=clock, solve=proof["solve"], projection=seal["projection"])


def score(root):
    binding = read(root / "binding.json")
    if binding["order"] != list(ORDER) or root.stat().st_mode & 0o077:
        raise ValueError("Expected exactly the frozen private two-solve root")
    runs = {mode: read_arm(root, mode, binding) for mode in ORDER}
    truth_doc = read(checked(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    (truth,) = {tuple(v["truth"]) for v in truth_doc["answers"].values() if v["recording"] == NORTH}
    archive = {key: read(checked(HERE / "measurements" / key, value))["cases"] for key, value in REFERENCE_SHA.items()}
    controls = {"v3": archive["north-combined.json"]["stock"]["score"]["arms"],
                "unfiltered": archive["north-combined.json"]["containing"]["score"]["arms"],
                "history": archive["north-causal-transfer.json"]["containing"]["score"]["arms"]}
    expected = {"unfiltered": archive["north-combined.json"]["containing"]["terminal_sha256"],
                "history": archive["north-causal-transfer.json"]["containing"]["terminal"]}
    for mode, result in runs.items():
        original = read(REFERENCE_ROOTS[mode] / "joint-research-receipt.json")
        if original["receipt"]["terminal_sha256"] != expected[mode]:
            raise ValueError("Unperturbed original owner control no longer matches")
        result["position_vs_v3"] = section(result["arms"], truth, controls["v3"])
        result["position_vs_unperturbed_same_route"] = section(result["arms"], truth, controls[mode])
        result["owners_vs_unperturbed_same_route"] = owner_changes(original, result)
        result["passes"] = result["decision"] == "complete" and all(
            result["position_vs_v3"]["arms"][arm]["delta_error_km"] <= .25 for arm in ARMS)
    chosen, history = (runs[mode] for mode in ORDER)
    chosen_vs_history = section(chosen["arms"], truth, history["arms"])
    protects = chosen["passes"] and (not history["passes"] or all(
        chosen_vs_history["arms"][arm]["delta_error_km"] < 0. for arm in ARMS))
    return dict(input=binding, controls=controls, outcomes=runs, chosen_vs_history=chosen_vs_history,
                owners_chosen_vs_history=owner_changes(history, chosen), protects_both_arm_accuracy=protects)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    write(args.output, score(args.root))
