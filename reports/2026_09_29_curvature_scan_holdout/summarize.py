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
        for w in ("early", "middle", "late"):
            for direction in (0, 1):
                key = f"{ds}_{w}_8_d{direction}"
                receipt = json.loads((HERE / f"{key}.receipt.json").read_text())
                path = HERE / f"{key}.json"
                if receipt["exit_code"] != 0 or not path.exists():
                    failures.append(dict(unit=key, receipt=receipt))
                    continue
                data = json.loads(path.read_text())
                for name, h in data["hashes"].items():
                    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
                assert len(data["source_sessions"]) == len(data["target_sessions"]) == 4
                assert not set(data["source_sessions"]) & set(data["target_sessions"])
                a, b = data["arms"]
                qualified = all(x["qualified"] for x in (a, b))
                if not qualified:
                    failures.append(dict(unit=key, reason="numerical qualification"))
                for arm in (a, b):
                    assert [t["session_id"] for t in arm["target_scans"]] == data["target_sessions"]
                    assert (
                        abs(
                            sum(t["log_score"] for t in arm["target_scans"])
                            - arm["target_log_score"]
                        )
                        < 1e-7
                    )
                rows.append(
                    dict(
                        unit=key,
                        dataset=ds,
                        qualified=qualified,
                        baseline_error_m=distance(reference, a["estimate_deg"]),
                        curvature_error_m=distance(reference, b["estimate_deg"]),
                        movement_m=distance(a["estimate_deg"], b["estimate_deg"]),
                        source_held_gain=b["source_held_score"] - a["source_held_score"],
                        target_gain=b["target_log_score"] - a["target_log_score"],
                        groups=data["groups"],
                        grouped_tracks=data["grouped_tracks"],
                    )
                )
    aggregates = []
    for ds in ("DS7", "DS8", "DS9", "all"):
        subset = [r for r in rows if r["qualified"] and (ds == "all" or r["dataset"] == ds)]
        aggregates.append(
            dict(
                dataset=ds,
                pairs=len(subset),
                geographic_wins=sum(r["curvature_error_m"] < r["baseline_error_m"] for r in subset),
                target_wins=sum(r["target_gain"] > 0 for r in subset),
                target_gain=sum(r["target_gain"] for r in subset),
                source_held_wins=sum(r["source_held_gain"] > 0 for r in subset),
                baseline_subkm=sum(r["baseline_error_m"] < 1000 for r in subset),
                curvature_subkm=sum(r["curvature_error_m"] < 1000 for r in subset),
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
                aggregates=aggregates,
                failures=failures,
                reference=reference,
                reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            ),
            f,
            indent=2,
        )
    lines = [
        "| Split | Qualified | Baseline m | Curvature m | Source held gain | Whole-target gain |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['unit']} | {r['qualified']} | {r['baseline_error_m']:.2f} | "
            f"{r['curvature_error_m']:.2f} | {r['source_held_gain']:+.3f} | "
            f"{r['target_gain']:+.3f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(aggregates=aggregates, failures=failures), indent=2))


if __name__ == "__main__":
    main()
