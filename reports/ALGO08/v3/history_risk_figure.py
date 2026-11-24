"""Compare paid saved-input runtimes and position-error changes on the routed panel."""

from argparse import ArgumentParser
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reports.ALGO08.v3.history_risk_route_panel import read_sealed_panel

HERE = Path(__file__).resolve().parent


def load_rows(size=3):
    rows = []
    for entry in read_sealed_panel(size)["enrolled"].values():
        result = entry["result"]
        runs = result["scientific"]["runs"]
        error = {arm: 1000 * (runs["routed"]["horizontal_error_km"][arm] - runs["named"]["horizontal_error_km"][arm])
                 for arm in ("c0", "fitted_c")}
        rows.append((result["case"], result["archive_stock_clock"]["elapsed_s"],
                     result["clock"]["elapsed_s"] + entry["source_stage"]["preflight"]["elapsed_ns"] / 1e9, error))
    return rows


def render(output, size=3):
    rows = load_rows(size)
    navy, green = "#18385b", "#008374"
    fig, (runtime, errors) = plt.subplots(1, 2, figsize=(10.2, 3.9), sharey=True)
    fig.subplots_adjust(left=0.115, right=0.97, bottom=0.28, top=0.76, wspace=0.11)
    fig.suptitle("Choosing the solver from earlier orbit quality", x=0.04, ha="left",
                 fontsize=17, fontweight="bold")
    for i, (_, stock, candidate, delta) in enumerate(rows):
        runtime.plot([candidate, stock], [i, i], color="#bfccd3", lw=2, zorder=1)
        runtime.scatter(stock, i, color=navy, s=46, label="ALGO08v3" if i == 0 else None, zorder=2)
        runtime.scatter(candidate, i, color=green, s=46, label="Routed, including checks" if i == 0 else None, zorder=2)
        errors.scatter(delta["c0"], i - 0.10, color=navy, marker="o", label="Fixed c = 0" if i == 0 else None)
        errors.scatter(delta["fitted_c"], i + 0.10, color=green, marker="D", label="Fitted c" if i == 0 else None)
    errors.axvline(0, color="#73838c", lw=1, zorder=0)
    errors.margins(x=0.13)
    errors.set_xlabel("Routed minus ALGO08v3 error (m)")
    runtime.set(xlim=(0, None), ylim=(len(rows) - 0.45, -0.55), xlabel="Elapsed from saved detections (s)")
    runtime.set_yticks(range(len(rows)), [r[0] for r in rows])
    for axis, title in ((runtime, "Runtime on each recording"), (errors, "Change in horizontal position error")):
        axis.set_title(title, loc="left", fontsize=12, fontweight="bold")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="x", color="#dce3e8")
        axis.set_axisbelow(True)
        axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False)
    fig.savefig(output, dpi=150, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, choices=(3, 4), default=3)
    size = parser.parse_args().cases
    slug = {3: "three", 4: "four"}[size]
    render(HERE / f"development/history-risk-{slug}-case.png", size)
