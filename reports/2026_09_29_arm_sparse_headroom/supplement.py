"""Summarize supplemental diagnostic and fresh-PGO evidence without running hardware."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if fraction == 0.5:
        return statistics.median(ordered)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def stats(values) -> dict:
    finite = [float(value) for value in values if value is not None and math.isfinite(value)]
    return {
        "count": len(finite),
        "mean": statistics.fmean(finite) if finite else None,
        "p50": percentile(finite, 0.50),
        "p95": percentile(finite, 0.95),
        "p99": percentile(finite, 0.99),
        "max": max(finite) if finite else None,
    }


def load_runs(folder: Path) -> tuple[list[dict], list[dict], list[dict], dict[str, str]]:
    calls, setups, summaries, files = [], [], [], {}
    for path in sorted(folder.glob("*.jsonl")):
        files[path.name] = digest(path)
        documents = [json.loads(line) for line in path.read_text().splitlines()]
        setups.append(documents[0])
        summaries.append(documents[-1])
        calls.extend(document["result"] for document in documents[1:-1])
    return calls, setups, summaries, files


def candidate_identity(call: dict) -> list:
    return [row["candidates"] for row in call["rows"]]


def panel_map(training_panel) -> tuple[dict, set[tuple[str, int]]]:
    execution = json.loads((HERE / "execution-panel.json").read_text())
    mapped = {}
    for group in execution["groups"]:
        if group["rate_hz"] != 2_500_000:
            continue
        for call in group["calls"]:
            context = call["case"]["context"]
            mapped[(group["id"], call["sequence"])] = (
                context["session_id"],
                context["visit_index"],
            )
    training = json.loads(training_panel.read_text())
    trained = {
        (item["context"]["session_id"], item["context"]["visit_index"])
        for item in training["training"]
    }
    return mapped, trained


def indexed_runs(folder: Path) -> dict[tuple[str, int], dict]:
    indexed = {}
    for path in sorted(folder.glob("*.jsonl")):
        group = path.stem
        documents = [json.loads(line) for line in path.read_text().splitlines()]
        for document in documents[1:-1]:
            call = document["result"]
            indexed[(group, call["sequence"])] = call
    return indexed


def compare_pgo(candidate: Path, control: Path, training_panel: Path) -> dict:
    if not candidate.is_dir():
        return {"available": False, "candidate_directory": str(candidate)}
    mapping, trained = panel_map(training_panel)
    new, old = indexed_runs(candidate), indexed_runs(control)
    new = {key: value for key, value in new.items() if key in mapping}
    old = {key: value for key, value in old.items() if key in mapping}
    if set(new) != set(mapping):
        return {
            "available": False,
            "reason": "candidate primary panel is incomplete",
            "observed_calls": len(new),
            "expected_calls": len(mapping),
            "candidate_files": {p.name: digest(p) for p in sorted(candidate.glob("*.jsonl"))},
        }
    assert set(old) == set(mapping), "control primary panel coverage differs"
    all_contexts = set(mapping.values())
    trained_label = f"trained{len(trained)}"
    held_out_label = f"held_out{len(all_contexts - trained)}"
    groups = {trained_label: [], held_out_label: []}
    walls = {trained_label: [], held_out_label: []}
    mismatches = 0
    for key in sorted(new):
        cohort = trained_label if mapping[key] in trained else held_out_label
        groups[cohort].append(new[key]["call_cpu_ms"])
        walls[cohort].append(new[key]["call_wall_ms"])
        mismatches += candidate_identity(new[key]) != candidate_identity(old[key])
    assert {mapping[key] for key in mapping if mapping[key] in trained} == trained
    return {
        "available": True,
        "candidate_files": {p.name: digest(p) for p in sorted(candidate.glob("*.jsonl"))},
        "control_files": {p.name: digest(p) for p in sorted(control.glob("*.jsonl"))},
        "candidate_identity_mismatched_calls": mismatches,
        "timing_scope": "outer maintained-client call CPU milliseconds",
        "training_panel_sha256": digest(training_panel),
        "cpu_ms": {k: stats(v) for k, v in groups.items()},
        "wall_ms": {k: stats(v) for k, v in walls.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", type=Path, default=HERE / "local/sparse-cached-diagnostic")
    parser.add_argument("--pgo", type=Path, default=HERE / "local/sparse-cached-pgo")
    parser.add_argument("--control", type=Path, default=HERE / "local/sparse-cached")
    parser.add_argument("--output", type=Path, default=HERE / "supplement.json")
    parser.add_argument("--training-panel", type=Path, default=HERE / "pgo-training-panel.json")
    args = parser.parse_args()
    calls, setups, summaries, files = load_runs(args.diagnostic)
    wrappers = [call["diagnostic_inclusive_with_wrapper_overhead"] for call in calls]
    fields = (
        "allocation_cpu_ms",
        "allocation_wall_ms",
        "fft_plan_cpu_ms",
        "fft_plan_wall_ms",
        "fftf_plan_cpu_ms",
        "fftf_plan_wall_ms",
        "fft_execute_cpu_ms",
        "fft_execute_wall_ms",
        "fftf_execute_cpu_ms",
        "fftf_execute_wall_ms",
        "malloc_calls",
        "calloc_calls",
        "realloc_calls",
        "free_calls",
        "allocation_requested_bytes",
        "fft_plan_calls",
        "fftf_plan_calls",
        "fft_execute_calls",
        "fftf_execute_calls",
    )
    result = {
        "schema": "org.leo.native-glrt-supplement/v1",
        "scope": {
            "diagnostic": (
                "link-visible wrapper measurements are inclusive, nested, and not headline runtime"
            ),
            "client": (
                "setup, serialization, and per-call E2E are maintained-client process measurements"
            ),
            "telemetry": "thermal reads and peak RSS snapshots occur outside the analyzed call",
        },
        "inputs": {
            "diagnostic_files": files,
            "execution_panel_sha256": digest(HERE / "execution-panel.json"),
            "pgo_training_panel_sha256": digest(HERE / "pgo-training-panel.json"),
        },
        "diagnostic": {
            "calls": len(calls),
            "wrapper": {field: stats(item[field] for item in wrappers) for field in fields},
            "call_cpu_ms": stats(call["call_cpu_ms"] for call in calls),
            "call_wall_ms": stats(call["call_wall_ms"] for call in calls),
            "detector_cpu_ms": stats(call["detector_cpu_ms"] for call in calls),
            "setup_cpu_ms": stats(item["setup_cpu_ms"] for item in setups),
            "setup_wall_ms": stats(item["setup_wall_ms"] for item in setups),
            "serialization_cpu_ms": stats(
                json.loads(line)["serialization_cpu_ms"]
                for path in args.diagnostic.glob("*.jsonl")
                for line in path.read_text().splitlines()[1:-1]
            ),
            "temperature_before_millidegrees": stats(
                call["thermal_millidegrees_before"]
                for call in calls
                if call["thermal_available_before"]
            ),
            "temperature_after_millidegrees": stats(
                call["thermal_millidegrees_after"]
                for call in calls
                if call["thermal_available_after"]
            ),
            "peak_rss_kib": stats(call["peak_rss_kib_after"] for call in calls),
            "client_e2e_cpu_ms": stats(
                value for summary in summaries for value in summary["e2e_cpu_ms"]
            ),
            "client_e2e_wall_ms": stats(
                value for summary in summaries for value in summary["e2e_wall_ms"]
            ),
            "write_cpu_ms_sum_per_process": stats(
                summary["write_cpu_ms_sum"] for summary in summaries
            ),
            "write_wall_ms_sum_per_process": stats(
                summary["write_wall_ms_sum"] for summary in summaries
            ),
        },
        "pgo": compare_pgo(args.pgo, args.control, args.training_panel),
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
