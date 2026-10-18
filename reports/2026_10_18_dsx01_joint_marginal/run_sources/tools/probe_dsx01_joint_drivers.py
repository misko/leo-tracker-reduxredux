"""Inspect leading residual drivers at GPS and at completed blind endpoints."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import objective_parts, problem_for, reference_xy
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_joint_marginal import OUTPUT

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run():
    fig, axes = plt.subplots(3, 3, figsize=(16, 10))
    records = {}
    for row, case in enumerate(("DSX01-S02", "DSX01-S03", "DSX01-S05")):
        path = OUTPUT / case / "robust/endpoints.json"
        fit = json.loads(path.read_text())["fits"]["c0"]
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        p = problem_for(scan, fit, "robust")
        endpoint = np.array(fit["parameters"])
        gps = endpoint.copy()
        gps[:2] = reference_xy()
        results = {"GPS": p.calculate(gps), "Blind endpoint": p.calculate(endpoint)}
        parts = {name: objective_parts(p, result) for name, result in results.items()}
        gain = parts["GPS"]["curve"] - parts["Blind endpoint"]["curve"]
        k = int(np.argmax(gain))
        track = scan.tracks[p.members[k]]
        sl, times = p.slices[k], track["times"]
        observed = p.values[sl]
        baseline = float(np.median(observed))
        ax = axes[row]
        ax[0].scatter(times, observed - baseline, s=7, color="gray", label="GLRT")
        means = {}
        for name, result in results.items():
            residual = result["conditional_residual_hz"][sl]
            means[name] = observed - residual
            ax[0].plot(times, means[name] - baseline, label=name)
            ax[1].plot(times, residual, ".-", markersize=3, linewidth=0.7, label=name)
        delta = means["GPS"] - means["Blind endpoint"]
        ax[2].plot(times, delta, color="purple")
        ax[1].axhline(0, color="black", linewidth=0.5)
        ax[2].axhline(0, color="black", linewidth=0.5)
        ax[0].set(
            title=f"{track['key']} / nominal {p.rows[k]['candidate_norad']}",
            ylabel=f"CFO − {baseline:.0f} Hz",
        )
        ax[1].set(title="Conditional point residuals", ylabel="Hz")
        ax[2].set(
            title=f"GPS − endpoint prediction; RMS {np.sqrt(np.mean(delta**2)):.2f} Hz", ylabel="Hz"
        )
        for a in ax:
            a.set_xlabel("Scan time (s)")
        ax[0].legend(fontsize=7)
        records[case] = dict(
            component=track["key"],
            nominal_norad=p.rows[k]["candidate_norad"],
            times=times,
            alias_lifted_GLRT_hz=observed,
            predictions_hz=means,
            curve_objective_gps=float(parts["GPS"]["curve"][k]),
            curve_objective_endpoint=float(parts["Blind endpoint"]["curve"][k]),
            total_objective_gps=parts["GPS"]["total"],
            total_objective_endpoint=parts["Blind endpoint"]["total"],
            note=(
                "Conditional means include hardware/RX smooth/phase/orbit/curve constant; "
                "hyperparameters and nominations fixed."
            ),
        )
    fig.tight_layout()
    fig.savefig(OUTPUT / "leading_track_drivers.png", dpi=170)
    plt.close(fig)
    write(OUTPUT / "leading_track_drivers.json", records)


if __name__ == "__main__":
    run()
