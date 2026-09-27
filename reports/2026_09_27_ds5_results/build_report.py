"""Combine completed DS5 result families without fitting or selecting positions."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_09_26_ds5_all_methods"


def check_references(fast, portable):
    if fast["reference"] != portable["reference"]:
        raise ValueError("Cannot compare errors scored against different reference coordinates")
    return fast["reference"]


def build():
    reference = check_references(
        json.loads((SOURCE / "fast-wave-postseal.json").read_text()),
        json.loads((SOURCE / "postseal-evaluation-common-reference.json").read_text()),
    )
    rows = []
    fast = list(csv.DictReader((SOURCE / "fast-wave-summary.csv").open()))
    for method in dict.fromkeys(r["method_id"] for r in fast):
        scopes = {r["scope"]: r for r in fast if r["method_id"] == method and r["stratum"] == "all"}
        rows.append(dict(method=method, family="point/surface", single_km=float(scopes["single"]["median_error_km"]), group8_km=float(scopes["group8"]["median_error_km"]), full_km=float(scopes["full"]["median_error_km"])))
    for r in csv.DictReader((SOURCE / "portable-comparison.csv").open()):
        if int(r["complete_count"]) != int(r["expected_count"]):
            raise ValueError("Portable comparison incomplete")
        rows.append(dict(method=r["method_label"], family="portable", single_km=float(r["single_median_error_km"]), group8_km=float(r["group8_median_error_km"]), full_km=float(r["full_error_km"])))
    (HERE / "comparison.json").write_text(json.dumps({"dataset": "DS5", "reference": reference, "reference_used_postseal_only": True, "rows": rows}, indent=2)+"\n")
    with (HERE / "comparison.csv").open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    fig, ax = plt.subplots(figsize=(13, 10), constrained_layout=True)
    y = np.arange(len(rows))
    for i, (key, label) in enumerate((("single_km", "Single median"), ("group8_km", "Group8 median"), ("full_km", "Full42"))):
        ax.scatter([r[key] for r in rows], y+(i-1)*.2, label=label, s=24)
    ax.set_yticks(y, [r["method"].replace("selected-point-", "").replace("surface-fusion-", "surface: ") for r in rows])
    ax.set_xscale("log"); ax.set_xlabel("Horizontal error to reference (km; logarithmic scale)")
    ax.axvline(1, color="gray", linestyle="--", label="1 km target")
    ax.set_title("DS5 completed point/surface and portable families\nDifferent estimation procedures; shared dataset membership")
    ax.legend(); ax.grid(axis="x", alpha=.2); fig.savefig(HERE / "comparison.png", dpi=160); plt.close(fig)
    lines = ["| Method | Single median km | Group8 median km | Full42 km |", "|---|---:|---:|---:|"]
    lines += [f"| {r['method']} | {r['single_km']:.3f} | {r['group8_km']:.3f} | {r['full_km']:.3f} |" for r in rows]
    (HERE / "comparison-table.md").write_text("\n".join(lines)+"\n")
    names = ["comparison.json", "comparison.csv", "comparison.png", "comparison-table.md"]
    (HERE / "SHA256SUMS").write_text("".join(f"{hashlib.sha256((HERE/n).read_bytes()).hexdigest()}  {n}\n" for n in names))


if __name__ == "__main__":
    build()
