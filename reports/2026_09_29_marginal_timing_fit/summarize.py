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
    rows, missing = [], []
    table = [
        "| Panel | Train half | Qualified | Profile error m | Marginal error m "
        "| Movement m | Whole-scan gain |",
        "|---|---|:---:|---:|---:|---:|---:|",
    ]
    for ds in (7, 8, 9):
        for part in ("early", "middle", "late"):
            key = f"DS{ds}_{part}_8"
            for direction in (0, 1):
                path = HERE / f"{key}_d{direction}.json"
                if not path.exists():
                    missing.append(dict(unit=key, direction=direction))
                    table.append(
                        f"| {key} | {'first' if direction == 0 else 'last'} "
                        "| NO OUTPUT | — | — | — | — |"
                    )
                    continue
                row = json.loads(path.read_text())
                for name, digest in row["hashes"].items():
                    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
                row["baseline_error_m"] = distance(row["baseline_estimate_deg"], reference)
                row["error_m"] = distance(row["estimate_deg"], reference)
                row["movement_m"] = distance(row["baseline_estimate_deg"], row["estimate_deg"])
                rows.append(row)
                table.append(
                    f"| {key} | {'first' if direction == 0 else 'last'} "
                    f"| {'yes' if row['qualified'] else 'NO'} "
                    f"| {row['baseline_error_m']:.2f} | {row['error_m']:.2f} "
                    f"| {row['movement_m']:.2f} "
                    f"| {row['target_gain']:+.3f} |"
                )
    aggregates = []
    for ds in (7, 8, 9):
        selected = [r for r in rows if r["unit"].startswith(f"DS{ds}_") and r["qualified"]]
        aggregates.append(
            dict(
                dataset=f"DS{ds}",
                qualified=len(selected),
                baseline_median_m=float(np.median([r["baseline_error_m"] for r in selected]))
                if selected
                else None,
                median_m=float(np.median([r["error_m"] for r in selected])) if selected else None,
                target_wins=sum(r["target_gain"] > 0 for r in selected),
                geographic_wins=sum(r["error_m"] < r["baseline_error_m"] for r in selected),
                target_gain_sum=sum(r["target_gain"] for r in selected),
                baseline_subkm=sum(r["baseline_error_m"] < 1000 for r in selected),
                subkm=sum(r["error_m"] < 1000 for r in selected),
            )
        )
    (HERE / "TABLE.md").write_text("\n".join(table) + "\n")
    (HERE / "summary.json").write_text(
        json.dumps(
            dict(reference=reference, rows=rows, missing=missing, aggregates=aggregates), indent=2
        )
        + "\n"
    )
    print(json.dumps(dict(missing=missing, aggregates=aggregates), indent=2))


if __name__ == "__main__":
    main()
