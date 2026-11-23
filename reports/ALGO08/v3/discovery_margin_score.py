"""Independently score the fixed unit and weighted saved publications."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean

from aperture_trial import ARMS, read, write
from dense_full_short_raw import checked
from discovery_margin import THRESHOLD
from discovery_margin_trial import SOLVE_ORDER
from eight_ms_crossover import PACKET_PINS, RAW_REPORT_PINS, originals
from eight_ms_physical_score import quality
from joint_publication import artifacts
from leo.contracts.digests import canonical_digest
from leo.presentation.localization_v3 import owner_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from mixture_score import section
from signed_0374_transfer import owner_changes
from tools.pipeline_eval.qualification.paired_publication import evidence


HERE = Path(__file__).resolve().parent


def read_run(root, mode, binding, graph, shape, prior):
    out = root / mode
    proof = read(out / "joint-research-receipt.json")
    seal = read(out / "discovery-margin.json")
    clock = read(root / f"{mode}-clock.json")
    receipt = proof["receipt"]
    result = evidence(out, receipt, 0, read_only=True)
    publication = json.loads(json.dumps(artifacts(out, receipt)))
    detector, = (out / "fast-scan-automatic-work").glob("*/detections.json")
    terminal = FastScanStore(out).automatic_workspace(receipt["run_id"], create=False) / "terminal.json"
    expected = PACKET_PINS[binding["case"]][1]
    traces = [row for row in graph["trials"] if row["mode"] == mode]
    if (clock["status"] != 0 or receipt["region"] != binding["request"]["offered_region"]
            or receipt["session_id"] != binding["request"]["session"] or receipt["counts"] != prior["counts"]
            or result["raw_authority"] != binding["request"]["raw_authority"]
            or not expected == canonical_digest(read(detector)) == read(terminal)["native_sha256"] == proof["saved_digest"]
            or proof["saved_handoff_manifest"] != binding["inventory"] or seal["mode"] != mode
            or seal["threshold"] != THRESHOLD or seal["terminal"] != receipt["terminal_sha256"]
            or seal["graph"] != shape["solver_shape"] or any(seal["observations"] != trace["observations"]
                                                               or trace["graph"] != shape["graph"] for trace in traces)
            or any(seal["counts"]["path_calls"] != trace["paths"]["native_paths"] for trace in traces)
            or publication != proof["evidence"]):
        raise ValueError(f"{mode} altered an invariant of the saved publication")
    if receipt["decision"] == "complete":
        grid = FastStandardAnalysisStore(out).position_grid(receipt["run_id"])
        if not grid["complete"] or grid["evaluated_points"] != prior["grid_points"] or len(publication["images"]) != 8:
            raise ValueError(f"{mode} omitted its standard grid or figures")
        for arm, rows in proof["selected_rows"].items():
            owned = {oid: sat for oid, sat, _ in rows}
            if len(owned) != len(rows) or owner_digest(owned) != result["owners"][arm]:
                raise ValueError(f"{mode} owner rows disagree with the published ownership")
    return dict(decision=receipt["decision"], reason=result["reason"], arms=result["arms"], owners=result["owners"],
                science=result["scientific_digests"], process=clock, terminal=receipt["terminal_sha256"],
                native_sha256=expected, path_grid_images=publication, reward=seal, solve=proof["solve"],
                roles=proof["selected_roles"], output=str(out), run_id=receipt["run_id"]), proof


def score(root, graph_trial, solver_shape):
    binding, graph = read(root / "binding.json"), read(graph_trial)
    shape = read(solver_shape)
    case = binding["case"]
    original, _, _ = originals(case, ("8ms",))
    if (binding["request"] != original["request"] or binding["inventory"] != original["inventory"]
            or graph["case"] != case or binding["order"] != list(SOLVE_ORDER)
            or any(graph[k] != shape[k] for k in ("case", "packet_sha256", "weighted_native_sha256", "threshold"))
            or binding["graph_trial_sha256"] != sha256(graph_trial.read_bytes()).hexdigest()):
        raise ValueError("Saved and Graph comparisons use different frozen assignments")
    archived = read(checked(HERE / f"measurements/eight-ms-{case}.json", RAW_REPORT_PINS[case]))
    known = archived["runs"]
    controls = {name: known[name]["errors_km"] for name in ("v3", "12ms")}
    report = {}
    proofs = {}
    for mode in SOLVE_ORDER:
        shape_for_mode, = [row for row in shape["trials"] if row["mode"] == mode]
        report[mode], proofs[mode] = read_run(root, mode, binding, graph, shape_for_mode, known["8ms"])
        row = report[mode]
        row["position"] = section(row["arms"], archived["survey"], known["v3"]["arms"])
        row["development_gate"] = quality({arm: row["position"]["arms"][arm]["error_km"] for arm in ARMS},
                                          controls, complete=row["decision"] == "complete")
    unit, exact = report["unit"], known["8ms"]
    if (unit["arms"] != exact["arms"] or unit["owners"] != exact["owner_sha256"]
            or unit["decision"] != exact["decision"] or unit["terminal"] != exact["terminal_sha256"]
            or unit["science"] != exact["scientific_digests"] or unit["path_grid_images"]["images"] != exact["publication"]["images"]):
        raise ValueError("Unit rewards did not reproduce original 8 ms science and figures")
    runtimes = {mode: mean(row["clocks"]["cpu_s"] for row in graph["trials"] if row["mode"] == mode)
                for mode in ("stock", *SOLVE_ORDER)}
    return dict(case=archived["case"], binding=binding, graph=graph, graph_mean_cpu_s=runtimes,
                comparison=report, owners_vs_unit=owner_changes(proofs["unit"], proofs["weighted"]),
                reference_errors_km=controls, reference_sha256=RAW_REPORT_PINS[case],
                solver_shape=shape)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "graph_trial", "solver_shape", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    write(args.output, score(args.root, args.graph_trial, args.solver_shape))
