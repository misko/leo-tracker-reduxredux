"""Score sealed global and tile-assisted predictions against v5 and the supplied tile centre."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import read_predictions, references
from ..scoring import ARMS, distance_km, distribution
from .full_v5_check import _load_case
from .prefix_figures import REPORT as V5_REPORT
from .prefix_figures import TIMING_IDS, csv_file

METHODS = {
    "point_votes": "point-votes",
    "rate_triplets": "rate-triplets",
    "folded_doppler": "folded-doppler",
}
MODES = ("global", "matched-tile")


def comparison_row(case, ref, row, v5, method, mode, arm):
    result = row["result"]
    endpoint = result.get("arms", {}).get(arm, {})
    control = ref["reference"]["baseline"][arm]
    original = v5["result"]["arms"][arm]["latlon"]
    if distance_km(original, control["latlon"]) > 1e-6:
        raise ValueError(f"paired v5 timing control differs from frozen v5 on {case['id']}")
    (tile,) = case["regions"]
    truth = ref["truth"]
    return dict(
        method=method,
        mode=mode,
        id=case["id"],
        dataset=ref["group"],
        arm=arm,
        status=result["status"],
        returned_km=distance_km(endpoint.get("latlon"), truth),
        forced_km=distance_km(endpoint.get("forced_latlon"), truth),
        v5_km=control["error_km"],
        prior_center_km=distance_km(tile["center"], truth) if mode == "matched-tile" else None,
        worker_wall_s=row.get("worker_wall_s"),
        v5_worker_wall_s=v5["worker_wall_s"],
    )


def summarize(rows):
    summary = []
    for key in dict.fromkeys((r["method"], r["mode"], r["dataset"], r["arm"]) for r in rows):
        method, mode, dataset, arm = key
        group = [r for r in rows if (r["method"], r["mode"], r["dataset"], r["arm"]) == key]
        out = dict(method=method, mode=mode, dataset=dataset, arm=arm, attempts=len(group))
        for name in ("returned", "forced", "v5", "prior_center"):
            errors = [r[name + "_km"] for r in group if r[name + "_km"] is not None]
            stats = distribution(errors)
            out.update(
                {
                    name + "_count": len(errors),
                    name + "_within_5_km": sum(e <= 5 for e in errors),
                    name + "_median_km": stats["p50"],
                    name + "_p95_km": stats["p95"],
                }
            )
        for name in ("worker_wall_s", "v5_worker_wall_s"):
            out["median_" + name] = distribution([r[name] for r in group])["p50"]
        summary.append(out)
    return summary


def score(directory, methods):
    refs = {r["id"]: r for p in ("ds26-all159", "roof16") for r in references(p, None)[1]}
    with gzip.open(V5_REPORT / "paired.jsonl.gz") as stream:
        v5 = {r["id"]: r for r in map(json.loads, stream) if r["method"] == "v5_lean"}
    rows = []
    for method in methods:
        records = {
            mode: read_predictions(directory / METHODS[method] / (mode + ".jsonl.gz"))
            for mode in MODES
        }
        ids = set(records["global"])
        if not ids or not ids <= set(TIMING_IDS) or ids != set(records["matched-tile"]):
            raise ValueError("cold and supplied-tile policies must use the same recording roster")
        for case_id in TIMING_IDS:
            if case_id not in ids:
                continue
            case, ref = _load_case(case_id), refs[case_id]
            for mode in MODES:
                row = records[mode][case_id]
                if row["method"] != method or row["mode"] != mode:
                    raise ValueError(
                        "prediction method or location-prior mode differs from its file"
                    )
                if (
                    row.get("native_sha256") != case["native"]["sha256"]
                    or row.get("catalog_sha256") != case["catalog"]["sha256"]
                ):
                    raise ValueError(
                        "cold receiver prediction uses different detector or orbital inputs"
                    )
                rows.extend(
                    comparison_row(case, ref, row, v5[case_id], method, mode, arm) for arm in ARMS
                )
    csv_file(directory / "per-recording.csv", rows)
    csv_file(directory / "distributions.csv", summarize(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--method", action="append", choices=METHODS)
    args = parser.parse_args()
    score(args.report, args.method or METHODS)


if __name__ == "__main__":
    main()
