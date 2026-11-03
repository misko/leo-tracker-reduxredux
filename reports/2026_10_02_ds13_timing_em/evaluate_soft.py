"""Post-seal comparison for the soft-frequency development experiment."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from joint_inputs import _coordinates, _ecef
from prepare_scans import ROOT
from soft_experiment import planned_cells


def sealed_records(root, protocol):
    records = {}
    hashes = snapshot_files([root / "protocol-soft.json"])
    for session, method, tolerance in planned_cells(protocol):
        directory = root / "runs-soft" / session / f"{method}-{tolerance}"
        fit_path = directory / "fit.json"
        failure_path = directory / "failure.json"
        if fit_path.exists() == failure_path.exists():
            raise ValueError("every planned cell must have exactly one sealed fit or failure")
        path = fit_path if fit_path.exists() else failure_path
        hashes[str(path)] = digest(path)
        record = json.loads(path.read_text())
        if fit_path.exists():
            if (record.get("schema") != "ds13-soft-frequency-fit/v1"
                    or record.get("session") != session or record.get("method") != method
                    or record.get("tolerance") != tolerance
                    or record.get("reference_read_before_seal") is not False
                    or not record.get("sealed_utc")
                    or record.get("protocol_sha256") != hashes[str(root / "protocol-soft.json")]
                    or record.get("setting") != protocol["tolerances"][tolerance]):
                raise ValueError("invalid fit identity or seal")
            assert_snapshot_unchanged(record["source_hashes"])
            records[session, method, tolerance] = record
    return records, hashes


def continuation_records(root):
    protocol_path = root / "protocol-continuation.json"
    protocol = json.loads(protocol_path.read_text())
    hashes = snapshot_files([protocol_path])
    records = {}
    cells = [(session, "continuation", tolerance) for tolerance in protocol["stages"]
             for session in protocol["sessions"]]
    for session, method, tolerance in cells:
        directory = root / "runs-continuation" / session / tolerance
        fit_path, failure_path = directory / "fit.json", directory / "failure.json"
        if fit_path.exists() == failure_path.exists():
            raise ValueError("all continuation cells must finish before reference evaluation")
        path = fit_path if fit_path.exists() else failure_path
        hashes[str(path)] = digest(path)
        if fit_path.exists():
            record = json.loads(path.read_text())
            if (record.get("schema") != "ds13-soft-continuation-fit/v1"
                    or record.get("session") != session or record.get("method") != method
                    or record.get("tolerance") != tolerance
                    or record.get("reference_read_before_seal") is not False
                    or not record.get("sealed_utc")
                    or record.get("protocol_sha256") != hashes[str(protocol_path)]):
                raise ValueError("invalid continuation identity or seal")
            assert_snapshot_unchanged(record["source_hashes"])
            records[session, method, tolerance] = record
    return records, hashes, cells


def reported_status(fitted):
    status = fitted["status"]
    if status == "projected_stationary_visibility_branch" and not fitted["success"]:
        return "best_finite_nonterminal_stationarity_unverified"
    return status


def evaluate():
    destination = ROOT / "comparison-soft.json"
    if destination.exists():
        raise FileExistsError(destination)
    protocol = json.loads((ROOT / "protocol-soft.json").read_text())
    records, hashes = sealed_records(ROOT, protocol)
    warm_records, warm_hashes, warm_cells = continuation_records(ROOT)
    records.update(warm_records)
    hashes.update(warm_hashes)
    previous_path = ROOT / "comparison-v2.json"
    previous = json.loads(previous_path.read_text())
    assert_snapshot_unchanged(previous["source_hashes"])
    hashes[str(previous_path)] = digest(previous_path)
    hashes[__file__] = digest(__file__)
    references = {}
    for session in protocol["sessions"]:
        path = ROOT / "scans" / session / "evaluation.json"
        hashes[str(path)] = digest(path)
        site = json.loads(path.read_text())["reference_site"]
        references[session] = _ecef(site["latitude_deg"], site["longitude_deg"])
    rows = []
    for cell in planned_cells(protocol) + warm_cells:
        session, method, tolerance = cell
        row = {"session": session, "method": method, "tolerance": tolerance}
        if cell not in records:
            rows.append({**row, "success": False, "status": "execution_failed", "error_km": None})
            continue
        record = records[cell]
        fitted = record["fit"]
        position = _ecef(*_coordinates(np.asarray(fitted["parameters"])[:2]))
        gradient_norm = fitted.get("projected_gradient_inf_norm")
        if gradient_norm is None:
            from solvers import _optimizer_scale

            gradient_norm = float(np.max(np.abs(
                np.asarray(record["final_gradient"]) * _optimizer_scale(len(fitted["vector"])))))
        rows.append({
            **row, "error_km": float(np.linalg.norm(position - references[session])),
            "status": reported_status(fitted), "raw_solver_status": fitted["status"],
            "success": fitted["success"],
            "objective": fitted["objective"], "prior_objective": fitted["prior_objective"],
            "projected_gradient_inf_norm": gradient_norm,
            "global_shift_s": fitted["global_shift_s"],
            "individual_timing_rms_s": float(np.sqrt(np.mean(
                np.asarray(fitted["individual_shifts_s"])**2))),
            "rx0_intercept_hz": fitted["parameters"][2],
            "rx0_slope_hz_s": fitted["parameters"][3],
            "rx1_intercept_hz": fitted["parameters"][4],
            "rx1_slope_hz_s": fitted["parameters"][5],
            "signal_fraction": record["diagnostics"]["signal_fraction"],
            "supported_satellites": record["diagnostics"]["satellites_with_support_ge5"],
            "confident_rows": record["confident_reporting"]["confident_rows"],
            "elapsed_s": fitted["elapsed_s"], "budget_s": fitted["budget_s"],
        })
    assert_snapshot_unchanged(hashes)
    result = {"schema": "ds13-soft-frequency-evaluation/v1", "rows": rows,
              "initializers": previous["initializers"],
              "hard_direct_controls": [
                  row for row in previous["rows"] if row["method"] == "direct"],
              "source_hashes": hashes, "scope": protocol["evaluation"],
              "continuation_scope": "Four broad-to-narrow warm fits also sealed before evaluation; "
                                    "predecessors chosen solely by same-width GLRT objective."}
    with destination.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def plot(result):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sessions = [row["session"] for row in result["initializers"]]
    tolerances = ["aggressive", "medium", "loose"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for axis, session, seed in zip(axes, sessions, result["initializers"], strict=True):
        selections = [("Hard direct (30s)", result["hard_direct_controls"], "direct"),
                      ("Soft direct (30s)", result["rows"], "direct"),
                      ("Soft Fisher (90s)", result["rows"], "fisher"),
                      ("Soft continuation (+90s/stage)", result["rows"], "continuation")]
        for label, rows, method in selections:
            widths = tolerances[:2] if method == "continuation" else tolerances
            chosen = [next(row for row in rows if row["session"] == session
                           and row["method"] == method and row["tolerance"] == tolerance)
                      for tolerance in widths]
            axis.plot(widths, [row["error_km"] for row in chosen], marker="o", label=label)
            for tolerance, row in zip(widths, chosen, strict=True):
                if row.get("success"):
                    axis.plot(tolerance, row["error_km"], marker="*", color="black", markersize=12)
        axis.axhline(seed["error_km"], color="gray", linestyle="--", label="Track seed")
        axis.axhline(1, color="gray", linestyle=":", label="1 km")
        axis.set_title(session)
        axis.set_xlabel("Gaussian width: 100 / 200 / 400 Hz")
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    axes[0].set_ylabel("Position error (km)")
    figure.suptitle("Soft-frequency development comparison; stars indicate solver convergence")
    figure.tight_layout()
    figure.savefig(ROOT / "comparison-soft.png", dpi=160)
    figure.savefig(ROOT / "comparison-soft.svg")
    plt.close(figure)


if __name__ == "__main__":
    result = evaluate()
    plot(result)
    for row in result["rows"]:
        print(json.dumps(row), flush=True)
