"""Compare matched RF-level and offer-order controls after the prediction commitment."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def coordinate_change(a, b):
    if a is None or b is None:
        return None if a == b else math.inf
    lon = math.radians(math.remainder(a[1] - b[1], 360))
    x, y = math.radians(a[0]), math.radians(b[0])
    h = math.sin((x - y) / 2)**2 + math.cos(x) * math.cos(y) * math.sin(lon / 2)**2
    return 12_742_017.6 * math.asin(math.sqrt(min(1.0, h)))


def compare(a, b):
    equal = all(a[key] == b[key] for key in ("status", "reason", "best_region", "region_id"))
    p, q = a["diagnostics"], b["diagnostics"]
    equal &= all(p.get(key) == q.get(key) for key in
                 ("region_result", "track_counts", "work", "sky", "tile_work", "forced_source"))
    coords = [coordinate_change(a[k], b[k]) for k in ("latlon", "best_latlon")]
    scores, errors, supports = [], [], 0
    regions = p.get("regional_scores", {})
    if regions.keys() != q.get("regional_scores", {}).keys():
        raise ValueError("regional alternatives changed")
    for reg, stages in regions.items():
        for stage, x in stages.items():
            y = q["regional_scores"][reg][stage]
            if x is None or y is None:
                equal &= x == y
                continue
            supports += int(x["n_tracks"] != y["n_tracks"])
            for key, bounds in [("score", scores), ("rms_hz", errors)]:
                if x[key] is None or y[key] is None:
                    equal &= x[key] == y[key]
                else:
                    bounds.append(abs(x[key] - y[key]))
    u, v = p.get("held_evidence", {}), q.get("held_evidence", {})
    s1, s2 = u.get("null_maxima", []), v.get("null_maxima", [])
    scores.extend(abs(x - y) for x, y in zip(s1, s2, strict=True))
    return {"id": a["id"], "arm": b["arm"], "decision_and_work_equal": equal,
            "support_mismatches": supports, "scored_metric_comparisons": len(scores),
            "rms_comparisons": len(errors), "max_abs_shape_score": max(scores, default=None),
            "max_abs_shape_rms_hz": max(errors, default=None),
            "max_coordinate_change_m": max((x for x in coords if x is not None), default=None)}


def run(root, panel):
    lock = json.loads((root / "locks" / "prediction-lock.json").read_bytes())
    docs = []
    for name in [panel + ".json", panel + "-checks.json"]:
        data = (root / "predictions" / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != lock["sha256"][name]:
            raise ValueError("prediction digest mismatch")
        docs.append(json.loads(data)["cases"])
    primary, checks = docs
    primary = {r["id"]: r for r in primary}
    rows = [compare(primary[r["id"]], r) for r in checks]
    summary = {"comparisons": len(rows), "decision_or_work_changes": sum(
        not r["decision_and_work_equal"] for r in rows),
        "support_mismatches": sum(r["support_mismatches"] for r in rows)}
    for key in ("max_abs_shape_score", "max_abs_shape_rms_hz", "max_coordinate_change_m"):
        summary[key] = max((r[key] for r in rows if r[key] is not None), default=None)
    return {"summary": summary, "comparisons": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panels", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lab = Path(__file__).resolve().parents[1]
    reports = {p: run(lab, p) for p in args.panels}
    args.output.write_text(json.dumps(reports, indent=2, allow_nan=False) + "\n")
