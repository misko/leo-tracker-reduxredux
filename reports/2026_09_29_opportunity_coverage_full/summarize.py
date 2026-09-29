"""Replay every record and independently check disjoint sample coverage."""

import gzip
import json
from collections import Counter, defaultdict

from study import HERE, PILOT, read, save, summarize, verify


def main():
    verify()
    assert read(HERE / "exit.json")["exit_code"] == 0
    records = []
    groups = defaultdict(Counter)
    for row in read(HERE / "plan.json")["records"]:
        if row["pilot"]:
            data = read(PILOT / (row["pilot"] + ".json"))
        else:
            name = HERE / "records" / row["session_id"]
            data = json.loads(gzip.decompress(name.with_suffix(".json.gz").read_bytes()))
        assert data["session_id"] == row["session_id"]
        assert data["manifest_sha256"] == row["manifest_sha256"]
        summary = summarize(data)
        if not row["pilot"]:
            assert json.loads(json.dumps(summary)) == read(name.with_suffix(".summary.json"))
        assert data["qualified"] and data["timing_qualified"]
        intervals = defaultdict(list)
        probes = defaultdict(list)
        for p in data["probes"]:
            intervals[p["receiver"], p["visit_index"]].append(
                (p["start_ms"], p["start_ms"] + data["probe_ms"])
            )
            probes[p["receiver"], p["visit_index"]].append(p)
        for rx in (0, 1):
            independent_covered = 0
            independent_valid = 0
            for v in data["visits"]:
                windows = sorted(intervals[rx, v["visit_index"]])
                # Disjoint probes make summed lengths equal the union independently.
                assert all(a[1] <= b[0] for a, b in zip(windows, windows[1:], strict=False))
                samples = v["end"] - v["start"]
                covered = sum(b - a for a, b in windows) * data["rate"] // 1000
                assert covered <= samples
                independent_covered += covered
                independent_valid += samples
                dwell = samples * 1000 / data["rate"]
                key = (row["dataset"], row["role"], rx, dwell)
                g = groups[key]
                g["visits"] += 1
                g["valid_samples"] += samples
                g["covered_samples"] += covered
                # Aggregate seconds, rather than sample counts across unequal sampling rates.
                g["valid_seconds"] += samples / data["rate"]
                g["covered_seconds"] += covered / data["rate"]
                g["probes"] += len(windows)
                g["zero_passing"] += sum(p["passing"] == 0 for p in probes[rx, v["visit_index"]])
                g["missing_visit"] += not windows
            assert independent_covered == summary["receivers"][rx]["covered_samples"]
            assert independent_valid == summary["receivers"][rx]["valid_samples"]
        summary["role"] = row["role"]
        records.append(summary)
    assert len(records) == 258
    group_rows = [
        dict(
            dataset=k[0],
            role=k[1],
            receiver=k[2],
            dwell_ms=k[3],
            **v,
            coverage_fraction=v["covered_seconds"] / v["valid_seconds"],
        )
        for k, v in sorted(groups.items())
    ]
    aggregate = {}
    for ds in ("DS7", "DS8", "DS9"):
        rs = [r for r in records if r["dataset"] == ds]
        outcomes = Counter()
        for r in rs:
            outcomes.update(r["outcomes"])
        aggregate[ds] = dict(
            records=len(rs),
            targets=sum(r["role"] == "target" for r in rs),
            visits=sum(r["visits"] for r in rs),
            outcomes=dict(outcomes),
            receiver_coverage_range={
                str(rx): [
                    min(r["receivers"][rx]["coverage_fraction"] for r in rs),
                    max(r["receivers"][rx]["coverage_fraction"] for r in rs),
                ]
                for rx in (0, 1)
            },
        )
    save(
        HERE / "summary.json",
        dict(audit_passed=True, records=records, groups=group_rows, datasets=aggregate),
    )
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
