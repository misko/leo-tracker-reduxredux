import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def distance(point, reference):
    p, q = np.radians(point), np.radians(reference)
    a = (
        np.sin((p[0] - q[0]) / 2) ** 2
        + np.cos(p[0]) * np.cos(q[0]) * np.sin((p[1] - q[1]) / 2) ** 2
    )
    return float(2 * 6371008.8 * np.arcsin(np.sqrt(a)))


def main():
    reference = json.loads(
        (HERE.parent / "2026_09_29_unassociated_trend/summary.json").read_text()
    )["reference"]
    rows, missing = [], []
    for ds in (7, 8, 9):
        for part in ("early", "middle", "late"):
            key = f"DS{ds}_{part}_8"
            for width in (3000, 10000):
                path = HERE / f"{key}_{width}.json"
                if not path.exists():
                    missing.append(dict(unit=key, width=width))
                    continue
                row = json.loads(path.read_text())
                for name, digest in row["hashes"].items():
                    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
                row["error_m"] = distance(row["estimate_deg"], reference)
                row["baseline_error_m"] = distance(row["baseline_estimate_deg"], reference)
                row["movement_m"] = distance(row["estimate_deg"], row["baseline_estimate_deg"])
                row["held_gain"] = row["held_score"] - row["baseline_held_score"]
                rows.append(row)
    assert not missing, missing
    table = [
        "| Panel | Prior width (Hz) | Qualified | Baseline error (m) | Soft-offset error (m) "
        "| Movement (m) | Held log-score gain |",
        "|---|---:|:---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        table.append(
            f"| {r['unit']} | {r['width']:.0f} | {'yes' if r['qualified'] else 'NO'} "
            f"| {r['baseline_error_m']:.2f} | {r['error_m']:.2f} "
            f"| {r['movement_m']:.2f} | {r['held_gain']:+.3f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(table) + "\n")
    aggregates = []
    for ds in (7, 8, 9):
        for width in (3000, 10000):
            subset = [r for r in rows if r["unit"].startswith(f"DS{ds}_") and r["width"] == width]
            aggregates.append(
                dict(
                    dataset=f"DS{ds}",
                    width=width,
                    qualified=sum(r["qualified"] for r in subset),
                    baseline_median_m=float(np.median([r["baseline_error_m"] for r in subset])),
                    median_m=float(np.median([r["error_m"] for r in subset])),
                    geographic_wins=sum(r["error_m"] < r["baseline_error_m"] for r in subset),
                    held_wins=sum(r["held_gain"] > 0 for r in subset),
                )
            )
    summary = dict(reference=reference, rows=rows, aggregates=aggregates)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for width, color in ((3000, "#0072B2"), (10000, "#D55E00")):
        subset = [r for r in rows if r["width"] == width]
        axes[0].scatter(
            [r["baseline_error_m"] for r in subset],
            [r["error_m"] for r in subset],
            label=f"{width / 1000:g} kHz",
            color=color,
        )
        axes[1].plot(
            range(9),
            [r["held_gain"] for r in subset],
            "o-",
            label=f"{width / 1000:g} kHz",
            color=color,
        )
    axes[0].plot([0, 4200], [0, 4200], "--", color="gray")
    axes[0].set(
        xlabel="Baseline error (m)",
        ylabel="Soft-offset error (m)",
        title="Below diagonal = smaller position error",
    )
    axes[1].axhline(0, color="gray", linestyle="--")
    axes[1].set(
        xticks=range(9),
        xticklabels=[r["unit"].replace("_8", "").replace("_", "\n") for r in rows[::2]],
        ylabel="Held log-score change",
        title="Above zero = better held prediction",
    )
    for ax in axes:
        ax.legend()
        ax.grid(alpha=0.2)
    figure.suptitle("Soft shared offsets: nine existing eight-scan panels")
    figure.tight_layout()
    figure.savefig(HERE / "comparison.png", dpi=160)
    print(json.dumps(aggregates, indent=2))
    print("Qualified", sum(r["qualified"] for r in rows), "/", len(rows))


if __name__ == "__main__":
    main()
