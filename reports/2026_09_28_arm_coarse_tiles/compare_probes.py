"""Compare identical saved-input ARM probes to the qualified FFTW backend."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(baseline, candidate):
    receipts = [json.loads((p / "run.json").read_text()) for p in (baseline, candidate)]
    assert all(r["complete"] for r in receipts)
    assert receipts[0]["oracle_sha256"] == receipts[1]["oracle_sha256"]
    loaded = []
    for directory in (baseline, candidate):
        rows = [json.loads(x) for x in (directory / "results.jsonl").read_text().splitlines()]
        indexed = {r["label"]: r for r in rows}
        assert len(indexed) == len(rows)
        loaded.append(indexed)
    assert loaded[0].keys() == loaded[1].keys()
    rows = []
    rates = defaultdict(list)
    for label, result in loaded[1].items():
        reference = loaded[0][label]
        native = result["native"]
        item = {
            "label": label,
            "candidate_json_identical": json.dumps(native["candidates"], sort_keys=True)
            == json.dumps(reference["native"]["candidates"], sort_keys=True),
            "coarse_grid_bitexact": digest(candidate / (label + ".f64"))
            == digest(baseline / (label + ".f64")),
            "baseline_cpu_ms": reference["native"]["mean_cpu_ms"],
            "candidate_cpu_ms": native["mean_cpu_ms"],
            "candidate_count": native["candidate_count"],
        }
        rows.append(item)
        rates[label.split("-")[0]].append(item)
    return {
        "schema": "coarse-arm-probe-comparison/v1",
        "baseline_results_sha256": digest(baseline / "results.jsonl"),
        "candidate_results_sha256": digest(candidate / "results.jsonl"),
        "windows": len(rows),
        "candidates": sum(r["candidate_count"] for r in rows),
        "all_candidates_identical": all(r["candidate_json_identical"] for r in rows),
        "all_grids_bitexact": all(r["coarse_grid_bitexact"] for r in rows),
        "by_rate": {
            rate: {
                "windows": len(group),
                "baseline_cpu_ms": sum(r["baseline_cpu_ms"] for r in group) / len(group),
                "candidate_cpu_ms": sum(r["candidate_cpu_ms"] for r in group) / len(group),
                "speedup": sum(r["baseline_cpu_ms"] for r in group)
                / sum(r["candidate_cpu_ms"] for r in group),
            }
            for rate, group in rates.items()
        },
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.baseline, args.candidate)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    assert result["all_candidates_identical"] and result["all_grids_bitexact"]
