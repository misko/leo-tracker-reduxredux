"""Seal bounded DS13 solver/tolerance fits before any reference evaluation."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from gated_likelihood import GatedLikelihood
from prepare_scans import MULTI, ROOT, load_scan
from rough_smoke import serializable
from solvers import fit_block_observed, fit_direct, fit_gem
from timing_model import TimingObjective

SOLVERS = {"direct": fit_direct, "gem": fit_gem, "block": fit_block_observed}


def validate_request(protocol, session, method, tolerance):
    if session not in protocol["sessions"]:
        raise ValueError("scan outside frozen protocol")
    if method not in protocol["models"] or method not in SOLVERS:
        raise ValueError("solver outside frozen protocol")
    if tolerance not in protocol["tolerances"]:
        raise ValueError("tolerance outside frozen protocol")
    return protocol["tolerances"][tolerance]


def association_summary(result):
    association = np.asarray(result["association_probability"])
    clutter = np.asarray(result["expected_clutter_count"])
    support = association.sum(axis=0)
    return {"expected_signal_peaks": float(association.sum()),
            "expected_clutter_peaks": float(clutter.sum()),
            "signal_fraction": float(association.sum() / (association.sum() + clutter.sum())),
            "satellite_support": support,
            "satellites_with_support_ge1": int(np.sum(support >= 1)),
            "satellites_with_support_ge5": int(np.sum(support >= 5))}


def run_case(session, method, tolerance):
    output = ROOT / "runs" / session / f"{method}-{tolerance}"
    if output.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    protocol_path = ROOT / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    setting = validate_request(protocol, session, method, tolerance)
    snapshot = None
    try:
        directory = ROOT / "scans" / session
        seed_path = directory / "seed.json"
        seed_hash = digest(seed_path)
        seed = json.loads(seed_path.read_text())
        manifest = json.loads((directory / "bundle.json").read_text())
        inherited = {**seed["source_hashes"], **manifest["provenance"]["source_hashes"]}
        assert_snapshot_unchanged(inherited)
        paths = [*inherited, seed_path, *[ROOT / name for name in (
            "run_experiment.py", "timing_model.py", "solvers.py", "gated_likelihood.py",
        )], MULTI / "finite_set_likelihood.py"]
        paths = list(dict.fromkeys(str(path) for path in paths))
        snapshot = snapshot_files(paths)
        if snapshot[str(seed_path)] != seed_hash:
            raise RuntimeError("initializer changed before fitting")
        population_path = ROOT.parent / "2026_10_02_ds13_from_911c4e5d/local/manifest.json"
        if digest(population_path) != protocol["population_manifest_sha256"]:
            raise ValueError("DS13 population changed")
        if seed["session"] != session or seed["reference_read"] is not False:
            raise ValueError("seed is not an identified reference-free initializer")
        _, data = load_scan(session)
        satellites = np.asarray(seed["satellites"], dtype=int)
        prepared = prepare_finite_set_likelihood(data.measured, data.group)
        likelihood = GatedLikelihood(prepared, 0.8 / len(satellites), gate_hz=setting["gate_hz"])
        fitted = SOLVERS[method](data, seed["initial"], satellites, likelihood,
                                 setting["sigma_hz"],
                                 budget_s=protocol["resources"]["fit_budget_s"])
        final = TimingObjective(data, seed["initial"], satellites, likelihood, setting["sigma_hz"])
        value, _ = final.evaluate(fitted["vector"])
        if not np.isclose(value, fitted["objective"], rtol=0, atol=1e-6):
            raise ValueError("final state does not reproduce solver objective")
        diagnostics = association_summary(likelihood.last_result)
        assert_snapshot_unchanged(snapshot)
        receipt = {"schema": "ds13-timing-em-fit/v1", "session": session, "method": method,
                   "tolerance": tolerance, "setting": setting, "fit": fitted,
                   "diagnostics": diagnostics, "source_hashes": snapshot,
                   "seed_sha256": seed_hash, "protocol_sha256": digest(protocol_path),
                   "geometry": data.geometry_receipt, "catalog_numbers": data.numbers[satellites],
                   "reference_read_before_seal": False, "evaluation_written": False,
                   "sealed_utc": datetime.now(UTC).isoformat(),
                   "elapsed_s": time.monotonic() - started}
        output.mkdir(parents=True, exist_ok=False)
        with (output / "fit.json").open("x") as stream:
            json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
        return {"session": session, "method": method, "tolerance": tolerance,
                "success": fitted["success"], "objective": fitted["objective"],
                "signal_fraction": diagnostics["signal_fraction"]}
    except Exception as error:
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            with (output / "failure.json").open("x") as stream:
                json.dump({"session": session, "method": method, "tolerance": tolerance,
                           "error": str(error), "source_hashes": snapshot}, stream, indent=2)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session")
    parser.add_argument("method", choices=tuple(SOLVERS))
    parser.add_argument("tolerance", choices=("aggressive", "medium", "loose"))
    args = parser.parse_args()
    print(json.dumps(run_case(args.session, args.method, args.tolerance)), flush=True)
