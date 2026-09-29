"""Independent reconstruction of conditional transfer and paired scores."""

from collections import defaultdict
from statistics import median

import numpy as np

from study import HERE, PRIOR, read, save, verify


def predictor(target, donors, shuffled):
    cells = defaultdict(list)
    for d in donors:
        if (
            d["available_utc_ns"] < target["start_utc_ns"]
            and d["receiver_id"] == target["receiver_id"]
        ):
            cells[d["unit_id"], d["rf_hz"]].append(d)
    excess = defaultdict(list)
    baseline = {}
    for (group, rf), rows in cells.items():
        rows = sorted(rows, key=lambda d: (d["number"], d["session_id"], d["track_id"]))
        slopes = [r["shape"]["slope"] for r in rows]
        if shuffled:
            slopes = slopes[-1:] + slopes[:-1]
        by_id = defaultdict(list)
        for r, slope in zip(rows, slopes, strict=True):
            by_id[r["number"]].append(slope)
        other = [median(v) for n, v in by_id.items() if n != target["number"]]
        if len(other) < 2:
            continue
        if rf == target["rf_hz"]:
            baseline[group] = median(other)
        if target["number"] in by_id:
            excess[group].append(median(by_id[target["number"]]) - median(other))
    if len(excess) < 2 or len(baseline) < 2:
        return None
    return dict(
        candidate_groups=sorted(excess),
        candidate_group_excess=[median(excess[g]) for g in sorted(excess)],
        rf_groups=sorted(baseline),
        rf_group_slopes=[baseline[g] for g in sorted(baseline)],
        rf_slope=median(baseline.values()),
        excess_slope=median(median(v) for v in excess.values()),
    )


def main():
    verify(read(HERE / "seal.json")["sha256"])
    donors, targets = [], []
    for u in read(HERE / "plan.json")["units"]:
        cases = read(PRIOR / "runs" / u["unit_id"] / "result.json")["cases"]
        (donors if u["role"] == "donor" else targets).extend(cases)
    ends = defaultdict(set)
    for d in donors:
        ends[d["unit_id"]].add(d["available_utc_ns"])
    assert all(len(v) == 1 for v in ends.values())
    result = read(HERE / "result.json")
    assert result["donor_cases"] == len(donors)
    assert result["target_cases"] == len(targets)
    for t, row in zip(targets, result["rows"], strict=True):
        assert all(t[k] == row[k] for k in ("unit_id", "session_id", "track_id", "number"))
        p, s = predictor(t, donors, False), predictor(t, donors, True)
        assert row["matched"] == (p is not None) == (s is not None)
        if p is None:
            continue
        for expected, stored in ((p, row["real"]), (s, row["shuffle"])):
            for k, v in expected.items():
                if k.endswith("groups"):
                    assert v == stored[k]
                else:
                    np.testing.assert_allclose(v, stored[k], rtol=1e-12, atol=1e-12)
        slopes = dict(
            zero=0,
            rf=p["rf_slope"],
            candidate=p["rf_slope"] + p["excess_slope"],
            shuffled=p["rf_slope"] + s["excess_slope"],
        )
        mask = np.asarray(t["mask"], bool)
        times, residual = np.asarray(t["times"]), np.asarray(t["residual"])
        for arm, slope in slopes.items():
            np.testing.assert_allclose(slope, row["slopes"][arm], atol=1e-12)
            error = abs(residual - residual[mask].mean() - slope * (times - times[mask].mean()))
            for split, select in (("training", mask), ("held", ~mask)):
                np.testing.assert_allclose(
                    median(error[select]), row["errors"][arm][split + "_median_abs"], atol=1e-9
                )
    panels = {}
    for unit in sorted({r["unit_id"] for r in result["rows"]}):
        allrows = [r for r in result["rows"] if r["unit_id"] == unit]
        rows = [r for r in allrows if r["matched"]]
        panels[unit] = aggregate(rows) | dict(eligible=len(allrows))
    summary = dict(
        audit_passed=True,
        panels=panels,
        overall=aggregate([r for r in result["rows"] if r["matched"]]),
        donor_cases=len(donors),
        target_cases=len(targets),
        rotated_cases=result["rotated_cases"],
        unchanged_label_cases=result["unchanged_label_cases"],
    )
    save(HERE / "summary.json", summary)
    print(summary)


def aggregate(rows):
    if not rows:
        return dict(matched=0)
    values = {
        a: [r["errors"][a]["held_median_abs"] for r in rows]
        for a in ("zero", "rf", "candidate", "shuffled")
    }
    gains = {
        a: [x - y for x, y in zip(values[a], values["candidate"], strict=True)]
        for a in ("zero", "rf", "shuffled")
    }
    return dict(
        matched=len(rows),
        median_held_hz={a: median(v) for a, v in values.items()},
        candidate_paired_gain_hz={a: median(v) for a, v in gains.items()},
        candidate_wins={a: sum(x > 0 for x in v) for a, v in gains.items()},
    )


if __name__ == "__main__":
    main()
