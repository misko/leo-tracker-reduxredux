"""Evaluate solver corrections without changing the sealed DS13 v1 experiment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from gated_likelihood import GatedLikelihood
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable
from run_experiment import association_summary, validate_request
from solver_followup import fit_block_observed, fit_gem
from timing_model import TimingObjective


def corrected_method(method):
    if method not in {"gem", "block"}:
        raise ValueError("only the two corrected solvers may be rerun")
    return {"gem": fit_gem, "block": fit_block_observed}[method]


def fit(session, method, tolerance):
    fitter = corrected_method(method)
    protocol = json.loads((ROOT / "protocol.json").read_text())
    setting = validate_request(protocol, session, method, tolerance)
    output = ROOT / "runs-v2" / session / f"{method}-{tolerance}"
    if output.exists():
        raise FileExistsError(output)
    source_path = ROOT / "runs" / session / f"{method}-{tolerance}" / "fit.json"
    source = json.loads(source_path.read_text())
    assert_snapshot_unchanged(source["source_hashes"])
    paths = [*source["source_hashes"], source_path,
             ROOT / "followup.py", ROOT / "protocol-v2.json", ROOT / "solver_followup.py"]
    snapshot = snapshot_files(paths)
    started = time.monotonic()
    try:
        _, data = load_scan(session)
        seed = json.loads((ROOT / "scans" / session / "seed.json").read_text())
        satellites = np.asarray(seed["satellites"], dtype=int)
        prepared = prepare_finite_set_likelihood(data.measured, data.group)
        likelihood = GatedLikelihood(prepared, 0.8 / len(satellites), gate_hz=setting["gate_hz"])
        fitted = fitter(data, seed["initial"], satellites, likelihood, setting["sigma_hz"],
                        budget_s=protocol["resources"]["fit_budget_s"])
        objective = TimingObjective(data, seed["initial"], satellites, likelihood,
                                    setting["sigma_hz"])
        value, _ = objective.evaluate(fitted["vector"])
        if not np.isclose(value, fitted["objective"], rtol=0, atol=1e-6):
            raise ValueError("corrected solver did not retain its reported state")
        diagnostics = association_summary(likelihood.last_result)
        assert_snapshot_unchanged(snapshot)
        receipt = {**source, "fit": fitted, "diagnostics": diagnostics,
                   "source_hashes": snapshot, "revision": "solver-correction-v2",
                   "revision_protocol_sha256": digest(ROOT / "protocol-v2.json"),
                   "source_fit_sha256": digest(source_path),
                   "sealed_utc": datetime.now(UTC).isoformat(),
                   "elapsed_s": time.monotonic() - started}
        output.mkdir(parents=True, exist_ok=False)
        with (output / "fit.json").open("x") as stream:
            json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
        return {"session": session, "method": method, "tolerance": tolerance,
                "objective": value, "status": fitted["status"]}
    except Exception as error:
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            (output / "failure.json").write_text(json.dumps({"error": str(error)}))
        raise


def launch(cell):
    session, method, tolerance = cell
    logs = ROOT / "logs-v2"
    logs.mkdir(exist_ok=True)
    with (logs / f"{session}-{method}-{tolerance}.log").open("x") as stream:
        try:
            result = subprocess.run([sys.executable, str(ROOT / "followup.py"), "fit", *cell],
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=90)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    if code:
        output = ROOT / "runs-v2" / session / f"{method}-{tolerance}"
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            (output / "failure.json").write_text(json.dumps({"exit_code": code}))
    return {"session": session, "method": method, "tolerance": tolerance, "exit_code": code}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fit", "batch"))
    parser.add_argument("cell", nargs="*")
    args = parser.parse_args()
    if args.action == "fit":
        print(json.dumps(fit(*args.cell)), flush=True)
    else:
        plan = json.loads((ROOT / "protocol.json").read_text())
        cells = [(session, method, tolerance) for method in ("gem", "block")
                 for tolerance in plan["tolerances"] for session in plan["sessions"]]
        with ThreadPoolExecutor(max_workers=2) as executor:
            for future in as_completed([executor.submit(launch, cell) for cell in cells]):
                print(json.dumps(future.result()), flush=True)
