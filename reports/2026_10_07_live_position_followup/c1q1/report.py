"""Render the bounded C1-Q1 comparison without refitting."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    source = json.loads((HERE / "results.json").read_text())
    rows = source["rows"]
    assert len(rows) == 48
    basins = {r["basin"] for r in rows}
    assert len(basins) == 6
    for basin in basins:
        pools = [
            {r["start"] for r in rows if (r["basin"], r["model"], r["arm"]) == (basin, model, arm)}
            for model in ("T1AT", "C1-Q1")
            for arm in ("fitted-c", "zero-c")
        ]
        assert all(p == {"associated", "zero-timing"} for p in pools)
    assert all(r["fit"]["vector"][6] == 0 for r in rows if r["arm"] == "zero-c")
    selected = []
    for model in ("T1AT", "C1-Q1"):
        for arm in ("fitted-c", "zero-c"):
            pool = [r for r in rows if (r["model"], r["arm"]) == (model, arm)]
            winner = min(pool, key=lambda r: (r["score"], r["basin"], r["start"]))
            selected.append(
                dict(
                    model=model,
                    arm=arm,
                    basin=winner["basin"],
                    start=winner["start"],
                    error_m=winner["error_m"],
                    posterior_rms_hz=winner["fit"]["posterior_rms_hz"],
                    converged=winner["fit"]["converged"],
                    stationarity=winner["fit"]["stationarity"],
                    score=winner["score"],
                    converged_starts=sum(r["fit"]["converged"] for r in pool),
                )
            )
    summary = dict(
        session=source["session"],
        cases=len(rows),
        basins=len(basins),
        converged=sum(r["fit"]["converged"] for r in rows),
        selected=selected,
        elapsed_s=source["elapsed_s"],
        parity_checks=len(source["parity"]),
        maximum_parity_difference=max(abs(r["delta"]) for r in source["parity"]),
        conclusion=(
            "No promotion evidence from this single-scan diagnostic; all selected fits converge."
        ),
        rf_scope=(
            "Same observations, bank, baseline, seeds and budgets within each basin; "
            "final basin may differ."
        ),
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 11})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, field, title in zip(
        axes,
        ("error_m", "posterior_rms_hz"),
        ("Position error (m)", "Posterior frequency RMS (Hz)"),
        strict=True,
    ):
        for offset, arm, color in ((-0.18, "fitted-c", "#167c80"), (0.18, "zero-c", "#d78535")):
            values = [
                next(r[field] for r in selected if r["model"] == model and r["arm"] == arm)
                for model in ("T1AT", "C1-Q1")
            ]
            bars = ax.bar(np.arange(2) + offset, values, width=0.32, color=color, label=arm)
            ax.bar_label(bars, fmt="%.0f", padding=3)
        ax.set_xticks([0, 1], ["T1AT", "C1-Q1"])
        ax.set_title(title, loc="left")
        ax.margins(y=0.2)
        ax.grid(axis="y", alpha=0.15)
    axes[0].legend(frameon=False)
    fig.suptitle(
        "One live scan: C1-Q1 improves frequency RMS, worsens selected position",
        x=0.07,
        ha="left",
        fontsize=13,
    )
    fig.text(
        0.07,
        0.025,
        "22:52 UTC scan • six frozen regional proposals • matched final c arms • "
        "all four selections converge",
        fontsize=9,
    )
    fig.tight_layout(rect=[0, 0.07, 1, 0.92])
    fig.savefig(HERE / "comparison.png", dpi=170)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
