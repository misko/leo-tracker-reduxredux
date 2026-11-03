"""Compare real-data width sweeps with explicitly favorable synthetic controls."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from joint_inputs import _coordinates, _ecef
from prepare_scans import ROOT


def position_error_km(position, reference):
    estimated = _ecef(*_coordinates(np.asarray(position, dtype=float)))
    actual = _ecef(reference["latitude_deg"], reference["longitude_deg"])
    return float(np.linalg.norm(estimated - actual))


def summarize_width(record, reference):
    fitted = record["fit"]
    return {
        "session": record["session"],
        "sigma_hz": record.get("sigma_hz", fitted.get("sigma_hz")),
        "error_km": position_error_km(fitted["parameters"][:2], reference),
        "success": fitted["success"],
        "status": fitted["status"],
        "projected_gradient_inf_norm": fitted["projected_gradient_inf_norm"],
        "objective": fitted["objective"],
        "rf_coefficient_hz_per_ghz": fitted["rf_coefficient_hz_per_ghz"],
    }


def evaluate():
    destination = ROOT / "glrt-information-summary.json"
    if destination.exists():
        raise FileExistsError(destination)
    protocol_path = ROOT / "protocol-soft.json"
    sessions = json.loads(protocol_path.read_text())["sessions"]
    paths = [protocol_path]
    for session in sessions:
        paths.extend([
            ROOT / "scans" / session / "evaluation.json",
            ROOT / "rf-calibration-diagnostic" / f"{session}-common.json",
            ROOT / "information-curvature-v2" / f"{session}.json",
            *[ROOT / "glrt-width-information" / f"{session}-{width}.json"
              for width in (400, 100, 50)],
            *[ROOT / "glrt-synthetic-control" / f"{session}-{seed}.json"
              for seed in (101, 202)],
        ])
    if not all(path.exists() for path in paths):
        raise ValueError("all width, synthetic and curvature diagnostics must be sealed")
    hashes = snapshot_files([__file__, *paths])
    for path in paths:
        record = json.loads(path.read_text())
        if "source_hashes" in record:
            assert_snapshot_unchanged(record["source_hashes"])
    real_rows, synthetic_rows, information_rows = [], [], []
    for session in sessions:
        reference = json.loads((ROOT / "scans" / session / "evaluation.json").read_text())[
            "reference_site"]
        common_path = ROOT / "rf-calibration-diagnostic" / f"{session}-common.json"
        records = [json.loads(common_path.read_text())]
        records.extend(json.loads((ROOT / "glrt-width-information" /
                                   f"{session}-{width}.json").read_text())
                       for width in (400, 100, 50))
        real_rows.extend(summarize_width(record, reference) for record in records)
        for seed in (101, 202):
            record = json.loads((ROOT / "glrt-synthetic-control" /
                                 f"{session}-{seed}.json").read_text())
            fitted = record["stages"][-1]["fit"]
            synthetic_rows.append({
                "session": session, "random_seed": seed,
                "error_km": record["final_error_km"], "success": record["success"],
                "status": fitted["status"],
                "projected_gradient_inf_norm": fitted["projected_gradient_inf_norm"],
                "noise_sigma_hz": record["noise_sigma_hz"],
                "initial_error_km": position_error_km(record["initial_position_km"], reference),
                "signal_peaks": record["injected_signal_peaks"],
                "clutter_peaks": record["clutter_peaks"],
            })
        record = json.loads((ROOT / "information-curvature-v2" / f"{session}.json").read_text())
        information_rows.append({
            "session": session, "step_stability": record["step_stability"],
            "timing_knots": record["timing_knots"],
            "observed_information": record["observed_information"],
            "complete_data_fisher_information": record["complete_data_fisher_information"],
        })
    assert_snapshot_unchanged(hashes)
    result = {
        "schema": "ds13-glrt-information-summary/v1", "source_hashes": hashes,
        "real_width_sweep": real_rows, "synthetic_controls": synthetic_rows,
        "local_information": information_rows,
        "scope": "Two development scans, known-site-reviewed candidate eligibility, no holdout. "
                 "All outcomes retained, including incomplete fits. Current observations are "
                 "retained GLRT peak frequencies, not complete response surfaces or raw IQ. "
                 "Synthetic controls preserve sampling geometry and use favorable model-consistent "
                 "signals, uniform clutter and true nuisance initialization. Their accuracy does "
                 "not establish real-data accuracy. Hessian uncertainty is local and model-based, "
                 "includes timing priors, and does not measure systematic bias. NLL values at "
                 "different widths are not an error ranking or held-out model comparison.",
    }
    with destination.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def plot(result):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sessions = list(dict.fromkeys(row["session"] for row in result["real_width_sweep"]))
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    for index, session in enumerate(sessions):
        color = f"C{index}"
        label = f"Scan {'AB'[index]} (...{session[-4:]})"
        rows = sorted((row for row in result["real_width_sweep"] if row["session"] == session),
                      key=lambda row: row["sigma_hz"])
        axes[0].plot([row["sigma_hz"] for row in rows], [row["error_km"] for row in rows],
                     color=color, label=label, alpha=.7)
        for row in rows:
            axes[0].scatter(row["sigma_hz"], row["error_km"], color=color,
                            facecolors=color if row["success"] else "white", zorder=3)
        for row in result["synthetic_controls"]:
            if row["session"] != session:
                continue
            horizontal = (row["random_seed"] - 101) / 101 + (index - .5) * .12
            axes[1].scatter(horizontal, row["error_km"], edgecolors=color,
                            facecolors=color if row["success"] else "white", s=75,
                            label=label if row["random_seed"] == 101 else None)
            axes[1].annotate(f"{1000 * row['error_km']:.0f} m",
                             (horizontal, row["error_km"]), xytext=(6, 5),
                             textcoords="offset points", fontsize=9)
    axes[0].set_xscale("log")
    axes[0].set_xticks([50, 100, 200, 400], labels=[50, 100, 200, 400])
    axes[0].set_xlabel("Assumed frequency standard deviation (Hz)")
    axes[0].set_ylim(0, 3.3)
    axes[0].set_title("Real retained GLRT peaks + common RF correction")
    axes[1].set_xticks([0, 1], labels=["Random seed 101", "Random seed 202"])
    axes[1].set_xlim(-.3, 1.35)
    axes[1].set_ylim(0, 1.12)
    axes[1].set_title("Favorable simulation: same sampling, 100 Hz noise")
    for axis in axes:
        axis.axhline(1., color="black", linestyle="--", linewidth=1, label="1 km")
        axis.set_ylabel("Position error (km)")
        axis.grid(alpha=.2)
        axis.legend(fontsize=8)
    figure.suptitle("Geometry supports sub-km in a matched model; real-data bias remains")
    figure.text(.5, .025,
                "Open points: convergence criterion not met. Synthetic nuisance initialization "
                "is favorable; no real-data accuracy guarantee.", ha="center", fontsize=9)
    figure.tight_layout(rect=(0, .06, 1, .96))
    figure.savefig(ROOT / "glrt-information-comparison.png", dpi=160)
    figure.savefig(ROOT / "glrt-information-comparison.svg")
    plt.close(figure)


if __name__ == "__main__":
    result = evaluate()
    plot(result)
    for category in ("real_width_sweep", "synthetic_controls"):
        for row in result[category]:
            print(json.dumps({"category": category, **row}), flush=True)
