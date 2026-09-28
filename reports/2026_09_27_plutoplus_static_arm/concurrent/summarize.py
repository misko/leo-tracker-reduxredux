#!/usr/bin/env python3
"""Receipt-only summaries for bounded GLRT/adaptive-scan concurrency phases."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_REFERENCE = HERE.parent / "target_run_01"


def load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        errors.append(f"missing: {path.name}")
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid {path.name}: {error}")
    return None


def load_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        errors.append(f"missing: {path.name}")
        return []
    result = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"invalid {path.name}:{number}: {error.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"invalid {path.name}:{number}: object required")
            continue
        result.append(value)
    return result


def percentile(values: list[float]) -> dict[str, float | int | None]:
    values = sorted(values)
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    def rank(fraction: float) -> float:
        return values[math.ceil(fraction * len(values)) - 1]
    return {"count": len(values), "mean": statistics.fmean(values), "p50": rank(.50), "p95": rank(.95),
            "p99": rank(.99), "max": values[-1]}


def number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def timing_stripped(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: timing_stripped(item) for key, item in value.items()
                if "cpu_ms" not in key and "wall_ms" not in key and key != "index"}
    if isinstance(value, list):
        return [timing_stripped(item) for item in value]
    return value


def receiver_science(receiver: dict[str, Any]) -> dict[str, Any]:
    return timing_stripped({"result": receiver.get("result"), "screens": receiver.get("screens")})


def reference_science(reference_dir: Path, case_id: str, errors: list[str]) -> list[dict[str, Any]] | None:
    receipt = load_json(reference_dir / f"{case_id}-D.json", errors)
    if not isinstance(receipt, dict):
        return None
    repetitions = receipt.get("repetitions")
    if not isinstance(repetitions, list) or not repetitions or not isinstance(repetitions[0], dict):
        errors.append(f"reference {case_id}: missing repetitions")
        return None
    receivers = repetitions[0].get("receivers")
    if not isinstance(receivers, list):
        errors.append(f"reference {case_id}: missing receivers")
        return None
    return [receiver_science(row) for row in receivers if isinstance(row, dict)]


def summarize_parity(visits: list[dict[str, Any]], ready: dict[str, Any] | None,
                     reference_dir: Path, errors: list[str]) -> dict[str, Any]:
    receivers = ready.get("receivers") if isinstance(ready, dict) else None
    mode = "both_rx" if receivers == 2 else "single_rx" if receivers == 1 else "unknown"
    checked = matched = 0
    mismatches: list[dict[str, Any]] = []
    reference_cache: dict[str, list[dict[str, Any]] | None] = {}
    for visit in visits:
        case_id = visit.get("case_id")
        current = visit.get("receivers")
        if not isinstance(case_id, str) or not isinstance(current, list):
            errors.append("visit missing case_id or receivers")
            continue
        if case_id not in reference_cache:
            reference_cache[case_id] = reference_science(reference_dir, case_id, errors)
        expected = reference_cache[case_id]
        if expected is None:
            continue
        wanted = receivers if receivers in (1, 2) else len(current)
        if len(current) != wanted:
            mismatches.append({"case_id": case_id, "reason": "receiver_count",
                               "expected": wanted, "actual": len(current)})
            continue
        for rx in range(wanted):
            checked += 1
            if rx >= len(expected) or not isinstance(current[rx], dict) or receiver_science(current[rx]) != expected[rx]:
                mismatches.append({"case_id": case_id, "receiver": rx, "reason": "science"})
            else:
                matched += 1
    return {"mode": mode, "comparisons": checked, "matched": matched,
            "passed": checked > 0 and checked == matched and not mismatches,
            "mismatches": mismatches[:20]}


def map_clock(clock: dict[str, Any] | None, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(clock, dict):
        return None
    before, after = number(clock.get("host_before_ns")), number(clock.get("host_after_ns"))
    uptime = str(clock.get("target_uptime", "")).split()
    try:
        uptime_ms = float(uptime[0]) * 1000.0
    except (IndexError, ValueError):
        errors.append("invalid clock target_uptime")
        return None
    if before is None or after is None or after < before:
        errors.append("invalid clock host bracket")
        return None
    midpoint = (before + after) / 2.0
    return {"target_uptime_ms": uptime_ms, "host_midpoint_ns": midpoint,
            "uncertainty_ms": (after - before) / 2_000_000.0 + 10.0}


def target_to_host_ns(target_ms: float, mapping: dict[str, Any]) -> float:
    return mapping["host_midpoint_ns"] + (target_ms - mapping["target_uptime_ms"]) * 1_000_000.0


def host_to_target_ms(host_ns: float, mapping: dict[str, Any]) -> float:
    return mapping["target_uptime_ms"] + (host_ns - mapping["host_midpoint_ns"]) / 1_000_000.0


def cpu_summary(samples: list[dict[str, Any]], interval: tuple[float, float] | None) -> dict[str, Any]:
    if interval is None:
        return {"samples": 0, "cores": {}, "interval": None}
    start, end = interval
    by_core: dict[str, dict[str, float]] = {}
    selected = 0
    previous_at = None
    for sample in samples:
        at = number(sample.get("monotonic_ms"))
        # A monitor delta belongs to (previous sample, current sample].  Exclude
        # either boundary partial rather than assigning unknown pre/post work.
        if at is None:
            continue
        if previous_at is None or previous_at < start or at > end:
            previous_at = at
            continue
        selected += 1
        for core in sample.get("cores", []):
            if not isinstance(core, dict) or not isinstance(core.get("delta"), dict):
                continue
            key = str(core.get("cpu"))
            totals = by_core.setdefault(key, {})
            for name, value in core["delta"].items():
                amount = number(value)
                if amount is not None:
                    totals[name] = totals.get(name, 0.0) + amount
        previous_at = at
    return {"samples": selected, "interval": {"start_ms": start, "end_ms": end}, "cores": by_core}


def capture_summary(phase: Path, mapping: dict[str, Any] | None, errors: list[str]) -> tuple[dict[str, Any], tuple[float, float] | None]:
    directory = phase / "capture"
    if not directory.exists():
        return {"present": False, "terminal": "not_requested", "visits": 0}, None
    visits = load_jsonl(directory / "visits.jsonl", errors)
    receipt = load_json(directory / "receipt.json", errors)
    archive = load_json(directory / "archive.json", errors)
    exit_code = (phase / "capture.exit").read_text().strip() if (phase / "capture.exit").exists() else None
    indices = [item.get("record", {}).get("visit") for item in visits if isinstance(item.get("record"), dict)]
    numeric_indices = [value for value in indices if isinstance(value, int)]
    gaps = sum(b != a + 1 for a, b in zip(numeric_indices, numeric_indices[1:]))
    missing = sum(int(item.get("record", {}).get("missing_samples_before", 0))
                  for item in visits if isinstance(item.get("record"), dict))
    result_counts: dict[str, int] = {}
    for item in visits:
        record = item.get("record", {})
        if isinstance(record, dict):
            key = str(record.get("result", "missing"))
            result_counts[key] = result_counts.get(key, 0) + 1
    # The archive spans capture setup and restoration.  It is evidence about the
    # archive, but never defines the steady delivered-visit overlap window.
    host_times = [number(item.get("host_monotonic_ns")) for item in visits]
    host_times = [item for item in host_times if item is not None]
    archive_host_interval = None
    if isinstance(archive, dict):
        archive_start, archive_end = number(archive.get("start_host_ns")), number(archive.get("end_host_ns"))
        if archive_start is not None and archive_end is not None:
            archive_host_interval = {"start_ns": archive_start, "end_ns": archive_end}
    interval = None
    if mapping is not None and host_times:
        interval = (host_to_target_ms(min(host_times), mapping), host_to_target_ms(max(host_times), mapping))
    restoration: list[dict[str, Any]] = []
    def find_restoration(value: Any, path: str = "receipt") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                next_path = f"{path}.{key}"
                if "restor" in key.lower():
                    restoration.append({"field": next_path, "value": item})
                find_restoration(item, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                find_restoration(item, f"{path}[{index}]")
    if receipt is not None:
        find_restoration(receipt)
    terminal_receipt = receipt.get("terminal") if isinstance(receipt, dict) else None
    terminal_fields = {key: terminal_receipt.get(key) for key in
                       ("planned", "delivered", "skipped", "invalid", "cancelled", "state", "reason", "error")
                       if isinstance(terminal_receipt, dict) and key in terminal_receipt}
    restoration_record = receipt.get("restoration") if isinstance(receipt, dict) else None
    restoration_exact = None
    if isinstance(restoration_record, dict):
        restoration_exact = (restoration_record.get("expected") == restoration_record.get("observed") and
                             restoration_record.get("expected_kernel_buffers") ==
                             restoration_record.get("observed_kernel_buffers") and
                             restoration_record.get("fastlock_inactive") is True)
    terminal = "completed" if exit_code == "0" and isinstance(terminal_receipt, dict) else "incomplete_or_unavailable"
    return ({"present": True, "terminal": terminal, "terminal_receipt": terminal_fields,
             "restoration_exact": restoration_exact, "capture_exit": exit_code,
             "receipt_present": isinstance(receipt, dict), "archive_present": isinstance(archive, dict),
             "archive_host_interval_ns": archive_host_interval,
             "visits": len(visits), "visit_index_gaps": gaps, "missing_samples_before": missing,
             "result_counts": result_counts, "restoration": restoration, "target_interval_ms":
             None if interval is None else {"start_ms": interval[0], "end_ms": interval[1]}}, interval)


def summarize_phase(phase: Path, reference_dir: Path = DEFAULT_REFERENCE) -> dict[str, Any]:
    errors: list[str] = []
    run = load_json(phase / "run.json", errors)
    clock = map_clock(load_json(phase / "clock.json", errors), errors)
    glrt_rows = load_jsonl(phase / "glrt.jsonl", errors) if (phase / "glrt.jsonl").exists() else []
    cpu_rows = load_jsonl(phase / "cpu.jsonl", errors)
    ready = next((row for row in glrt_rows if row.get("type") == "ready"), None)
    complete = next((row for row in reversed(glrt_rows) if row.get("type") == "complete"), None)
    visits = [row for row in glrt_rows if row.get("type") == "visit"]
    published = {row.get("index"): row for row in glrt_rows if row.get("type") == "published"}
    period = number(ready.get("period_ms")) if isinstance(ready, dict) else None
    def metrics_for(selected_visits: list[dict[str, Any]], selected_published: dict[Any, dict[str, Any]]) -> dict[str, Any]:
        return {"cpu_ms": percentile([x for row in selected_visits if (x := number(row.get("cpu_ms"))) is not None]),
                "wall_ms": percentile([x for row in selected_visits if (x := number(row.get("wall_ms"))) is not None]),
                "queue_ms": percentile([x for row in selected_visits if (x := number(row.get("queue_ms"))) is not None]),
                "response_ms": percentile([x for row in selected_visits if (x := number(row.get("response_ms"))) is not None]),
                "published_response_ms": percentile([x for row in selected_published.values() if (x := number(row.get("response_ms"))) is not None]),
                "published_service_cpu_ms": percentile([x for row in selected_published.values() if (x := number(row.get("service_cpu_ms"))) is not None])}
    metrics = metrics_for(visits, published)
    completed_published = {row.get("index"): published[row.get("index")] for row in visits
                           if row.get("index") in published and isinstance(published[row.get("index")], dict)}
    deadline_values = [number(row.get("response_ms")) for row in completed_published.values()]
    deadline_values = [value for value in deadline_values if value is not None]
    misses = None if period is None else sum(value > period for value in deadline_values)
    interval = None
    if isinstance(ready, dict) and isinstance(complete, dict):
        start, end = number(ready.get("epoch_ms")), number(complete.get("end_ms"))
        if start is not None and end is not None and end >= start:
            interval = (start, end)
    capture, capture_interval = capture_summary(phase, clock, errors)
    monitor_times = [number(row.get("monotonic_ms")) for row in cpu_rows]
    monitor_times = [value for value in monitor_times if value is not None]
    full_interval = (min(monitor_times), max(monitor_times)) if len(monitor_times) >= 2 else None
    overlap = None
    if interval is not None and capture_interval is not None:
        start, end = max(interval[0], capture_interval[0]), min(interval[1], capture_interval[1])
        if end >= start:
            overlap = (start, end)
    overlap_visits: list[dict[str, Any]] = []
    overlap_published: dict[Any, dict[str, Any]] = {}
    if capture_interval is not None:
        capture_start, capture_end = capture_interval
        for visit in visits:
            publication = published.get(visit.get("index"))
            visit_start = number(visit.get("start_ms"))
            published_end = number(publication.get("end_ms")) if isinstance(publication, dict) else None
            if visit_start is not None and published_end is not None and visit_start >= capture_start and published_end <= capture_end:
                overlap_visits.append(visit)
                overlap_published[visit.get("index")] = publication
    overlap_deadlines = [number(row.get("response_ms")) for row in overlap_published.values()]
    overlap_deadlines = [value for value in overlap_deadlines if value is not None]
    overlap_misses = None if period is None else sum(value > period for value in overlap_deadlines)
    parity = summarize_parity(visits, ready, reference_dir, errors) if visits else \
        {"mode": "unknown", "comparisons": 0, "matched": 0, "passed": False, "mismatches": []}
    overlap_parity = summarize_parity(overlap_visits, ready, reference_dir, errors) if overlap_visits else \
        {"mode": "both_rx" if isinstance(ready, dict) and ready.get("receivers") == 2 else "single_rx" if isinstance(ready, dict) and ready.get("receivers") == 1 else "unknown", "comparisons": 0, "matched": 0, "passed": False, "mismatches": []}
    expected_jobs = ready.get("jobs") if isinstance(ready, dict) else None
    validity = {"ready": isinstance(ready, dict), "complete": isinstance(complete, dict),
                "expected_jobs": expected_jobs, "visit_count": len(visits), "published_count": len(published),
                "complete_receipt": bool(isinstance(expected_jobs, int) and len(visits) == expected_jobs and
                                         len(published) == expected_jobs), "parity_passed": parity["passed"]}
    validity["passed"] = bool(validity["ready"] and validity["complete"] and validity["complete_receipt"] and
                               validity["parity_passed"])
    glrt = {"present": bool(glrt_rows), "ready": ready, "complete": complete,
            "visits": len(visits), "published": len(published), "period_ms": period,
            "metrics": metrics, "completed_published": len(completed_published),
            "completed_published_response_misses_over_period": misses, "parity": parity,
            "capture_overlap": {"fully_completed_published_visits": len(overlap_visits),
                                "metrics": metrics_for(overlap_visits, overlap_published),
                                "completed_published_response_misses_over_period": overlap_misses,
                                "parity": overlap_parity}, "validity": validity}
    remote_exit = (phase / "remote.exit").read_text().strip() if (phase / "remote.exit").exists() else None
    capture_valid = (not capture["present"] or
                     (capture["terminal"] == "completed" and capture["restoration_exact"] is True))
    phase_validity = {"remote_exit": remote_exit, "remote_exit_passed": remote_exit in (None, "0"),
                      "glrt_required": bool(glrt_rows),
                      "glrt_receipts_passed": (not glrt_rows or validity["passed"]),
                      "capture_required": capture["present"], "capture_receipts_passed": capture_valid,
                      "receipt_errors": len(errors)}
    # Deadline misses are deliberately excluded: a complete, scientifically
    # valid phase can still fail its performance budget.
    phase_validity["passed"] = bool(phase_validity["remote_exit_passed"] and
                                    phase_validity["glrt_receipts_passed"] and capture_valid and not errors)
    return {"schema": "org.leo.research.concurrent-phase-summary/v1", "phase": phase.name,
            "errors": errors, "clock_mapping": clock, "glrt": glrt, "capture": capture,
            "cpu": {"full_interval": cpu_summary(cpu_rows, full_interval),
                    "capture_interval": cpu_summary(cpu_rows, capture_interval),
                    "glrt_interval": cpu_summary(cpu_rows, interval),
                    "capture_overlap": cpu_summary(cpu_rows, overlap)},
            "validity": phase_validity, "run": run}


def table(summary: dict[str, Any]) -> str:
    glrt = summary["glrt"]
    metric = glrt["metrics"]["response_ms"]
    parity = glrt["parity"]["passed"] if glrt["present"] else "NA"
    return (f"{summary['phase']}\t{glrt['visits']}\t{glrt['completed_published_response_misses_over_period']}\t"
            f"{metric['p50']}\t{metric['p95']}\t{parity}\t{summary['validity']['passed']}\t"
            f"{summary['capture']['terminal']}\t{len(summary['errors'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phases", nargs="+", type=Path)
    parser.add_argument("--reference-run", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output-name", default="summary.json")
    args = parser.parse_args()
    print("phase\tglrt_visits\tmisses\tresponse_p50_ms\tresponse_p95_ms\tparity\tvalid\tcapture\terrors")
    for phase in args.phases:
        summary = summarize_phase(phase, args.reference_run)
        (phase / args.output_name).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(table(summary))


if __name__ == "__main__":
    main()
