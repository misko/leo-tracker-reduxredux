"""Coverage accounting in integer device samples, independently of UTC rounding."""

import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def union_length(intervals):
    total, right = 0, None
    for start, end in sorted(intervals):
        if end <= start:
            raise ValueError("nonpositive interval")
        total += max(0, end - max(start, right if right is not None else start))
        right = max(end, right if right is not None else end)
    return total


def summarize(raw):
    visits = {v["visit_index"]: v for v in raw["visits"]}
    assert len(visits) == len(raw["visits"])
    coverage = defaultdict(list)
    keys = set()
    paired = defaultdict(dict)
    counts = defaultdict(Counter)
    outside = 0
    for p in raw["probes"]:
        key = (p["visit_index"], p["probe_index"], p["start_ms"])
        fullkey = (*key, p["receiver"])
        assert fullkey not in keys
        keys.add(fullkey)
        v = visits[p["visit_index"]]
        assert p["valid_start_counter"] == v["start"]
        assert p["rf_hz"] == v["rf_hz"]
        assert p["receiver"] in (0, 1)
        assert 0 <= p["passing"] <= p["candidates"]
        assert p["start_ms"] * raw["rate"] % 1000 == 0
        assert raw["probe_ms"] * raw["rate"] % 1000 == 0
        start = v["start"] + p["start_ms"] * raw["rate"] // 1000
        end = start + raw["probe_ms"] * raw["rate"] // 1000
        outside += not (v["start"] <= start < end <= v["end"])
        coverage[p["receiver"], p["visit_index"]].append((start, end))
        paired[key][p["receiver"]] = (start, end, p["rf_hz"], p["passing"])
        counts[p["receiver"]]["probes"] += 1
        counts[p["receiver"]]["zero_passing"] += p["passing"] == 0
    assert outside == 0
    outcomes = Counter()
    for pair in paired.values():
        if set(pair) != {0, 1}:
            outcomes["missing_receiver"] += 1
        elif pair[0][:3] != pair[1][:3]:
            outcomes["mismatched_pair"] += 1
        else:
            present = sum(pair[r][3] > 0 for r in (0, 1))
            outcomes[f"{present}_receivers_with_passing_candidates"] += 1
    total = sum(v["end"] - v["start"] for v in visits.values())
    assert total > 0
    for rx in (0, 1):
        covered = sum(union_length(coverage[rx, visit]) for visit in visits)
        counts[rx].update(covered_samples=covered, valid_samples=total)
        counts[rx]["coverage_fraction"] = covered / total
        counts[rx]["visits_without_probe"] = sum(not coverage[rx, v] for v in visits)
    return dict(
        dataset=raw["dataset"],
        session_id=raw["session_id"],
        qualified=raw["qualified"],
        timing_qualified=raw["timing_qualified"],
        visits=len(visits),
        probe_ms=raw["probe_ms"],
        valid_dwell_ms_counts=dict(
            Counter(str((v["end"] - v["start"]) * 1000 / raw["rate"]) for v in visits.values())
        ),
        receivers=dict(counts),
        outcomes=dict(outcomes),
        outside_probes=outside,
    )


if __name__ == "__main__":
    rows = [
        summarize(json.loads((HERE / (ds + ".json")).read_text())) for ds in ("DS7", "DS8", "DS9")
    ]
    with (HERE / "summary.json").open("x") as f:
        json.dump(dict(audit_passed=True, records=rows), f, indent=2)
    print(json.dumps(rows, indent=2))
