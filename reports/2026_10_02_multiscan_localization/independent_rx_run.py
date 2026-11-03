"""Bounded cohort experiment with scan-local RX intercepts and slopes."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms, digest
from independent_rx_fit import continuous_to_lines, fit_independent_rx
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials
from timing10_comparison import prepare

RUN_ID = "grouped-independent-rx-v1"


def child_initializer(data, receipts):
    if set(receipts) != set(data.child_sessions):
        raise ValueError("child initializers must exactly match captures")
    lines = []
    positions = []
    for session in data.child_sessions:
        receipt = receipts[session]
        if receipt["unit"]["session_ids"] != [session] or receipt["unit"]["size"] != 1:
            raise ValueError("child receipt identity mismatch")
        fitted = receipt["fit"]
        lines.append(np.asarray(fitted["rx_initial"])[2:6].reshape(2, 2))
        positions.append(fitted["rough"]["position_km"])
    parameters = np.zeros(6 + len(data.numbers))
    parameters[:2] = np.median(positions, axis=0)
    return parameters, np.asarray(lines)


def run_unit(unit_id):
    output = ROOT / "runs" / RUN_ID / unit_id
    if output.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    snapshot = None
    try:
        own_paths = [Path(__file__), ROOT / "independent_rx_fit.py",
                     ROOT / "independent-rx-all24-plan-v1.json",
                     ROOT / "finite_set_capture_reset.py"]
        snapshot = {str(path.resolve()): digest(path) for path in own_paths}
        data, _, binding = prepare(unit_id, "grouped")
        for path, value in binding["source_hashes"].items():
            if path in snapshot and snapshot[path] != value:
                raise RuntimeError("dependency changed during preparation")
            snapshot[path] = value
        from finite_set_capture_reset import validate_child_rough_provenance

        selection = json.loads((ROOT / "selection.json").read_text())
        child_units = {unit["session_ids"][0]: unit
                       for unit in selection["datasets"][binding["dataset"]]["units"]
                       if unit["size"] == 1}
        receipts = {}
        for session in data.child_sessions:
            child = child_units[session]
            path = ROOT / "runs/coherent-v1" / child["unit_id"] / "fit.json"
            rough_path = ROOT / "runs/rough-v1" / child["unit_id"] / "fit.json"
            for source in (path, rough_path):
                snapshot[str(source)] = digest(source)
            receipt = json.loads(path.read_text())
            validate_child_rough_provenance(receipt, path, child, binding["dataset"])
            receipts[session] = receipt
        fresh_parameters, fresh_lines = child_initializer(data, receipts)
        parent = binding["grouped_fit"]
        trials, attempts = [], []
        for source in parent["trials"]:
            satellites = np.asarray(source["satellite_indices"], dtype=int)
            likelihood = build_likelihood_arms(
                data, len(satellites), len(parent["full_bank"]),
            )["finite_set"]
            warm = fit_independent_rx(data, source["parameters"],
                                      continuous_to_lines(data, source["parameters"]),
                                      satellites, likelihood)
            if not np.isclose(warm["initial_objective"], source["objective"], rtol=0, atol=1e-6):
                raise ValueError("independent lines do not reproduce continuous initializer")
            fresh = fit_independent_rx(data, fresh_parameters, fresh_lines, satellites, likelihood)
            best = min((warm, fresh), key=lambda trial: (trial["objective"], not trial["success"]))
            trials.append(best)
            attempts.append({"continuous_start": warm, "child_rx_start": fresh})
        fitted = {"full_bank": parent["full_bank"], "trials": trials,
                  "attempts": attempts, "selection": select_trials(trials)}
        assert_snapshot_unchanged(snapshot)
        receipt = {key: value for key, value in binding.items() if key != "grouped_fit"}
        receipt.update(schema="grouped-independent-rx/v1", run_id=RUN_ID, fit=fitted,
                       source_hashes=snapshot, sealed_utc=datetime.now(UTC).isoformat(),
                       reference_read_before_seal=False, evaluation_written=False,
                       elapsed_s=time.monotonic() - started,
                       limits={"seconds_per_start_per_bank": 15, "starts_per_bank": 2},
                       scope="Independent scan/RX lines; shared position and satellite timing. "
                             "All-data, fixed candidate bank ladder, no reference-derived starts. "
                             "Bounded L-BFGS-B, not the continuous model's profile/GN optimizer.")
        output.mkdir(parents=True, exist_ok=False)
        with (output / "fit.json").open("x") as stream:
            json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
        return {"unit": unit_id, "run_id": RUN_ID,
                "selection_resolved": fitted["selection"]["selection_resolved"]}
    except Exception as error:
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            with (output / "failure.json").open("x") as stream:
                json.dump({"unit": unit_id, "error": str(error), "source_hashes": snapshot},
                          stream, indent=2)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", required=True)
    print(json.dumps(run_unit(parser.parse_args().unit)), flush=True)
