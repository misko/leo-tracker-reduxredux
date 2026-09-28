"""Independently validate and summarize archived host tracking cohorts."""

from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

GATE = 0.025
EPOCH_TOLERANCE = 2
CFO_TOLERANCE_HZ = 8000


def read_jsonl(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def positive(candidates):
    return [candidate for candidate in candidates if candidate["margin"] >= GATE]


def maximum_match(reference, native):
    owner = {}

    def assign(index, seen):
        for candidate, value in enumerate(native):
            if candidate in seen:
                continue
            if (
                abs(reference[index]["epoch_sample"] - value["epoch"]) > EPOCH_TOLERANCE
                or abs(reference[index]["tracking_cfo_hz"] - value["tracking_cfo_hz"])
                > CFO_TOLERANCE_HZ
            ):
                continue
            seen.add(candidate)
            if candidate not in owner or assign(owner[candidate], seen):
                owner[candidate] = index
                return True
        return False

    for index in range(len(reference)):
        assign(index, set())
    return len(owner)


def baseline_index(path: Path):
    index = {}
    for row in read_jsonl(path):
        context = row["context"]
        if row["method"] == "original" and row["repeat"] == 0 and row["status"] == "ok":
            key = (context["session_id"], context["visit_index"])
            assert key not in index
            index[key] = row["result"]["probes"]
    return index


def empty_counts():
    return {
        "dwells": 0,
        "windows": 0,
        "baseline_positive": 0,
        "native_positive": 0,
        "matched_positive": 0,
        "baseline_positive_windows": 0,
        "native_positive_windows": 0,
        "recovered_positive_windows": 0,
        "candidate_eval_attempts": 0,
        "total_cpu_ms": 0.0,
    }


def add_counts(destination, source):
    for key, value in source.items():
        destination[key] += value


def summarize(rows_path: Path, run_path: Path, baseline, expected_contexts):
    run = json.loads(run_path.read_text())
    rows = read_jsonl(rows_path)
    assert run["complete"] and len(rows) == run["planned_dwells"]
    contexts = [(row["context"]["session_id"], row["context"]["visit_index"]) for row in rows]
    assert len(contexts) == len(set(contexts))
    assert set(contexts) == expected_contexts
    total = empty_counts()
    per_rate = defaultdict(empty_counts)
    for result, context_key in zip(rows, contexts, strict=True):
        assert result["returncode"] == 0 and not result["stderr"]
        raw = result["raw_jsonl"]
        assert raw == [json.loads(line) for line in result["stdout"].splitlines()]
        windows = [row for row in raw if row.get("type") == "window"]
        summaries = [row for row in raw if row.get("type") == "summary"]
        assert windows == result["rows"] and len(windows) == 22 and len(summaries) == 1
        assert {(row["receiver_id"], row["probe_index"]) for row in windows} == {
            (receiver, probe) for receiver in range(2) for probe in range(11)
        }
        assert all(row["status"] == "ok" and len(row["candidates"]) == 8 for row in windows)
        expected = {(row["receiver_id"], row["probe_index"]): row for row in baseline[context_key]}
        counts = empty_counts()
        counts["dwells"] = 1
        counts["windows"] = 22
        for row in windows:
            key = (row["receiver_id"], row["probe_index"])
            reference = positive(expected[key]["candidates"])
            native = positive(row["candidates"])
            matched = maximum_match(reference, native)
            counts["baseline_positive"] += len(reference)
            counts["native_positive"] += len(native)
            counts["matched_positive"] += matched
            counts["baseline_positive_windows"] += bool(reference)
            counts["native_positive_windows"] += bool(native)
            counts["recovered_positive_windows"] += bool(matched)
            counts["candidate_eval_attempts"] += row["candidate_eval_attempts"]
            counts["total_cpu_ms"] += row["timings_ms"]["total_cpu"]
        summary = summaries[0]
        assert summary["candidate_eval_attempts"] == counts["candidate_eval_attempts"]
        assert math.isclose(summary["total_cpu_ms"], counts["total_cpu_ms"], abs_tol=1e-6)
        for mode in ("refresh", "tracked", "fallback"):
            assert summary[f"{mode}_windows"] == sum(row["mode"] == mode for row in windows)
        audit = result["audit"]
        assert not audit["errors"]
        for key in counts.keys() - {"dwells", "windows"}:
            audit_key = "actual_glrt_attempts" if key == "candidate_eval_attempts" else key
            if audit_key in audit["counts"]:
                assert math.isclose(audit["counts"][audit_key], counts[key], abs_tol=1e-6)
        add_counts(total, counts)
        add_counts(per_rate[str(result["context"]["rate_hz"])], counts)
    for group in [total, *per_rate.values()]:
        group["missed_positive"] = group["baseline_positive"] - group["matched_positive"]
        group["added_positive"] = group["native_positive"] - group["matched_positive"]
        group["individual_recall"] = (
            group["matched_positive"] / group["baseline_positive"]
            if group["baseline_positive"]
            else None
        )
        group["window_recall"] = (
            group["recovered_positive_windows"] / group["baseline_positive_windows"]
            if group["baseline_positive_windows"]
            else None
        )
        group["cpu_seconds_per_dwell"] = group["total_cpu_ms"] / group["dwells"] / 1000
    return {"run": run, "total": total, "per_rate": dict(sorted(per_rate.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--cohort704", required=True, type=Path)
    parser.add_argument("--cohort64", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contexts = json.loads(args.inputs.read_text())["rows"]
    all_keys = {(row["session_id"], row["visit_index"]) for row in contexts}
    selected = {
        (row["session_id"], row["visit_index"])
        for rate in (2500000, 5000000, 7500000, 10000000)
        for edge in ("lower", "upper")
        for row in [
            item for item in contexts if item["rate_hz"] == rate and item["target"]["edge"] == edge
        ][:8]
    }
    baseline = baseline_index(args.baseline)
    output = {
        "schema": "arm-glrt-tracking-host-summary/v1",
        "cohort704_refresh2": summarize(
            args.cohort704 / "rows.jsonl.gz", args.cohort704 / "run.json", baseline, all_keys
        ),
        "cohort64": {},
    }
    for refresh in (1, 2, 3, 5, 11):
        directory = args.cohort64 / f"refresh{refresh}"
        output["cohort64"][str(refresh)] = summarize(
            directory / "rows.jsonl.gz", directory / "run.json", baseline, selected
        )
    args.output.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
