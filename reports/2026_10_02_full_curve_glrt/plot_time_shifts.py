import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    audit = json.loads((ROOT / "time-shift-exact-audit.json").read_text())
    rows = sorted(
        [row for row in audit["satellite_matches"] if row["matched_groups"] > 0],
        key=lambda row: row["shift_s"],
    )
    shifts = np.array([row["shift_s"] for row in rows])
    counts = np.array([row["matched_groups"] for row in rows])
    assert int(counts.sum()) == audit["groups_within_1000hz"]
    with (ROOT / "matched-satellite-time-shifts.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=["catalog_number", "shift_s", "matched_groups"])
        writer.writeheader()
        writer.writerows(rows)
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharex=True)
    bins = np.arange(-3, 3.001, 0.25)
    axes[0].hist(shifts, bins=bins, color="#2563eb", edgecolor="white")
    axes[1].hist(shifts, bins=bins, weights=counts, color="#16a34a", edgecolor="white")
    axes[0].set_title(f"One vote per matched satellite (n={len(rows)})")
    axes[1].set_title(f"Weighted by matched observation groups (n={counts.sum()})")
    axes[0].set_ylabel("Satellite count")
    axes[1].set_ylabel("Matched observation-group count")
    for axis in axes:
        axis.axvline(0, color="#333333", linewidth=1)
        axis.set_xlim(-3, 3)
        axis.set_xlabel("Fitted satellite orbit-time shift (s)")
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle(
        "scan-fw-4971402f107cf8e1 — fitted time-shift distribution\n"
        "Matches: nearest visible curve within 1 kHz; candidate IDs, not confirmed identities"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.84))
    figure.savefig(ROOT / "time-shift-distribution.png", dpi=170)
    figure.savefig(ROOT / "time-shift-distribution.svg")
    detail, axis = plt.subplots(figsize=(10, max(6, len(rows) * 0.26)))
    positions = np.arange(len(rows))
    axis.barh(positions, shifts, color=np.where(shifts >= 0, "#2563eb", "#ea580c"))
    axis.set_yticks(
        positions,
        [f"{row['catalog_number']}  (n={row['matched_groups']})" for row in rows],
        fontsize=8,
    )
    axis.axvline(0, color="#333333", linewidth=1)
    for boundary in (-3, 3):
        axis.axvline(boundary, color="#dc2626", linestyle="--", linewidth=0.8)
    axis.set_xlim(-3.15, 3.15)
    axis.set_xlabel("Fitted satellite orbit-time shift (s)")
    axis.set_ylabel("Candidate catalogue number (matched observation groups)")
    axis.set_title(
        "Per-satellite time shifts — satellites with ≥1 matched GLRT group\n"
        "Positive = evaluate orbit at receive time + shift; ±3 s bound, Gaussian prior σ=1 s"
    )
    axis.grid(axis="x", alpha=0.2)
    detail.tight_layout()
    detail.savefig(ROOT / "time-shifts-by-satellite.png", dpi=160)
    detail.savefig(ROOT / "time-shifts-by-satellite.svg")
    summary = {
        "matched_satellites": len(rows),
        "matched_groups": int(counts.sum()),
        "minimum_s": float(shifts.min()),
        "maximum_s": float(shifts.max()),
        "median_s": float(np.median(shifts)),
        "median_absolute_s": float(np.median(np.abs(shifts))),
        "within_one_second": int(np.sum(np.abs(shifts) <= 1)),
        "within_half_second": int(np.sum(np.abs(shifts) <= 0.5)),
    }
    (ROOT / "time-shift-distribution.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
