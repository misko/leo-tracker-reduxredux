"""Truth-free broad-to-narrow continuation with immutable predecessor receipts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable
from run_experiment import association_summary
from soft_likelihood import SoftLikelihood, confident_matches
from soft_solvers import fit_soft
from timing_model import TimingObjective


def select_predecessor(candidates):
    valid = [(path, record) for path, record in candidates
             if np.isfinite(record["fit"]["objective"])]
    if not valid:
        raise ValueError("no finite predecessor")
    identities = {(record["session"], record["tolerance"], record["seed_sha256"])
                  for _, record in valid}
    if len(identities) != 1:
        raise ValueError("predecessors must share scan, width and frozen seed")
    return min(valid, key=lambda pair: pair[1]["fit"]["objective"])


def run_case(session, tolerance):
    protocol_path = ROOT / "protocol-continuation.json"
    protocol = json.loads(protocol_path.read_text())
    if session not in protocol["sessions"] or tolerance not in protocol["stages"]:
        raise ValueError("outside continuation protocol")
    output = ROOT / "runs-continuation" / session / tolerance
    if output.exists():
        raise FileExistsError(output)
    source_width = protocol["predecessor"][tolerance]
    paths = [ROOT / "runs-soft" / session / f"{method}-{source_width}" / "fit.json"
             for method in ("direct", "fisher")]
    if source_width == "medium":
        paths.append(ROOT / "runs-continuation" / session / source_width / "fit.json")
    candidates = []
    inherited = {}
    for path in paths:
        if not path.exists():
            if not (path.parent / "failure.json").exists():
                raise ValueError("predecessor not finished")
            continue
        record = json.loads(path.read_text())
        if record.get("reference_read_before_seal") is not False:
            raise ValueError("predecessor not reference-free")
        assert_snapshot_unchanged(record["source_hashes"])
        inherited.update(record["source_hashes"])
        inherited[str(path)] = digest(path)
        candidates.append((path, record))
    selected_path, selected = select_predecessor(candidates)
    seed_path = ROOT / "scans" / session / "seed.json"
    seed = json.loads(seed_path.read_text())
    base_protocol = json.loads((ROOT / "protocol-soft.json").read_text())
    setting = base_protocol["tolerances"][tolerance]
    inherited.update(snapshot_files([protocol_path, __file__, ROOT / "soft_solvers.py"]))
    assert_snapshot_unchanged(inherited)
    started = time.monotonic()
    _, data = load_scan(session)
    satellites = np.asarray(seed["satellites"], dtype=int)
    likelihood = SoftLikelihood(prepare_finite_set_likelihood(data.measured, data.group),
                                0.8 / len(satellites))
    fitted = fit_soft(data, selected["fit"]["parameters"], satellites, likelihood,
                      setting["sigma_hz"], budget_s=protocol["resources"]["fit_budget_s"])
    final = TimingObjective(data, seed["initial"], satellites, likelihood, setting["sigma_hz"])
    value, gradient = final.evaluate(fitted["vector"])
    if not np.isclose(value, fitted["objective"], rtol=0, atol=1e-6):
        raise ValueError("warm-start fit changed the underlying objective")
    diagnostics = association_summary(likelihood.last_result)
    predicted, _ = final.predict(fitted["vector"])
    reporting = confident_matches(data.measured, predicted,
                                  likelihood.last_result["row_association_probability"],
                                  likelihood.alias_hz, setting["report_cutoff_hz"])
    assert_snapshot_unchanged(inherited)
    receipt = {"schema": "ds13-soft-continuation-fit/v1", "session": session,
               "method": "continuation", "tolerance": tolerance, "setting": setting,
               "fit": fitted, "diagnostics": diagnostics, "confident_reporting": reporting,
               "final_gradient": gradient, "source_hashes": inherited,
               "seed_sha256": digest(seed_path), "protocol_sha256": digest(protocol_path),
               "predecessor": str(selected_path),
               "predecessor_objectives": {str(path): record["fit"]["objective"]
                                          for path, record in candidates},
               "reference_read_before_seal": False, "sealed_utc": datetime.now(UTC).isoformat(),
               "elapsed_s": time.monotonic() - started}
    output.mkdir(parents=True, exist_ok=False)
    with (output / "fit.json").open("x") as stream:
        json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
    return {"session": session, "tolerance": tolerance, "status": fitted["status"],
            "success": fitted["success"], "objective": fitted["objective"]}


def run_cell(cell):
    session, tolerance = cell
    output = ROOT / "runs-continuation" / session / tolerance
    if output.exists():
        raise FileExistsError(output)
    protocol = json.loads((ROOT / "protocol-continuation.json").read_text())
    logs = ROOT / "logs-continuation"
    logs.mkdir(exist_ok=True)
    logfile = logs / f"{session}-{tolerance}.log"
    with logfile.open("x") as stream:
        try:
            code = subprocess.run(
                [sys.executable, __file__, "cell", *cell], stdout=stream,
                stderr=subprocess.STDOUT, check=False,
                env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
                timeout=protocol["resources"]["external_cell_timeout_s"],
            ).returncode
        except subprocess.TimeoutExpired:
            code = 124
    if code or not (output / "fit.json").exists():
        output.mkdir(parents=True, exist_ok=True)
        with (output / "failure.json").open("x") as stream:
            json.dump({"session": session, "tolerance": tolerance,
                       "exit_code": code, "log": str(logfile)}, stream)
    return {"cell": cell, "exit_code": code}


def batch():
    protocol_path = ROOT / "protocol-continuation.json"
    snapshot = snapshot_files([protocol_path])
    protocol = json.loads(protocol_path.read_text())
    rows = []
    for tolerance in protocol["stages"]:
        with ThreadPoolExecutor(max_workers=2) as executor:
            for row in executor.map(run_cell, [(session, tolerance)
                                              for session in protocol["sessions"]]):
                rows.append(row)
                print(json.dumps(row), flush=True)
    assert_snapshot_unchanged(snapshot)
    with (ROOT / "batch-continuation.json").open("x") as stream:
        json.dump({"source_hashes": snapshot, "rows": rows}, stream, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cell_parser = commands.add_parser("cell")
    cell_parser.add_argument("session")
    cell_parser.add_argument("tolerance", choices=("medium", "aggressive"))
    commands.add_parser("batch")
    args = parser.parse_args()
    if args.command == "cell":
        print(json.dumps(run_case(args.session, args.tolerance)), flush=True)
    else:
        batch()
