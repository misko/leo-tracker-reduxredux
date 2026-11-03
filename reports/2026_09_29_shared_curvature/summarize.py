import hashlib
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    h = (
        math.sin((lat1 - lat2) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon1 - lon2) / 2) ** 2
    )
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def main():
    reference_path = HERE.parent / "2026_09_29_unassociated_trend/summary.json"
    reference = json.loads(reference_path.read_text())["reference"]
    rows = []
    failures = []
    for ds in ("DS7", "DS8", "DS9"):
        for window in ("early", "middle", "late"):
            key = f"{ds}_{window}_8"
            receipt = json.loads((HERE / f"{key}.receipt.json").read_text())
            path = HERE / f"{key}_0.1.json"
            if receipt["exit_code"] != 0 or not path.exists():
                failures.append(dict(unit=key, receipt=receipt))
                continue
            result = json.loads(path.read_text())
            for name, h in result["hashes"].items():
                assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
            row = dict(
                unit=key,
                dataset=ds,
                qualified=result["qualified"],
                baseline_error_m=distance(reference, result["baseline_estimate_deg"]),
                curvature_error_m=distance(reference, result["estimate_deg"]),
                movement_m=distance(result["baseline_estimate_deg"], result["estimate_deg"]),
                held_gain=result["held_score"] - result["baseline_held_score"],
                common_held_gain=result["common_held_score"] - result["baseline_held_score"],
                groups=result["groups"],
                grouped_tracks=result["grouped_tracks"],
            )
            rows.append(row)
            if not result["qualified"]:
                failures.append(dict(unit=key, reason="numerical qualification"))
    aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        subset = [r for r in rows if r["dataset"] == ds and r["qualified"]]
        aggregates.append(
            dict(
                dataset=ds,
                qualified_panels=len(subset),
                baseline_median_m=float(np.median([r["baseline_error_m"] for r in subset]))
                if subset
                else None,
                curvature_median_m=float(np.median([r["curvature_error_m"] for r in subset]))
                if subset
                else None,
            )
        )
    with (HERE / "summary.json").open("x") as f:
        json.dump(
            dict(
                rows=rows,
                failures=failures,
                aggregates=aggregates,
                reference=reference,
                reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            ),
            f,
            indent=2,
        )
    lines = [
        "| Panel | Qualified | Baseline error m | Curvature error m | Movement m | "
        "Held gain | Original-model held gain |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['unit']} | {r['qualified']} | {r['baseline_error_m']:.2f} | "
            f"{r['curvature_error_m']:.2f} | {r['movement_m']:.2f} | "
            f"{r['held_gain']:+.3f} | {r['common_held_gain']:+.3f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(aggregates=aggregates, failures=failures), indent=2))


if __name__ == "__main__":
    main()
