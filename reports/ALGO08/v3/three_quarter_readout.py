"""Score the sealed saved publication and price keeping full acquisition authentication."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from three_quarter_members import ARMS, FIELD, ROOT, checked, digest, gates, read, write  # noqa: E402
from three_quarter_saved import CASE, STAGE  # noqa: E402


def full_auth_model(audit, field=FIELD):
    case_costs = {}
    for row in audit["records"]:
        case = row["case"]
        if not row["matched_original_counterfactual"]:
            case_costs[case] = dict(without_solver=row["successor_s"], linear_solver=row["successor_s"])
            continue
        pair = read(field / "cases" / case / "pair.json")
        source = field / "cases" / case / "successor" / f"attempt-{pair['generation']:06d}"
        result = read(source / "result.json", row["result_pins"][1])
        correct = read(source / "publication/unified-short-bootstrap.json")
        if correct["native_sha256"] != result["native_sha256"] or correct["native_sha256"] != row["historical_final_native_sha256"]:
            raise ValueError("The measured dispatch changed before timing readout")
        native = correct["receiver_audit"]["native"]
        physical = row["physical"]
        credit = sum(native["native_wall_ns"].get(role, 0)*1e-9*count/native["native_calls"][role] if count else 0.
                     for role, count in physical["dropped_lanes"].items())
        linear_solve_credit = row["model"]["measured_solve_wall_s"] * physical["factors_omitted"] / max(physical["factors_total"], 1)
        baseline = row["successor_s"]
        case_costs[case] = dict(detector_only_wall_credit=credit, without_solver=baseline-credit,
                               linear_solver=baseline-credit-linear_solve_credit,
                               solver_needed_for_half=max(baseline-credit-row["installed_s"]/2, 0))
    gate = {mode: gates(audit["records"], [case_costs[row["case"]][mode] for row in audit["records"]])
            for mode in ("without_solver", "linear_solver")}
    return dict(fully_preserved_authentication=True, case_costs=case_costs, gates=gate)


def score(inputs, solved, output):
    import json

    from clean_saved_0169_trial import output_seal
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.scoring import distance_km

    audit = read(inputs / "audit.json")
    conservative = full_auth_model(audit)
    admission = read(solved / "admission.json")
    if read(solved / "prediction-seal.json") != output_seal(solved):
        raise ValueError("The saved prediction changed before scoring")
    source = admission["scope"]
    trial = read(solved / "worker.json")
    actual = trial["terminal"]
    if actual["decision"] != "complete" or trial["handoffs"] != 1 or trial["waveform_reads"] or trial["survey_reads"]:
        raise ValueError("The one charged saved result did not publish a complete scientific pair")
    media = artifacts(solved / "candidate", actual)
    store = FastStandardAnalysisStore(solved / "candidate")
    grid = store.position_grid(actual["run_id"])
    detail = store.detail(actual["run_id"])
    if not grid["complete"] or len(grid["points"]) != 179 or len(media["images"]) != 8 or set(detail["arms"]) != set(ARMS):
        raise ValueError("Both paid arms, 179 grid positions and eight images are required")
    if media["grid"] != trial["result_evidence"]["sidecars"]["grid"] or media["path"] != trial["result_evidence"]["sidecars"]["path"]:
        raise ValueError("Independent standard sidecar digests differ from the sealed publication")
    auth = admission["authority"]
    reference_file = ROOT / "reports/2026_11_21_ds30_full/reference-audit.json"
    reference, = (row["reference"] for row in json.loads(checked(reference_file, "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"))["cases"]
                  if row["dataset_label"] == CASE and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [reference["latitude_deg"], reference["longitude_deg"]]
    pair = FIELD / "cases" / CASE
    controls = {name: read(pair / name / "attempt-000001/result.json", pin)
                for name, pin in zip(("installed", "successor"), source["result_pins"], strict=True)}
    result = {}
    for name, entry in controls.items():
        if entry["raw_identity"] != auth or entry["evidence"]["receipt"]["region"] != actual["region"]:
            raise ValueError("Comparison does not retain the same enrolled authority and original offer")
        result[name] = {arm: dict(row, error_km=distance_km(truth, row["latlon"])) for arm, row in entry["evidence"]["arms"].items()}
    result["three_quarter"] = {arm: dict(latlon=row["endpoint_latlon"], rf_rms_hz=row["residual_rms_hz"],
                                        error_km=distance_km(truth, row["endpoint_latlon"])) for arm, row in detail["arms"].items()}
    # The published terminal RF boundary reports the same calibrated numbers as the field receipts.
    from tools.pipeline_eval.qualification.paired_publication import evidence

    paid = evidence(solved / "candidate", actual, (solved / "admission.json").stat().st_mtime_ns, read_only=True)
    if paid["raw_authority"] != auth["raw_authority_sha256"]:
        raise ValueError("The scientific publication lost parent raw authority")
    for arm, row in paid["arms"].items():
        if row["latlon"] != result["three_quarter"][arm]["latlon"]:
            raise ValueError("Published endpoint differs from the scored coordinate")
        result["three_quarter"][arm]["all_owned_rf_rms_hz"] = result["three_quarter"][arm]["rf_rms_hz"]
        result["three_quarter"][arm]["rf_rms_hz"] = row["rf_rms_hz"]
    old_saved = read(STAGE / "ordinary-receipt.json")
    old_saved_witness = read(STAGE / "ordinary/exact-named-raw-witness.json", old_saved["witness_sha256"])
    (solve,) = trial["analysis"]["solve"]
    (ordinary_solve,) = old_saved_witness["timing"]["solve"]
    wall_delta = ordinary_solve["elapsed_s"] - solve["elapsed_s"]
    models = source["model"]
    original_includes_intake = source["successor_s"]
    projected = {"explicit_member_omission": original_includes_intake-models["mean_share_acquisition_credit_wall_s"]-wall_delta,
                 "all_payload_authentication": conservative["case_costs"][CASE]["without_solver"]-wall_delta}
    write(output, dict(case=CASE, saved_clock=trial["timing"], original_saved_clock=old_saved["timing"], matched_solve=solve,
                      original_saved_solve=ordinary_solve, original_field_solve_wall_s=models["measured_solve_wall_s"],
                      wall_solver_credit=wall_delta, ratios_with_0086_solver_credit={key: value/source["installed_s"] for key,value in projected.items()},
                      modeled_0086_raw_wall_s=projected, saved_science=result, qualification=dict(grid=179, figures=8, handoffs=1),
                      candidate_owner_counts={arm: len(rows) for arm, rows in trial["result_evidence"]["owner_rows"].items()},
                      preserved_full_auth_model=conservative, source_sha256=digest(audit)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("inputs", type=Path)
    cli.add_argument("saved", type=Path)
    cli.add_argument("output", type=Path)
    paths = cli.parse_args()
    score(paths.inputs, paths.saved, paths.output)
