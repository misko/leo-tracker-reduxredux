"""Render a retrospective from saved summaries; performs no scientific fits."""
from pathlib import Path
import csv
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCES = {
    "channels": Path("/srv/bulk/leo/research/ds24-next-directions-review-r01/overview_metrics.json"),
    "receiver_development": Path("/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/report/summary.json"),
    "receiver_later": Path("/srv/bulk/leo/research/ds24-phase-shape-validation-r01/validation/report/summary.json"),
    "recovery": Path("/srv/bulk/leo/research/algo04-candidate-20261023/tables/summary.csv"),
    "information": Path("/srv/bulk/leo/research/ds24-bottlenecks-20261024/information/summary.json"),
    "current_fixed": ROOT / "current_fixed_diagnostic.json",
}


def main():
    data = {k: json.loads(p.read_text()) for k, p in SOURCES.items() if p.suffix == ".json"}
    recovery = list(csv.DictReader(SOURCES["recovery"].open()))
    arms = ("c0", "fitted_c")
    colors = ("#3973a5", "#b04a27")
    names = ("c = 0", "fitted c")
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.dpi": 150})
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 8.2), layout="constrained")
    ax = axes[0, 0]
    channels = data["channels"]
    assert channels["cohort_size"] == 24
    for i, (arm, color, name) in enumerate(zip(arms, colors, names)):
        values = channels[f"{arm}_mean_km"][:3]
        bars = ax.bar(np.arange(3) + (i - .5) * .34, values, width=.34,
                      color=color, label=name)
        ax.bar_label(bars, fmt="%.3f", fontsize=9, padding=3)
    ax.set(xticks=range(3), xticklabels=["CH1–8", "CH1–4", "CH5–8"],
           ylabel="Mean position error (km)", ylim=(0, 2.35),
           title="All eight channels already help\nSame 24 DS24 fast scans")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    for arm, color, name in zip(arms, colors, names):
        rows = [next(r for r in recovery if r["cohort"] == "all" and
                     r["method"] == m and r["arm"] == arm)
                for m in ("reference", "graph", "candidate")]
        assert all(int(r["scans"]) == 410 for r in rows)
        x = [float(r["associated_percent"]) for r in rows]
        y = [float(r["mean_km"]) for r in rows]
        ax.plot(x, y, "o-", color=color, label=name)
        if arm == "fitted_c":
            for a, b, label in zip(x, y, ["Reference", "Graph recovery", "ALGO04 candidate"]):
                ax.annotate(label, (a, b), xytext=(0, -20), textcoords="offset points",
                            ha="center", fontsize=9)
    ax.set(xlabel="Postfit GLRT associations (%)", ylabel="Mean position error (km)",
           xlim=(68.5, 77), ylim=(1.37, 1.68),
           title="More associations did not ensure accuracy\nSame 410 available DS23 scans; candidate rejected")
    ax.legend(frameon=False, loc="upper right")

    changes = []
    for arm in arms:
        old = next(r for r in data["receiver_development"]["summary"] if
                   r["model"] == "baseline" and r["arm"] == arm and r["variant"] == "policy")
        new = next(r for r in data["receiver_development"]["summary"] if
                   r["model"] == "receiver_fast_rx1_rf50" and r["arm"] == arm and r["variant"] == "policy")
        later_old = next(r for r in data["receiver_later"]["summaries"] if
                         r["arm"] == arm and r["variant"] == "baseline")
        later_new = next(r for r in data["receiver_later"]["summaries"] if
                         r["arm"] == arm and r["variant"] == "primary_policy")
        assert old["n"] == new["n"] == 24
        assert later_old["selected_cases"] == later_new["selected_cases"] == 8
        for metric in ("mean", "p95"):
            changes.append({"arm": arm, "metric": metric,
                            "development_change_m": 1000 * (new[f"{metric}_km"] - old[f"{metric}_km"]),
                            "later_change_m": 1000 * (later_new["errors_km"][metric] - later_old["errors_km"][metric])})
    for ax, metric, label in zip(axes[1], ("mean", "p95"), ("Mean", "P95")):
        ax.axhline(0, color="0.35", lw=1)
        for i, (arm, color, name) in enumerate(zip(arms, colors, names)):
            row = next(r for r in changes if r["arm"] == arm and r["metric"] == metric)
            bars = ax.bar(np.arange(2) + (i - .5) * .34,
                          [row["development_change_m"], row["later_change_m"]],
                          width=.34, color=color, label=name)
            ax.bar_label(bars, fmt="%+.1f", padding=3, fontsize=9)
        ax.set(xticks=range(2), xticklabels=["Development\n24 scans", "Later frozen test\n8 scans"],
               ylabel=f"Change in {label.lower()} error (m); lower is better",
               title=f"Shared RX1 correction: {label.lower()} error", ylim=(-230, 215))
    fig.suptitle("Measured results from separate, paired comparisons", fontsize=16)
    fig.savefig(ROOT / "measured_results.png")
    fig.savefig(ROOT / "measured_results.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.2, 4.7), layout="constrained")
    info_values = {}
    for i, (arm, color, name) in enumerate(zip(arms, colors, names)):
        r = data["information"][arm]["variants"]["curved"]
        values = [r["local_major_sigma_km"]["median"]] + [
            r["freeze_major_sigma_km"][key]["median"]
            for key in ("receiver_all", "phase", "phase_and_orbit")]
        info_values[arm] = [1000 * v for v in values]
        bars = ax.bar(np.arange(4) + (i - .5) * .34, info_values[arm], width=.34, color=color, label=name)
        ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=10)
    ax.set(xticks=range(4), xticklabels=["Current model", "Receiver terms\nknown", "Orbital timing\nknown", "Timing + shape\nknown"],
           ylabel="Median local weak-axis scale (m)", ylim=(0, 630),
           title="Diagnostic: which uncertainty resembles position movement?\nConditional curved-data calculation; NOT achieved error or calibrated confidence")
    ax.legend(frameon=False, loc="upper right")
    fig.savefig(ROOT / "conditional_information.png")
    fig.savefig(ROOT / "conditional_information.pdf")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.3), layout="constrained")
    for ax, key, label in zip(axes,
                             ("movement_proxy_m", "weak_variance_change_pct"),
                             ("Predicted local movement magnitude (m)",
                              "Increase in original weak-direction variance (%)")):
        for i, (arm, color, name) in enumerate(zip(arms, colors, names)):
            rows = [r for r in data["current_fixed"]["rows"] if r["arm"] == arm]
            assert len(rows) == 4 and all(r["controls_pass"] for r in rows)
            bars = ax.bar(np.arange(4) + (i - .5) * .34, [r[key] for r in rows],
                          width=.34, color=color, label=name)
            ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
        ax.set(xticks=range(4), xticklabels=["0010", "0011", "0012", "0013"],
               xlabel="DS24 scan", ylabel=label)
        ax.margins(y=.2)
    axes[0].legend(frameon=False)
    fig.suptitle("Current fixed-position diagnostic: retain omitted orbit uncertainty\nLocal model effects; not achieved movement or position-error improvements", fontsize=12)
    fig.savefig(ROOT / "current_fixed_diagnostic.png")
    fig.savefig(ROOT / "current_fixed_diagnostic.pdf")
    plt.close(fig)
    receipt = {
        "new_position_fits": 0, "new_RF_collection": False,
        "source_bindings": {k: {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                            for k, p in SOURCES.items()},
        "receiver_changes": changes, "conditional_information_m": info_values,
        "checks": {"channel_n_24": True, "recovery_n_410": True,
                   "receiver_development_n_24": True, "receiver_later_n_8": True,
                   "both_c_arms": True},
        "scope": "Figures summarize different published experiments; gains are not additive."
    }
    (ROOT / "figure_data.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
