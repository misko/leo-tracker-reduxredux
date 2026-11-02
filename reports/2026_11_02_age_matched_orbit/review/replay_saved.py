"""Postfit-only saved-endpoint replay, outside inference; no optimization."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np
from algo07_science import engine as e
from algo07_science.diagnose import objective
from audit_age import read, sha, require

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent


def replay(protocol_path, results_path):
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("60-second saved-endpoint replay cap")))
    signal.setitimer(signal.ITIMER_REAL, 60.)
    checks, capped = [], False
    try:
        protocol, results = read(protocol_path), read(results_path)
        require(results["protocol_sha256"] == sha(protocol_path), "RF result authority differs")
        for path, expected in protocol["source_sha256"].items():
            require(sha(path) == expected, "Frozen source differs")
        records = {r["case"]: r for r in read(protocol["evaluation"]["roster_path"])["cases"]}
        available = [r for r in results["rows"] if r.get("age_prior_receipt", {}).get("status") == "ready"
            and any(a.get("status") == "complete" and a.get("nuisance", {}).get("status") == "available" for a in r.get("raw_endpoints", {}).values())]
        available.sort(key=lambda r: (r["case"] != "FRSH-0001", r["case"]))
        require(bool(available), "No complete age-supported nuisance endpoint available")
        result = available[0]
        record = records[result["case"]]
        source = Path(record["input_path"]).parent.parent
        e.configure(source, ROOT / "saved_replay_runtime")
        e.ROOTS[result["case"][:4]] = source
        d, z, _ = e.load_case(result["case"])
        spec = importlib.util.spec_from_file_location("independent_postfit_age_covariance", REPORT / "covariance/age_covariance.py")
        covariance = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = covariance
        spec.loader.exec_module(covariance)
        dd, receipt = covariance.candidate_context(d, z, dict(selected_family=record["target_family"]))
        require(receipt == result["age_prior_receipt"], "Covariance receipt replay differs")
        for arm in ("c0", "fitted_c"):
            endpoint = result.get("raw_endpoints", {}).get(arm, {})
            if endpoint.get("status") != "complete" or endpoint.get("nuisance", {}).get("status") != "available":
                continue
            x = np.asarray(endpoint["x"])
            p, context = e.build(dd, z, arm, np.asarray(endpoint["reference"]))
            base, _ = e.build(d, z, arm, np.asarray(endpoint["reference"]))
            calculated, baseline = p.calculate(x), base.calculate(x)
            objective_difference = float(objective(p, context, x) - endpoint["objective"])
            require(abs(objective_difference) <= 1e-4, "Saved endpoint objective differs")
            saved = endpoint["nuisance"]
            coefficient = np.asarray(calculated["coefficient"])
            coefficient_difference = float(np.max(abs(coefficient - np.asarray(saved["coefficient"]))))
            require(coefficient_difference <= 1e-10, "Saved conditional nuisance coefficients differ")
            independent_residual = p.values - p.q * calculated["intercept"] - calculated["features"] @ coefficient
            residual_difference = float(np.max(abs(independent_residual - calculated["conditional_residual_hz"])))
            require(residual_difference <= 1e-8, "Conditional base residual coefficient decomposition differs")
            target = next(j for j in p.supported if int(p.scan.norads[j]) == record["target_family"])
            local = p.supported.index(target)
            start = p.hardware.shape[1] + p.smooth.shape[1] + len(p.labels) + 3 * local
            columns = np.arange(start, start + 3)
            root = np.linalg.cholesky(np.asarray(receipt["coefficient_covariance"]))
            feature_difference = float(np.max(abs(calculated["features"][:, columns] - baseline["features"][:, columns] @ root)))
            keep = np.ones(coefficient.size, bool)
            keep[columns] = False
            unrelated_difference = float(np.max(abs(calculated["features"][:, keep] - baseline["features"][:, keep])))
            require(feature_difference <= 1e-8 and unrelated_difference == 0., "Target-only feature transform differs")
            scales = np.asarray(receipt["current_mode_SD"])
            physical = scales * (root @ coefficient[columns])
            physical_difference = float(np.max(abs(physical - np.asarray(saved["target_orbit"]["physical_parameter_revision"]))))
            require(physical_difference <= 1e-12, "Saved physical mode coefficient map differs")
            checks.append(dict(case=result["case"], arm=arm, objective_difference=objective_difference,
                conditional_coefficient_max_difference=coefficient_difference,
                conditional_residual_decomposition_max_difference_hz=residual_difference,
                target_feature_Cholesky_map_max_difference=feature_difference,
                unrelated_feature_max_difference=unrelated_difference,
                target_physical_coefficient_max_difference=physical_difference,
                scope=saved["scope"]))
    except TimeoutError:
        capped = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.)
    packet = dict(status="capped" if capped else "passed", no_optimizer=True, no_phase_refresh=True,
        no_GPS_read=True, seconds=time.monotonic() - began, seconds_cap=60., maximum_endpoints=2,
        protocol_sha256=sha(protocol_path), results_sha256=sha(results_path), auditor_sha256=sha(__file__), checks=checks)
    (ROOT / "saved_endpoint_replay.json").write_text(json.dumps(packet, indent=2, allow_nan=False) + "\n")
    print(json.dumps(packet, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=REPORT / "protocol.json")
    parser.add_argument("--results", type=Path, default=REPORT / "evaluation/results.json")
    args = parser.parse_args()
    replay(args.protocol, args.results)
