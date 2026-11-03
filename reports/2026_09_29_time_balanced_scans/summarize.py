import hashlib
import json
import sys
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


def main(prefix=""):
    reference = json.loads(
        (HERE.parent / "2026_09_29_unassociated_trend/summary.json").read_text()
    )["reference"]
    manifest = json.loads((HERE / "manifest.json").read_text())
    rows, missing = [], []
    table = [
        "| Set | Qualified | Error m | Start span h | Tracks | Held log score |",
        "|---|:---:|---:|---:|---:|---:|",
    ]
    for unit in manifest["sets"]:
        path = HERE / f"{prefix}{unit['unit']}.json"
        if not path.exists():
            missing.append(unit["unit"])
            continue
        row = json.loads(path.read_text())
        for name, digest in row["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        selected = row["selected"]
        row["qualified"] = selected is not None
        row["error_m"] = distance(selected["estimate_deg"], reference) if selected else None
        rows.append(row)
        if selected:
            table.append(
                f"| {row['unit']} | yes | {row['error_m']:.2f} "
                f"| {row['start_span_hours']:.3f} | {row['tracks']} "
                f"| {selected['held_score']:.3f} |"
            )
        else:
            table.append(
                f"| {row['unit']} | NO | — | {row['start_span_hours']:.3f} | {row['tracks']} | — |"
            )
    aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        groups = {
            arm: [r for r in rows if r["dataset"] == ds and r["arm"] == arm]
            for arm in ("contiguous", "balanced")
        }
        complete = all(len(g) == 3 and all(r["qualified"] for r in g) for g in groups.values())
        if complete:
            a, b = groups["contiguous"], groups["balanced"]
            assert sorted(s for r in a for s in r["sessions"]) == sorted(
                s for r in b for s in r["sessions"]
            )
            assert sum(r["tracks"] for r in a) == sum(r["tracks"] for r in b)
            assert sum(r["observations"] for r in a) == sum(r["observations"] for r in b)
            aggregates.append(
                dict(
                    dataset=ds,
                    complete=True,
                    contiguous_median_m=float(np.median([r["error_m"] for r in a])),
                    balanced_median_m=float(np.median([r["error_m"] for r in b])),
                    contiguous_subkm=sum(r["error_m"] < 1000 for r in a),
                    balanced_subkm=sum(r["error_m"] < 1000 for r in b),
                    held_total_gain=sum(r["selected"]["held_score"] for r in b)
                    - sum(r["selected"]["held_score"] for r in a),
                    contiguous_span_h=float(np.median([r["start_span_hours"] for r in a])),
                    balanced_span_h=float(np.median([r["start_span_hours"] for r in b])),
                )
            )
        else:
            aggregates.append(dict(dataset=ds, complete=False))
    (HERE / f"{prefix}TABLE.md").write_text("\n".join(table) + "\n")
    (HERE / f"{prefix}summary.json").write_text(
        json.dumps(
            dict(reference=reference, rows=rows, missing=missing, aggregates=aggregates), indent=2
        )
        + "\n"
    )
    print(json.dumps(dict(missing=missing, aggregates=aggregates), indent=2))


if __name__ == "__main__":
    main("grid_" if len(sys.argv) > 1 and sys.argv[1] == "grid" else "")
