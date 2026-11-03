"""Frozen-seed soft-frequency experiment, with no reference access in fitting."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from prepare_scans import MULTI, ROOT, load_scan
from rough_smoke import serializable
from run_experiment import association_summary
from soft_likelihood import SoftLikelihood, confident_matches
from solvers import fit_direct
from timing_model import TimingObjective


def planned_cells(protocol, method=None):
    if method is not None and method not in protocol["models"]:
        raise ValueError("unknown solver")
    return [(session, solver, tolerance) for solver in protocol["models"]
            if method is None or solver == method for tolerance in protocol["tolerances"]
            for session in protocol["sessions"]]


def run_case(session, method, tolerance):
    protocol_path = ROOT / "protocol-soft.json"
    protocol = json.loads(protocol_path.read_text())
    if (session, method, tolerance) not in planned_cells(protocol):
        raise ValueError("cell outside frozen protocol")
    output = ROOT / "runs-soft" / session / f"{method}-{tolerance}"
    if output.exists():
        raise FileExistsError(output)
    setting = protocol["tolerances"][tolerance]
    directory = ROOT / "scans" / session
    seed_path = directory / "seed.json"
    seed = json.loads(seed_path.read_text())
    bundle = json.loads((directory / "bundle.json").read_text())
    inherited = {**seed["source_hashes"], **bundle["provenance"]["source_hashes"]}
    assert_snapshot_unchanged(inherited)
    paths = [*inherited, seed_path, directory / "bundle.json", directory / "bundle.npz",
             protocol_path, *[ROOT / name for name in (
                 "soft_experiment.py", "soft_likelihood.py", "timing_model.py", "solvers.py",
                 "run_experiment.py")], MULTI / "finite_set_likelihood.py"]
    if method == "fisher":
        paths.extend([ROOT / "soft_solvers.py", ROOT / "solver_followup.py"])
    snapshot = snapshot_files(list(dict.fromkeys(str(path) for path in paths)))
    if seed["session"] != session or seed["reference_read"] is not False:
        raise ValueError("invalid seed identity")
    started = time.monotonic()
    _, data = load_scan(session)
    satellites = np.asarray(seed["satellites"], dtype=int)
    likelihood = SoftLikelihood(prepare_finite_set_likelihood(data.measured, data.group),
                                0.8 / len(satellites))
    options = {"budget_s": protocol["models"][method]["budget_s"]}
    if method == "direct":
        fitted = fit_direct(data, seed["initial"], satellites, likelihood,
                            setting["sigma_hz"], **options)
    else:
        from soft_solvers import fit_soft

        fitted = fit_soft(data, seed["initial"], satellites, likelihood,
                          setting["sigma_hz"], method="fisher", **options)
    final = TimingObjective(data, seed["initial"], satellites, likelihood, setting["sigma_hz"])
    value, gradient = final.evaluate(fitted["vector"])
    if not np.isclose(value, fitted["objective"], atol=1e-6, rtol=0):
        raise ValueError("sealed objective does not reproduce")
    diagnostics = association_summary(likelihood.last_result)
    predicted, _ = final.predict(fitted["vector"])
    reporting = confident_matches(data.measured, predicted,
                                  likelihood.last_result["row_association_probability"],
                                  likelihood.alias_hz, setting["report_cutoff_hz"])
    assert_snapshot_unchanged(snapshot)
    receipt = {"schema": "ds13-soft-frequency-fit/v1", "session": session,
               "method": method, "tolerance": tolerance, "setting": setting,
               "fit": fitted, "diagnostics": diagnostics, "confident_reporting": reporting,
               "final_gradient": gradient, "source_hashes": snapshot,
               "seed_sha256": digest(seed_path), "protocol_sha256": digest(protocol_path),
               "geometry": data.geometry_receipt, "catalog_numbers": data.numbers[satellites],
               "reference_read_before_seal": False, "sealed_utc": datetime.now(UTC).isoformat(),
               "elapsed_s": time.monotonic() - started}
    output.mkdir(parents=True, exist_ok=False)
    with (output / "fit.json").open("x") as stream:
        json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
    return {"session": session, "method": method, "tolerance": tolerance,
            "status": fitted["status"], "success": fitted["success"], "objective": value}


def run_cell(cell):
    session, method, tolerance = cell
    protocol = json.loads((ROOT / "protocol-soft.json").read_text())
    output = ROOT / "runs-soft" / session / f"{method}-{tolerance}"
    if output.exists():
        raise FileExistsError(output)
    logs = ROOT / "logs-soft"
    logs.mkdir(exist_ok=True)
    logfile = logs / f"{session}-{method}-{tolerance}.log"
    environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    with logfile.open("x") as stream:
        try:
            code = subprocess.run(
                [sys.executable, __file__, "cell", *cell], stdout=stream,
                stderr=subprocess.STDOUT, env=environment,
                timeout=protocol["resources"]["external_cell_timeout_s"], check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            code = 124
    if code or not (output / "fit.json").exists():
        output.mkdir(parents=True, exist_ok=True)
        with (output / "failure.json").open("x") as stream:
            json.dump({"session": session, "method": method, "tolerance": tolerance,
                       "exit_code": code, "log": str(logfile)}, stream)
    return {"cell": cell, "exit_code": code}


def batch(method):
    protocol_path = ROOT / "protocol-soft.json"
    snapshot = snapshot_files([protocol_path])
    protocol = json.loads(protocol_path.read_text())
    cells = planned_cells(protocol, method)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_cell, cell) for cell in cells]
        rows = []
        for future in as_completed(futures):
            rows.append(future.result())
            print(json.dumps(rows[-1]), flush=True)
    assert_snapshot_unchanged(snapshot)
    with (ROOT / f"batch-soft-{method}.json").open("x") as stream:
        json.dump({"source_hashes": snapshot, "rows": rows}, stream, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cell_parser = commands.add_parser("cell")
    cell_parser.add_argument("session")
    cell_parser.add_argument("method", choices=("direct", "fisher"))
    cell_parser.add_argument("tolerance", choices=("aggressive", "medium", "loose"))
    batch_parser = commands.add_parser("batch")
    batch_parser.add_argument("method", choices=("direct", "fisher"))
    args = parser.parse_args()
    if args.command == "cell":
        print(json.dumps(run_case(args.session, args.method, args.tolerance)), flush=True)
    else:
        batch(args.method)
