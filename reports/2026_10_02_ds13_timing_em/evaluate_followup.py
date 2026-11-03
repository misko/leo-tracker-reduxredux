"""Compare corrected solvers with unchanged direct fits; retain the v1 report."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest
from joint_inputs import _coordinates, _ecef
from prepare_scans import ROOT


def evaluate():
    destination = ROOT / "comparison-v2.json"
    if destination.exists():
        raise FileExistsError(destination)
    protocol = json.loads((ROOT / "protocol.json").read_text())
    for session in protocol["sessions"]:
        for method in ("gem", "block"):
            for tolerance in protocol["tolerances"]:
                directory = ROOT / "runs-v2" / session / f"{method}-{tolerance}"
                if not any((directory / name).exists() for name in ("fit.json", "failure.json")):
                    raise ValueError("all corrected fits must finish before evaluation")
    original_path = ROOT / "comparison.json"
    original = json.loads(original_path.read_text())
    assert_snapshot_unchanged(original["source_hashes"])
    hashes = {str(original_path): digest(original_path),
              str(ROOT / "protocol-v2.json"): digest(ROOT / "protocol-v2.json")}
    corrected = {}
    for row in original["rows"]:
        if row["method"] == "direct":
            continue
        directory = ROOT / "runs-v2" / row["session"] / f"{row['method']}-{row['tolerance']}"
        fit_path = directory / "fit.json"
        if fit_path.exists():
            record = json.loads(fit_path.read_text())
            assert_snapshot_unchanged(record["source_hashes"])
            if (record.get("revision") != "solver-correction-v2"
                    or record.get("reference_read_before_seal") is not False
                    or not record.get("sealed_utc")
                    or record.get("session") != row["session"]
                    or record.get("method") != row["method"]
                    or record.get("tolerance") != row["tolerance"]
                    or record.get("revision_protocol_sha256") != digest(ROOT / "protocol-v2.json")):
                raise ValueError("corrected fit identity or protocol mismatch")
            corrected[row["session"], row["method"], row["tolerance"]] = record
            hashes[str(fit_path)] = digest(fit_path)
        elif (directory / "failure.json").exists():
            hashes[str(directory / "failure.json")] = digest(directory / "failure.json")
        else:
            raise ValueError("all corrected fits must finish before evaluation")
    rows = []
    for source in original["rows"]:
        row = dict(source)
        if row["method"] == "direct":
            row["revision"] = "unchanged-v1-control"
            rows.append(row)
            continue
        record = corrected.get((row["session"], row["method"], row["tolerance"]))
        if record is None:
            rows.append({"session": row["session"], "method": row["method"],
                         "tolerance": row["tolerance"], "error_km": None,
                         "status": "execution_failed", "success": False})
            continue
        fitted = record["fit"]
        reference_path = ROOT / "scans" / row["session"] / "evaluation.json"
        hashes[str(reference_path)] = digest(reference_path)
        site = json.loads(reference_path.read_text())["reference_site"]
        estimated = _ecef(*_coordinates(np.asarray(fitted["parameters"])[:2]))
        reference = _ecef(site["latitude_deg"], site["longitude_deg"])
        row.update(error_km=float(np.linalg.norm(estimated - reference)), status=fitted["status"],
                   success=fitted["success"], objective=fitted["objective"],
                   data_objective=fitted["data_objective"], global_shift_s=fitted["global_shift_s"],
                   individual_timing_rms_s=float(np.sqrt(np.mean(
                       np.asarray(fitted["individual_shifts_s"])**2))),
                   rx0_intercept_hz=fitted["parameters"][2], rx0_slope_hz_s=fitted["parameters"][3],
                   rx1_intercept_hz=fitted["parameters"][4], rx1_slope_hz_s=fitted["parameters"][5],
                   signal_fraction=record["diagnostics"]["signal_fraction"],
                   supported_satellites=record["diagnostics"]["satellites_with_support_ge5"],
                   elapsed_s=fitted["elapsed_s"], revision="solver-correction-v2")
        rows.append(row)
    assert_snapshot_unchanged(hashes)
    result = {"schema": "ds13-timing-em-corrected-evaluation/v1", "rows": rows,
              "initializers": original["initializers"], "source_hashes": hashes,
              "scope": "Solver correction after first development evaluation; not independent "
                       "validation. Direct controls reused. Every corrected cell retained."}
    with destination.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def plot(result):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sessions = [row["session"] for row in result["initializers"]]
    tolerances = ["aggressive", "medium", "loose"]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for axis, session, seed in zip(axes, sessions, result["initializers"], strict=True):
        for method in ("direct", "gem", "block"):
            errors = [next(row["error_km"] for row in result["rows"]
                           if row["session"] == session and row["method"] == method
                           and row["tolerance"] == tolerance) for tolerance in tolerances]
            axis.plot(tolerances, errors, marker="o", label=method)
        axis.axhline(seed["error_km"], color="gray", linestyle="--", label="track initializer")
        axis.axhline(1, color="gray", linestyle=":", label="1 km")
        axis.set_title(session)
        axis.set_xlabel("Frequency tolerance")
        axis.grid(alpha=0.25)
        axis.legend()
    axes[0].set_ylabel("Position error (km)")
    figure.suptitle("DS13 solver-corrected development comparison — unresolved fits included")
    figure.tight_layout()
    figure.savefig(ROOT / "comparison-v2.png", dpi=160)
    figure.savefig(ROOT / "comparison-v2.svg")
    plt.close(figure)


if __name__ == "__main__":
    result = evaluate()
    plot(result)
    for row in result["rows"]:
        print(json.dumps(row), flush=True)
