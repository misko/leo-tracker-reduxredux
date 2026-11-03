import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    h = (
        math.sin((lat1 - lat2) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon1 - lon2) / 2) ** 2
    )
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def mixture(scores):
    top = max(scores)
    return top + math.log(sum(math.exp(v - top) for v in scores) / len(scores))


def main():
    reference_path = HERE.parent / "2026_09_29_unassociated_trend/summary.json"
    reference = json.loads(reference_path.read_text())["reference"]
    targets = json.loads((HERE.parent / "2026_09_29_out_of_pool/manifest.json").read_text())
    pools = json.loads((HERE.parent / "2026_09_29_scan_budget/manifest.json").read_text())
    assert targets["config"] == pools["config"]
    rows = []
    target_rows = []
    failures = []
    for ds in ("DS7", "DS8", "DS9"):
        receipt = json.loads((HERE / f"{ds}.receipt.json").read_text())
        path = HERE / f"{ds}.json"
        if receipt["exit_code"] != 0 or not path.exists():
            failures.append(dict(dataset=ds, receipt=receipt))
            continue
        d = json.loads(path.read_text())
        for name, h in d["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
        if not d["qualified"]:
            failures.append(dict(dataset=ds, reason="numerical qualification"))
        for t in d["targets"]:
            frozen = next(s for s in targets["sets"] if s["unit"] == t["unit"])
            assert frozen["positions"][1] == d["baseline"]["x"][:2]
            assert t["session_id"] not in d["source_sessions"]
            old = [v["log_score"] for v in t["prior_values"]]
            target_rows.append(
                dict(
                    dataset=ds,
                    unit=t["unit"],
                    qualified=t["qualified"],
                    curvature_minus_baseline=t["log_score"] - old[1],
                    curvature_minus_center=t["log_score"] - old[0],
                    curvature_minus_n8_mixture=t["log_score"] - mixture(old[2:]),
                )
            )
        subset = [r for r in target_rows if r["dataset"] == ds]
        row = dict(
            dataset=ds,
            qualified=d["qualified"],
            baseline_error_m=distance(reference, d["baseline"]["estimate_deg"]),
            curvature_error_m=distance(reference, d["fit"]["estimate_deg"]),
            movement_m=distance(d["baseline"]["estimate_deg"], d["fit"]["estimate_deg"]),
            source_held_gain=d["fit"]["source_held_score"] - d["source_baseline_held_score"],
            groups=d["groups"],
            grouped_tracks=d["grouped_tracks"],
        )
        for comparator in ("baseline", "center", "n8_mixture"):
            key = "curvature_minus_" + comparator
            row[key] = sum(r[key] for r in subset)
            row[key + "_wins"] = sum(r[key] > 0 for r in subset)
        rows.append(row)
    with (HERE / "summary.json").open("x") as f:
        json.dump(
            dict(
                rows=rows,
                targets=target_rows,
                failures=failures,
                reference=reference,
                reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            ),
            f,
            indent=2,
        )
    lines = [
        "| Dataset | Qualified | Baseline m | Curvature m | "
        "vs baseline log score | vs center | vs N8 mixture |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['dataset']} | {r['qualified']} | {r['baseline_error_m']:.2f} | "
            f"{r['curvature_error_m']:.2f} | {r['curvature_minus_baseline']:+.3f} | "
            f"{r['curvature_minus_center']:+.3f} | {r['curvature_minus_n8_mixture']:+.3f} |"
        )
    lines.extend(
        ["", "| Target | vs baseline | vs center | vs N8 mixture |", "|---|---:|---:|---:|"]
    )
    for r in target_rows:
        lines.append(
            f"| {r['unit']} | {r['curvature_minus_baseline']:+.3f} | "
            f"{r['curvature_minus_center']:+.3f} | {r['curvature_minus_n8_mixture']:+.3f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(rows=rows, failures=failures), indent=2))


if __name__ == "__main__":
    main()
