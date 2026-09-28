"""Reconcile every ARM window with native totals before publishing timings."""

import argparse
import json
import math
from pathlib import Path


def summarize(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["complete"]
    results = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    assert len(results) == len(manifest["selected"]) * len(manifest["refreshes"])
    totals = {}
    for result in results:
        windows = [r for r in result["records"] if r["type"] == "window"]
        summaries = [r for r in result["records"] if r["type"] == "summary"]
        assert len(windows) == 22 and len(summaries) == 1
        assert {(r["receiver_id"], r["probe_index"]) for r in windows} == {
            (rx, probe) for rx in range(2) for probe in range(11)
        }
        assert all(r["status"] == "ok" and len(r["candidates"]) == 8 for r in windows)
        assert not result["audit"]["errors"]
        summary = summaries[0]
        counts = result["audit"]["counts"]
        total = totals.setdefault(str(result["refresh"]), {"dwells": 0, "windows": 0})
        total["dwells"] += 1
        total["windows"] += len(windows)
        for key, value in counts.items():
            total[key] = total.get(key, 0) + value
        assert summary["status"] == "ok"
        assert summary["candidate_eval_attempts"] == counts["actual_glrt_attempts"]
        assert math.isclose(summary["total_cpu_ms"], counts["total_cpu_ms"], abs_tol=1e-6)
        for mode in ("refresh", "tracked", "fallback"):
            assert summary[mode + "_windows"] == sum(r["mode"] == mode for r in windows)
        assert math.isfinite(counts["total_cpu_ms"]) and counts["total_cpu_ms"] > 0
        total.setdefault("native_summaries", []).append(summary)
    baseline = totals["1"]["total_cpu_ms"]
    for total in totals.values():
        total["speedup_vs_refresh1"] = baseline / total["total_cpu_ms"]
        total["cpu_seconds_per_dwell"] = total["total_cpu_ms"] / 1000 / total["dwells"]
        total["individual_hit_recall"] = total["matched_positive"] / total["baseline_positive"]
    return totals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.directory), indent=2))
