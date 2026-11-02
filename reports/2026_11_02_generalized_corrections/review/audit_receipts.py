"""Independent RF receipt/decision audit; no position fits or geography reads."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent
ARMS = ("c0", "fitted_c")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def fallback(record):
    return {arm: dict(source="exact_saved_ALGO07",
        objective=record["baseline"][arm]["objective"],
        associated=record["baseline"][arm]["associated"],
        selected_replacement=record["selected"]) for arm in ARMS}


def selected(record, endpoints, source):
    return {arm: dict(source=source, x=endpoints[arm]["x"],
        reference=endpoints[arm]["reference"],
        objective=endpoints[arm]["objective"], rms_hz=endpoints[arm]["rms_hz"],
        associated=record["baseline"][arm]["associated"]) for arm in ARMS}


def paired(rows):
    return set(rows) == set(ARMS) and all(rows[a].get("qualified") for a in ARMS)


def projection_pass(guard):
    """Recompute the frozen engineering decision from continuous RF quantities."""
    if guard.get("status") != "complete":
        return False
    policy = guard["policy"]
    for key, expected in dict(noise_sigma_hz=150., minimum_other_families=3,
            minimum_displacement_information=4., minimum_projected_RF_gain=4.,
            minimum_leave_one_family_out_information=1.,
            minimum_leave_one_family_out_RF_gain=0.,
            column_scaled_relative_SVD_cutoff=1e-10).items():
        require(policy[key] == expected, "C receipt changed frozen engineering policy")
    full = guard["full"]
    minimums = (
        len(guard["other_families"]) >= policy["minimum_other_families"],
        full["displacement_information"] >= policy["minimum_displacement_information"],
        full["projected_RF_gain"] >= policy["minimum_projected_RF_gain"],
        all(item["displacement_information"] >= policy["minimum_leave_one_family_out_information"]
            for item in guard["leave_one_family_out"]),
        all(item["projected_RF_gain"] >= policy["minimum_leave_one_family_out_RF_gain"]
            for item in guard["leave_one_family_out"]),
        "other_family_nominal_prediction_below_horizon" not in guard["reasons"],
    )
    require(len(guard["leave_one_family_out"]) == len(guard["other_families"]),
            "Missing family-deletion counterfactual")
    for item in [full] + guard["leave_one_family_out"]:
        require(item["displacement_information"] >= -1e-10, "Negative RF information")
        delta = item["control_profile_quadratic"] - item["candidate_profile_quadratic"]
        require(abs(delta - item["projected_RF_gain"]) <= 1e-7 * max(1., abs(delta)),
                "Projection RF contrast arithmetic differs")
        require(0 <= item["residual_dimension"] <= item["points"], "Invalid residual rank")
        require(item["nuisance_rank"] + item["residual_dimension"] == item["points"],
                "Projection rank arithmetic differs")
    require(not policy["prior_sensitivity_changes_guard"], "Prior sensitivity changed guard")
    require(not guard["target_fitted_hardware_used"] and not guard["saved_phase_references_used"]
            and not guard["GPS_used"], "Forbidden guard conditioning")
    return all(minimums)


def endpoint_checks(row, baseline, policy):
    require(row["status"] == "complete", "Qualified endpoint is incomplete")
    require(row["optimizer_success"] and row["phase_closed"] and row["central_stationary"],
            "Qualified endpoint fails numerical state")
    require(np.isfinite(row["final_inner_precision_change"])
            and row["final_inner_precision_change"] <= 1e-5,
            "Qualified endpoint has unconverged precision")
    require(row["phase_change_s"] <= .01 and not row["boundary"], "Qualified phase or boundary failure")
    final = row["history"][-1]
    raw_phase_gap = float(np.max(abs(np.asarray(final["posterior_phase"])
                                    - np.asarray(final["reference"]))))
    require(raw_phase_gap <= .01 and abs(raw_phase_gap - row["phase_change_s"]) <= 1e-12,
            "Raw posterior phase/reference gap differs")
    require(row["final_gradient"]["stable"] and row["final_gradient"]["finite"]
            and row["final_gradient"]["projected_gradient_inf"] <= 1e-4,
            "Final central gradient is not stationary")
    require(all(row["flags"].values()), "Qualified endpoint has failed flag")
    require(abs(row["objective_replay_difference"]) <= 1e-4, "Objective replay mismatch")
    require(row["native_inventory"]["native_ids_sha256"] == baseline["native_ids_sha256"],
            "Qualified native observation union changed")
    require(row["native_inventory"]["fitted_owners_sha256"] == baseline["fitted_owners_sha256"],
            "Qualified native ownership changed")
    require(len(row["history"]) <= policy["max_rounds"], "Phase round budget exceeded")
    for round_ in row["history"]:
        solver = round_["position_solver"]
        require(solver["actual_objective_calls"] <= solver["max_actual_calls"],
                "Actual objective-call ceiling exceeded")
        require(solver["max_actual_calls"] <= policy["max_actual_calls"],
                "Per-reference objective-call ceiling changed")


def audit_case(record, result, configuration):
    case = record["case"]
    require(record["input_sha256"] == result["input_sha256"], case + ": input receipt differs")
    require(sha(record["input_path"]) == record["input_sha256"], case + ": native input changed")
    variants = result["variants"]
    a, b, c = [variants[k] for k in ("A", "A+B", "A+B+C")]
    ar, br = a.get("raw_endpoints", {}), b.get("raw_endpoints", {})
    diagnostics = result.get("numerical_trigger_diagnostics", {})
    expected_a = bool(paired(ar) and any(v["trigger"] for v in diagnostics.values())
        and all(ar[arm]["saved_arm_position_objective_at_final_reference"] - ar[arm]["objective"]
                >= -configuration["A_objective_nondegradation_tolerance"] for arm in ARMS))
    expected_b = bool(paired(br) and b.get("prior_receipt", {}).get("status") == "ready")
    guards = c.get("geometry_guards", {})
    guard_pass = {}
    for arm, value in guards.items():
        guard_pass[arm] = projection_pass(value)
        require(value["guard_pass"] == guard_pass[arm], case + ": C diagnostic decision differs")
    expected_c = bool(b["accepted"] and set(guards) == set(ARMS)
                      and all(guard_pass.values()))
    # A decision can be absent when the execution window ends before that stage.
    if "raw_endpoints" in a:
        require(a["accepted"] == expected_a, case + ": A decision differs")
    else:
        require(not a["accepted"], case + ": A accepted without endpoints")
    if "raw_endpoints" in b:
        require(b["accepted"] == expected_b, case + ": B decision differs")
    else:
        require(not b["accepted"], case + ": B accepted without endpoints")
    require(c["accepted"] == expected_c, case + ": C decision differs")
    for rows in (ar, br):
        for arm, endpoint in rows.items():
            if endpoint.get("qualified"):
                endpoint_checks(endpoint, result["baseline_replay"][arm], configuration["solver"])
    output_a = selected(record, ar, "A_numerical_repair") if a["accepted"] else fallback(record)
    output_b = selected(record, br, "A+B_causal_covariance") if b["accepted"] else output_a
    output_c = selected(record, br, "A+B+C_guarded_causal_covariance") if c["accepted"] else output_a
    for label, expected in [("A", output_a), ("A+B", output_b), ("A+B+C", output_c)]:
        require(variants[label]["selected_output"] == expected, case + ": selected fallback differs " + label)
    receipt = result.get("prior_receipt", {})
    if receipt.get("status") == "ready":
        covariance = np.asarray(receipt["coefficient_covariance"])
        eigen = np.linalg.eigvalsh(covariance)
        require(np.allclose(covariance, covariance.T, atol=1e-10), case + ": covariance not symmetric")
        require(eigen.min() >= 1-1e-9 and eigen.max() <= 16+1e-9, case + ": covariance bounds differ")
        require(receipt["selected_epochs"] >= 3 and receipt["selected_span_hours"] >= 12,
                case + ": insufficient causal-history support")
        require(receipt["represented_energy_fraction"] >= .5, case + ": unsupported history projection")
        require(all(v["alignment_converged"] for v in receipt["historical_projection"]),
                case + ": historical phase alignment did not converge")
        require(not receipt["RF_or_GPS_used_for_covariance"], case + ": covariance uses RF/GPS")
    return dict(case=case, status=result["status"],
                accepted={k:bool(variants[k]["accepted"]) for k in variants},
                completed_endpoints=sum(r.get("status") == "complete" for rows in (ar, br) for r in rows.values()),
                qualified_endpoints=sum(bool(r.get("qualified")) for rows in (ar, br) for r in rows.values()),
                guard_arms=len(guards), covariance_ready=receipt.get("status") == "ready")


def audit(protocol_path, result_path, destination):
    protocol, results = read(protocol_path), read(result_path)
    configuration = protocol["evaluation"]
    require(results["protocol_sha256"] == sha(protocol_path), "Protocol/result binding differs")
    for path, expected in protocol["source_sha256"].items():
        require(sha(path) == expected, "Frozen source differs: " + path)
    roster_path = configuration["roster_path"]
    require(sha(roster_path) == configuration["roster_sha256"] == results["roster_sha256"], "Roster hash differs")
    roster = read(roster_path)
    cases = {r["case"]:r for r in roster["cases"]}
    require(len(cases) == len(results["rows"]), "Result coverage differs")
    require(set(cases) == {r["case"] for r in results["rows"]}, "Result case set differs")
    checks = []
    for result in results["rows"]:
        require(result["protocol_sha256"] == sha(protocol_path), "Case protocol binding differs")
        checks.append(audit_case(cases[result["case"]], result, configuration))
    output = dict(status="passed", no_position_fit=True, no_GPS_read=True,
        protocol_sha256=sha(protocol_path), results_sha256=sha(result_path),
        roster_sha256=sha(roster_path), auditor_sha256=sha(__file__), cases=len(checks),
        accepted={label:sum(row["accepted"][label] for row in checks) for label in ("A", "A+B", "A+B+C")},
        status_counts=dict(Counter(row["status"] for row in checks)),
        completed_endpoints=sum(r["completed_endpoints"] for r in checks),
        qualified_endpoints=sum(r["qualified_endpoints"] for r in checks),
        geometry_guard_arms=sum(r["guard_arms"] for r in checks),
        causal_covariances_ready=sum(r["covariance_ready"] for r in checks),
        case_checks=checks)
    Path(destination).write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k:v for k,v in output.items() if k != "case_checks"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--results", type=Path, default=REPORT/"evaluation/results.json")
    parser.add_argument("--output", type=Path, default=ROOT/"receipt_audit.json")
    args = parser.parse_args()
    audit(args.protocol, args.results, args.output)
