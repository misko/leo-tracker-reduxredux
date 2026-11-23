"""Plot dense complete-solve clocks and southern containing-offer position scores."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def measurement(name):
    return json.loads((HERE / "measurements" / name).read_bytes())


def main():
    runs = measurement("live-inference-profile-summary.json")["runs"]
    south = measurement("full-short-south.json")
    budget = measurement("full-short-live-budget.json")["estimates"]
    fastest = max((r for r in budget if r["seal"] == "optimistic"), key=lambda r: r["reader_MB_s"])
    fig, (solve, error) = plt.subplots(1, 2, figsize=(11.2, 4.1), layout="constrained")
    colors = ["#334e73", "#13806f", "#98846a"]
    labels = ["Installed v3", "Candidate", "Visibility-first trial"]
    times = [runs[key]["solve"]["cpu_s"] for key in ("installed", "control", "visible")]
    bars = solve.barh(labels, times, color=colors, height=.56)
    solve.bar_label(bars, fmt="%.2f s", padding=3)
    solve.invert_yaxis()
    solve.set(xlabel="CPU seconds from saved detections through grid", xlim=(0, 72), title="Dense physical recording · DS30-0008")
    limit = fastest["dense_solve_budget_s"]
    solve.axvline(limit, color="#a04025", ls=":", label=f"Modeled solver budget {limit:.1f} s")
    solve.legend(frameon=False, loc="lower right", fontsize=8)
    for idx, (key, label) in enumerate((("stock", "Installed v3"), ("containing", "Candidate"))):
        data = south["stock"] if key == "stock" else south["cases"][key]
        errors = [data["score"]["arms"][arm]["error_km"] for arm in ("c0", "fitted_c")]
        bars = error.bar([x + (idx-.5)*.33 for x in range(2)], errors, width=.31, color=colors[idx], label=label)
        error.bar_label(bars, fmt="%.3f", padding=3)
    error.set(xticks=[0, 1], xticklabels=["Fixed c = 0", "Fitted c"], ylabel="Horizontal error (km)",
              ylim=(0, 1.32), title="Southern simulation · valid region")
    error.legend(loc="upper left", frameon=False, fontsize=9)
    for axis in (solve, error):
        axis.spines[["top", "right"]].set_visible(False)
    fig.savefig(HERE / "development/full-short-transfer.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
