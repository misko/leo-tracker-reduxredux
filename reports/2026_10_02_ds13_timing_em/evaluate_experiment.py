"""Post-seal-only DS13 comparison, retaining every planned solver/tolerance cell."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest
from joint_inputs import _coordinates, _ecef
from rough_smoke import serializable

ROOT = Path(__file__).resolve().parent


def planned_cells(protocol):
    return [(session, method, tolerance) for session in protocol["sessions"]
            for method in protocol["models"] for tolerance in protocol["tolerances"]]


def require_complete(root, protocol):
    for session, method, tolerance in planned_cells(protocol):
        directory = root / "runs" / session / f"{method}-{tolerance}"
        if not any((directory / name).exists() for name in ("fit.json", "failure.json")):
            raise ValueError("all planned fits must finish before reference evaluation")


def evaluate():
    output = ROOT / "comparison.json"
    if output.exists():
        raise FileExistsError(output)
    protocol = json.loads((ROOT / "protocol.json").read_text())
    protocol_hash = digest(ROOT / "protocol.json")
    require_complete(ROOT, protocol)
    records = {}
    hashes = {str(ROOT / "protocol.json"): protocol_hash,
              str(Path(__file__)): digest(Path(__file__))}
    for session, method, tolerance in planned_cells(protocol):
        directory = ROOT / "runs" / session / f"{method}-{tolerance}"
        path = directory / "fit.json"
        if path.exists():
            record = json.loads(path.read_text())
            if (record.get("schema") != "ds13-timing-em-fit/v1"
                    or record.get("session") != session or record.get("method") != method
                    or record.get("tolerance") != tolerance
                    or record.get("reference_read_before_seal") is not False
                    or record.get("evaluation_written") is not False
                    or not record.get("sealed_utc")
                    or record.get("protocol_sha256") != protocol_hash):
                raise ValueError("fit is not an identified sealed protocol result")
            assert_snapshot_unchanged(record["source_hashes"])
            records[session, method, tolerance] = record
        else:
            path = directory / "failure.json"
        hashes[str(path)] = digest(path)
    references = {}
    initializers = []
    for session in protocol["sessions"]:
        path = ROOT / "scans" / session / "evaluation.json"
        hashes[str(path)] = digest(path)
        references[session] = json.loads(path.read_text())["reference_site"]
        seed_path = ROOT / "scans" / session / "seed.json"
        hashes[str(seed_path)] = digest(seed_path)
        seed = json.loads(seed_path.read_text())
        site = references[session]
        truth = _ecef(site["latitude_deg"], site["longitude_deg"])
        initial_position = _ecef(*_coordinates(np.asarray(seed["initial"])[:2]))
        initializers.append({"session": session,
                             "error_km": float(np.linalg.norm(initial_position - truth)),
                             "rough_success": seed["rough"]["success"],
                             "candidate_satellites": len(seed["satellites"])})
    rows = []
    for session, method, tolerance in planned_cells(protocol):
        record = records.get((session, method, tolerance))
        row = {"session": session, "method": method, "tolerance": tolerance}
        if record is None:
            rows.append({**row, "status": "execution_failed", "error_km": None})
            continue
        fitted = record["fit"]
        position = _ecef(*_coordinates(np.asarray(fitted["parameters"])[:2]))
        site = references[session]
        truth = _ecef(site["latitude_deg"], site["longitude_deg"])
        rows.append({**row, "status": fitted["status"], "success": fitted["success"],
                     "error_km": float(np.linalg.norm(position - truth)),
                     "objective": fitted["objective"], "data_objective": fitted["data_objective"],
                     "global_shift_s": fitted["global_shift_s"],
                     "individual_timing_rms_s": float(np.sqrt(np.mean(
                         np.asarray(fitted["individual_shifts_s"])**2))),
                     "rx0_intercept_hz": fitted["parameters"][2],
                     "rx0_slope_hz_s": fitted["parameters"][3],
                     "rx1_intercept_hz": fitted["parameters"][4],
                     "rx1_slope_hz_s": fitted["parameters"][5],
                     "signal_fraction": record["diagnostics"]["signal_fraction"],
                     "supported_satellites": record["diagnostics"]["satellites_with_support_ge5"],
                     "elapsed_s": fitted["elapsed_s"]})
    assert_snapshot_unchanged(hashes)
    result = {"schema": "ds13-timing-em-evaluation/v1", "rows": rows,
              "initializers": initializers, "source_hashes": hashes,
              "scope": "Two all-data conditional development scans, no holdout. Reference is "
                       "post-seal only. All cells retained. Nonconverged results are provisional."}
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with (ROOT / "comparison.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return result


def plot(result):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sessions = list(dict.fromkeys(row["session"] for row in result["rows"]))
    tolerances = ["aggressive", "medium", "loose"]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for axis, session in zip(axes, sessions, strict=True):
        for method in ("direct", "gem", "block"):
            rows = [next(row for row in result["rows"]
                         if row["session"] == session and row["method"] == method
                         and row["tolerance"] == tolerance) for tolerance in tolerances]
            axis.plot(tolerances, [row["error_km"] for row in rows], marker="o", label=method)
        axis.set_title(session)
        axis.axhline(1, color="gray", linestyle=":", label="1 km")
        axis.set_xlabel("Frequency tolerance")
        axis.grid(alpha=0.25)
        axis.legend()
    axes[0].set_ylabel("Position error (km)")
    figure.suptitle("DS13 two-scan development comparison — unresolved fits remain included")
    figure.tight_layout()
    figure.savefig(ROOT / "comparison.png", dpi=160)
    figure.savefig(ROOT / "comparison.svg")
    plt.close(figure)


if __name__ == "__main__":
    result = evaluate()
    plot(result)
    for row in result["rows"]:
        print(json.dumps(row), flush=True)
