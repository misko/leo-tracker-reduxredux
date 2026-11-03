import hashlib
import json
from pathlib import Path

import numpy as np

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
    rows = []
    table = [
        "| Panel | Slope SD, Hz/s | Qualified | Baseline m | Shared-slope m "
        "| Held gain | Common-model held gain |",
        "|---|---:|:---:|---:|---:|---:|---:|",
    ]
    for ds in (7, 8, 9):
        for part in ("early", "middle", "late"):
            key = f"DS{ds}_{part}_8"
            for sigma in (0.5, 2.0):
                r = json.loads((HERE / f"{key}_{sigma:g}.json").read_text())
                for name, digest in r["hashes"].items():
                    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
                r["baseline_error_m"] = distance(r["baseline_estimate_deg"], reference)
                r["error_m"] = distance(r["estimate_deg"], reference)
                r["held_gain"] = r["held_score"] - r["baseline_held_score"]
                r["common_held_gain"] = r["common_held_score"] - r["baseline_held_score"]
                rows.append(r)
                table.append(
                    f"| {key} | {sigma:g} | {'yes' if r['qualified'] else 'NO'} "
                    f"| {r['baseline_error_m']:.2f} | {r['error_m']:.2f} "
                    f"| {r['held_gain']:+.3f} | {r['common_held_gain']:+.3f} |"
                )
    aggregates = []
    for ds in (7, 8, 9):
        for sigma in (0.5, 2.0):
            s = [r for r in rows if r["unit"].startswith(f"DS{ds}_") and r["sigma"] == sigma]
            aggregates.append(
                dict(
                    dataset=f"DS{ds}",
                    sigma=sigma,
                    qualified=sum(r["qualified"] for r in s),
                    baseline_median_m=float(np.median([r["baseline_error_m"] for r in s])),
                    median_m=float(np.median([r["error_m"] for r in s])),
                    geographic_wins=sum(r["error_m"] < r["baseline_error_m"] for r in s),
                    held_wins=sum(r["held_gain"] > 0 for r in s),
                )
            )
    (HERE / "TABLE.md").write_text("\n".join(table) + "\n")
    (HERE / "summary.json").write_text(
        json.dumps(dict(reference=reference, rows=rows, aggregates=aggregates), indent=2) + "\n"
    )
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
