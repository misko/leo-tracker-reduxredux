"""Postfit-only bounded saved-endpoint verification. No optimization or GPS.

This auditor is intentionally outside the inference source seal. It reads the
sealed RF result, evaluates saved endpoints and copied-data perturbations, and
records its own hash. It never changes any inference source or receipt.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import signal
import time

import numpy as np

from algo07_science import engine as e
from algo07_science.diagnose import objective
from algo07_science.validation import clean
from audit_receipts import read, require, sha


ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def independent_profile(y, m0, m1, u0, u1):
    """Least-squares residualization, independently of guard.project_support."""
    union = np.column_stack((u0, u1))
    length = np.linalg.norm(union, axis=0)
    union = union[:, length > 0] / length[length > 0]
    vectors = np.column_stack(((y-m0)/150., (m1-m0)/150.))
    fitted = union @ np.linalg.lstsq(union, vectors, rcond=1e-10)[0]
    r, s = (vectors-fitted).T
    return dict(displacement_information=float(s@s), projected_RF_gain=float(2*r@s-s@s))


def copied_target_perturbation(d, target):
    scan = copy.copy(d["scan"])
    scan.tracks = list(scan.tracks)
    p = d["problems"]["fitted_c"][0]
    indices = {i for i, row in zip(p.members, p.rows) if row["candidate_norad"] == target}
    for index in indices:
        track = dict(scan.tracks[index])
        track["values"] = np.asarray(track["values"]) + 1e6
        scan.tracks[index] = track
    require(bool(indices), "No target observations reached perturbation")
    return dict(d, scan=scan), len(indices)


def check_case(record, result, numerical, covariance, guard, evidence):
    case = record["case"]
    input_root = Path(record["input_path"]).parent.parent
    e.configure(input_root, ROOT/"replay_contexts"/case)
    e.ROOTS[case[:4]] = input_root
    d, z, _ = e.load_case(case)
    prior = result.get("prior_receipt", {})
    dd = d
    if prior.get("status") == "ready":
        dd, receipt = covariance.candidate_context(d, z, dict(selected_family=result["target_family"]))
        require(receipt["status"] == "ready", "Causal covariance replay became unsupported")
        require(np.array_equal(receipt["coefficient_covariance"], prior["coefficient_covariance"]),
                "Causal covariance differs on replay")
    rows = []
    for label, context in [("A", d), ("A+B", dd)]:
        for arm, row in result["variants"][label].get("raw_endpoints", {}).items():
            if row.get("status") != "complete":
                continue
            x = np.asarray(row["x"])
            p, ctx = e.build(context, z, arm, np.asarray(row["reference"]))
            cost = lambda at: objective(p, ctx, at)
            delta = float(cost(x) - row["objective"])
            require(abs(delta) <= 1e-4, "Endpoint objective replay differs")
            phases = np.asarray(p.state(x)["phases"])[p.labels]
            gap = float(max(abs(phases-p.reference)))
            require(abs(gap - row["phase_change_s"]) < 1e-10, "Raw phase replay differs")
            gradient = numerical.gradient_probe(cost, x)
            require(abs(gradient["projected_gradient_inf"]
                        - row["final_gradient"]["projected_gradient_inf"]) <= 1e-7,
                    "Endpoint gradient replay differs")
            inventory = evidence.native_inventory(p, ctx)
            require(inventory["native_ids_sha256"] == row["native_inventory"]["native_ids_sha256"],
                    "Native IDs differ on replay")
            rows.append(dict(model=label, arm=arm, objective_difference=delta,
                phase_gap_s=gap, projected_gradient_inf=gradient["projected_gradient_inf"]))
    crows = []
    for arm, saved in result["variants"]["A+B+C"].get("geometry_guards", {}).items():
        control = result["variants"]["A"]["selected_output"][arm]
        if control["source"] == "exact_saved_ALGO07":
            control = dict(x=d["problems"][arm][1])
        candidate = result["variants"]["A+B"]["raw_endpoints"][arm]
        target = result["target_family"]
        actual = guard.evaluate_guard(d, dd, control, candidate, arm=arm, target_family=target, z=z)
        require(clean(actual) == saved, "Guard replay differs")
        # Geometry is rebuilt on copied scans; all target CFOs change by 1MHz.
        pd, count = copied_target_perturbation(d, target)
        pdd = dict(dd, scan=pd["scan"])
        perturbed = guard.evaluate_guard(pd, pdd, control, candidate,
                                         arm=arm, target_family=target, z=z)
        require(clean(perturbed) == saved, "Target CFO leaked into other-family guard")
        x0, x1 = guard._endpoint(control), guard._endpoint(candidate)
        p0, m0, u0, _, _ = guard._geometry(d, z, arm, x0)
        p1, m1, u1, _, _ = guard._geometry(dd, z, arm, x1)
        _, family = guard._inventory(p0)
        use = p0.keep & (family != target)
        independent = independent_profile(p0.values[use], m0[use], m1[use], u0[use], u1[use])
        for name, value in independent.items():
            require(abs(value-saved["full"][name]) <= 1e-7 * max(1.,abs(value)),
                    "Independent projection differs")
        crows.append(dict(arm=arm, target_tracks_perturbed=count,
                         target_CFO_shift_hz=1e6, target_perturbation_invariant=True,
                         independent_projection=independent))
    return dict(case=case, endpoint_replays=rows, guard_replays=crows)


def main(protocol_path, result_path, output_path, limit, seconds):
    began = time.monotonic()
    protocol, result = read(protocol_path), read(result_path)
    binding = result.get("protocol_sha256", result.get("scientific_protocol_sha256"))
    require(sha(protocol_path) == binding, "Protocol differs")
    for path, expected in protocol["source_sha256"].items():
        require(sha(path) == expected, "Frozen source differs")
    roster = read(protocol["evaluation"]["roster_path"])
    records = {r["case"]:r for r in roster["cases"]}
    numerical = module("saved_endpoint_solver", REPORT/"solver/numerical.py")
    covariance = module("saved_endpoint_covariance", REPORT/"covariance/causal_covariance.py")
    guard = module("saved_endpoint_guard", REPORT/"identifiability/guard.py")
    evidence = module("saved_endpoint_evidence", REPORT/"evaluation/evidence.py")
    available = [r for r in sorted(result["rows"], key=lambda x:x["case"])
                 if any(v.get("status") == "complete"
                        for variant in r["variants"].values()
                        for v in variant.get("raw_endpoints", {}).values())]
    # Include one guard-bearing case if available, then lexical distinct cases.
    guarded = [r for r in available if r["variants"]["A+B+C"].get("geometry_guards")]
    selected = (guarded[:1] + [r for r in available if not guarded or r["case"] != guarded[0]["case"]])[:limit]
    checks = []
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("Postfit replay audit cap")))
    signal.setitimer(signal.ITIMER_REAL, seconds)
    capped = False
    try:
        for row in selected:
            checks.append(check_case(records[row["case"]], row, numerical, covariance, guard, evidence))
    except TimeoutError:
        capped = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.)
    output = dict(status="capped" if capped else "passed", no_optimizer=True,
        no_phase_refresh=True, no_GPS_read=True, maximum_cases=limit, seconds_cap=seconds,
        seconds=time.monotonic()-began, protocol_sha256=sha(protocol_path),
        results_sha256=sha(result_path), auditor_sha256=sha(__file__), checks=checks)
    Path(output_path).write_text(json.dumps(clean(output), indent=2, allow_nan=False)+"\n")
    print(json.dumps(clean(output), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--results", type=Path, default=REPORT/"evaluation/results.json")
    parser.add_argument("--output", type=Path, default=ROOT/"endpoint_replay_audit.json")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=90.)
    args = parser.parse_args()
    main(args.protocol, args.results, args.output, args.limit, args.seconds)
