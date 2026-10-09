"""Immutable report of the first ordinary-start zero-c recovery snapshot."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE.parent / "2026_10_09_position_error_iter71"


def main():
    destination = HERE / "snapshot.json"
    assert not destination.exists(), "Preserve the first recovery snapshot"
    summary = json.loads((SOURCE / "summary.json").read_text())
    assert len(summary["complete_indices"]) == 40 and summary["receipts"] == 574
    selected = {}
    for arm, stages in summary["selected"].items():
        selected[arm] = {}
        for name, row in stages.items():
            selected[arm][name] = dict(
                index=row["index"],
                error_km=row["error_km"],
                objective=row["fit"]["objective"],
                rms_hz=row["fit"]["posterior_rms_hz"],
            )
    rejected_path = SOURCE / "results/115-06-fitted-c.json"
    rejected = json.loads(rejected_path.read_text())["fit"]
    receipt_names = summary["receipt_files"]
    files = [SOURCE / x for x in receipt_names] + [
        SOURCE / "summary.json",
        SOURCE / "protocol.json",
    ]
    snapshot = dict(
        complete_sources=40,
        fit_receipts=574,
        selected=selected,
        fitted_continuation={
            k: rejected[k]
            for k in ("objective", "converged", "stationarity", "solver_success", "elapsed_s")
        },
        source_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        },
    )
    destination.write_text(json.dumps(snapshot, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        values = selected[arm]
        bars = ax.bar(
            list(values),
            [r["error_km"] for r in values.values()],
            color=("gray", "tab:blue", "tab:orange"),
        )
        ax.set(yscale="log", ylabel="Position error, km (log scale)", title=arm, ylim=(0.1, 500))
        ax.axhline(1, color="black", linestyle="--", linewidth=0.7)
        ax.bar_label(bars, labels=[f"{r['error_km']:.3f}" for r in values.values()])
    fig.suptitle("Partial: 40/63 ordinary sources; winners selected by converged score")
    fig.savefig(HERE / "ordinary-recovery.png", dpi=170)
    plt.close(fig)
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()
