import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text())


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    q = (
        math.sin((lat1 - lat2) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon1 - lon2) / 2) ** 2
    )
    return 2 * 6371008.8 * math.asin(math.sqrt(q))


def main():
    manifest = read(HERE / "manifest.json")
    for name, expected in manifest["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    refpath = HERE.parent / "2026_09_29_unassociated_trend/summary.json"
    reference = read(refpath)["reference"]
    rows, failures = [], []
    for ds in ("DS7", "DS8", "DS9"):
        receipt = read(HERE / f"{ds}.receipt.json")
        if receipt["exit_code"] != 0:
            failures.append(dict(dataset=ds, receipt=receipt))
            continue
        result = read(HERE / f"{ds}.json")
        assert (
            result["manifest_sha256"]
            == hashlib.sha256((HERE / "manifest.json").read_bytes()).hexdigest()
        )
        before, after = result["before"], result["after"]
        assert [(r["di"], r["ti"], r["track_id"]) for r in before["rows"]] == [
            (r["di"], r["ti"], r["track_id"]) for r in after["rows"]
        ]
        targets = result["targets"]
        assert len(targets) == 4
        qualified = result["fit"]["qualified"] and all(
            t[a]["qualified"] for t in targets for a in ("baseline", "surrogate")
        )
        deltas = [t["surrogate"]["log_score"] - t["baseline"]["log_score"] for t in targets]
        row = dict(
            dataset=ds,
            qualified=qualified,
            source_tracks=len(before["rows"]),
            baseline_error_m=distance(result["baseline"]["estimate_deg"], reference),
            surrogate_error_m=distance(result["fit"]["estimate_deg"], reference),
            position_shift_m=distance(
                result["fit"]["estimate_deg"], result["baseline"]["estimate_deg"]
            ),
            surrogate_source_gain=result["fit"]["score"] - result["initial_surrogate_score"],
            exact_source_gain=after["exact_score"] - before["exact_score"],
            initial_exact_minus_surrogate=before["exact_score"] - result["initial_surrogate_score"],
            final_exact_minus_surrogate=after["exact_score"] - result["fit"]["score"],
            final_min_retained_mass=min(r["retained_mass"] for r in after["rows"]),
            final_missing_best=sum(not r["best_retained"] for r in after["rows"]),
            changed_full_counts=sum(
                a["full_count"] != b["full_count"]
                for a, b in zip(after["rows"], before["rows"], strict=True)
            ),
            max_full_count_change=max(
                abs(a["full_count"] - b["full_count"])
                for a, b in zip(after["rows"], before["rows"], strict=True)
            ),
            target_score_gain=sum(deltas),
            target_wins=sum(d > 0 for d in deltas),
            target_deltas=deltas,
            elapsed_seconds=result["elapsed_seconds"],
        )
        rows.append(row)
    with (HERE / "summary.json").open("x") as out:
        json.dump(
            dict(
                rows=rows,
                failures=failures,
                reference=reference,
                reference_source_sha256=hashlib.sha256(refpath.read_bytes()).hexdigest(),
            ),
            out,
            indent=2,
            allow_nan=False,
        )
    print(json.dumps(dict(rows=rows, failures=failures), indent=2))


if __name__ == "__main__":
    main()
