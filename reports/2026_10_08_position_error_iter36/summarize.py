"""Summarize every attempted clock start, with converged score-based selection."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest, name
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    lines = [
        "| Scan | Start | c | Converged | Error km | Objective | RMS Hz |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    summary = {}
    for k, label in enumerate(plan["cases"]):
        data = json.loads((HERE / "results" / f"{label}.json").read_text())
        summary[label] = {}
        for row in data["candidates"]:
            if row["arm"] == "zero-c":
                assert row["vector"][6] == 0
            assert max(abs(row["vector"][3]), abs(row["vector"][5])) <= 60 + 1e-7
            assert row["converged"] == (row["stationarity"] <= 0.001)
            lines.append(
                f"| {label} | {row['initialization']} | {row['arm']} | "
                f"{row['converged']} | {row['error_km']:.6f} | "
                f"{row['objective']:.6f} | {row['posterior_rms_hz']:.3f} |"
            )
        for j, arm in enumerate(("fitted-c", "zero-c")):
            rows = [r for r in data["candidates"] if r["arm"] == arm]
            eligible = [r for r in rows if r["converged"]]
            winner = min(eligible, key=lambda r: r["objective"]) if eligible else None
            summary[label][arm] = winner
            ax = axes[k, j]
            colors = ["tab:green" if r is winner else "tab:blue" for r in rows]
            bars = ax.bar(np.arange(len(rows)), [r["error_km"] for r in rows], color=colors)
            for bar, row in zip(bars, rows, strict=True):
                if not row["converged"]:
                    bar.set_hatch("xx")
            ax.set_xticks(
                np.arange(len(rows)),
                [r["initialization"] for r in rows],
                rotation=25,
                ha="right",
                fontsize=8,
            )
            ax.set(title=f"{label} / {arm}", ylabel="Position error (km)")
            ax.axhline(1, color="grey", linestyle="--", linewidth=0.8)
    fig.suptitle(
        "Clock initialization test: green = lowest converged objective; hatch = failed KKT"
    )
    fig.savefig(HERE / "clock-starts.png", dpi=150)
    (HERE / "candidates.md").write_text("\n".join(lines) + "\n")
    (HERE / "selected.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                label: {
                    arm: None
                    if row is None
                    else dict(
                        start=row["initialization"],
                        error_km=row["error_km"],
                        objective=row["objective"],
                    )
                    for arm, row in arms.items()
                }
                for label, arms in summary.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
