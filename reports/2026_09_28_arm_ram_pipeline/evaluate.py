"""Evaluate sealed ARM RAM-pipeline JSONL receipts without replaying DSP."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PRIOR_ASSESS = (
    HERE.parent
    / "2026_09_27_ds5_cached_tracking/review/arm_probe/assess.py"
)
_spec = importlib.util.spec_from_file_location("arm_pipeline_prior_assess", PRIOR_ASSESS)
if _spec is None or _spec.loader is None:  # pragma: no cover - installation fault
    raise RuntimeError("cannot load inherited ARM scientific assessor")
prior = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prior)

SCHEMA = "org.leo.research.arm-ram-pipeline/v1"
METHODS = ("D", "goal40mag")
MODES = ("isolated", "concurrent")
RATES = (2_500_000, 5_000_000, 7_500_000, 10_000_000)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def _finite(value: Any, name: str, *, nonnegative: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    result = float(value)
    if nonnegative and result < 0:
        raise ValueError(f"{name}: negative")
    return result


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    point = (len(ordered) - 1) * fraction
    lo, hi = int(point), math.ceil(point)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (point - lo)


def _distribution(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else None,
        "p50": _quantile(values, 0.50),
        "p95": _quantile(values, 0.95),
        "max": max(values) if values else None,
    }


def _cpu_total(value: dict[str, Any]) -> int:
    keys = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
    return sum(int(value[key]) for key in keys)


def _cpu_busy(value: dict[str, Any]) -> int:
    return _cpu_total(value) - int(value["idle"]) - int(value["iowait"])


def _headroom(complete: dict[str, Any]) -> dict[str, Any]:
    """Use producer-overlap counters only; never infer it from the drain tail."""
    start = complete.get("consumer_core_stat_start")
    end = complete.get("producer_end_consumer_core_stat")
    if not isinstance(start, dict) or not isinstance(end, dict):
        return {
            "available": False,
            "reason": "producer-overlap /proc/stat end counter absent",
        }
    total = _cpu_total(end) - _cpu_total(start)
    busy = _cpu_busy(end) - _cpu_busy(start)
    if total <= 0 or busy < 0 or busy > total:
        raise ValueError("invalid producer-overlap CPU counters")
    busy_fraction = busy / total
    return {
        "available": True,
        "measure": "whole-core /proc/stat producer-window estimate; includes non-benchmark activity and 100 Hz accounting",
        "total_ticks": total,
        "busy_ticks": busy,
        "busy_fraction": busy_fraction,
        "headroom_fraction": 1.0 - busy_fraction,
        "at_least_40_percent_estimate": (1.0 - busy_fraction) >= 0.40,
        "qualifies_robust_40_percent_gate": False,
    }


def _canonical_science(job: dict[str, Any]) -> dict[str, Any]:
    """The native result and screens are science; all surrounding timers are not."""
    receivers = job.get("receivers")
    if not isinstance(receivers, list) or len(receivers) != 2:
        raise ValueError("processed job does not contain both receiver results")
    canonical = []
    for receiver in receivers:
        if not isinstance(receiver, dict) or set(("receiver", "result", "screens")) - set(receiver):
            raise ValueError("malformed receiver scientific payload")
        canonical.append(
            {
                "receiver": receiver["receiver"],
                "result": _strip_timers(receiver["result"]),
                "screens": _strip_timers(receiver["screens"]),
            }
        )
    if [row["receiver"] for row in canonical] != [0, 1]:
        raise ValueError("receiver inventory differs")
    return {"receivers": canonical}


def _strip_timers(value: Any) -> Any:
    """Remove timing instrumentation at every nesting level, preserving result order."""
    if isinstance(value, list):
        return [_strip_timers(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _strip_timers(item)
            for key, item in value.items()
            if not (key == "cpu_ms" or key == "wall_ms" or key.endswith("_cpu_ms") or key.endswith("_wall_ms"))
        }
    return value


def _science_rows(job: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = _canonical_science(job)
    return [prior.science(receiver) for receiver in canonical["receivers"]]


def _read_phase(path: Path, declared: dict[str, Any] | None = None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{lineno}: object required")
        records.append(value)
    if len(records) < 2 or records[0].get("type") != "ready" or records[-1].get("type") != "complete":
        raise ValueError(f"{path}: ready and terminal complete records required")
    ready, complete = records[0], records[-1]
    if ready.get("schema") != SCHEMA or complete.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unexpected receipt schema")
    if complete.get("complete") is not True:
        raise ValueError(f"{path}: incomplete phase")
    jobs = [row for row in records[1:-1] if row.get("type") == "job"]
    if len(jobs) != len(records) - 2:
        raise ValueError(f"{path}: unrecognized non-job record")
    count = ready.get("jobs")
    if type(count) is not int or count < 1 or count != complete.get("jobs") or len(jobs) != count:
        raise ValueError(f"{path}: job denominator mismatch")
    if [job.get("index") for job in jobs] != list(range(count)):
        raise ValueError(f"{path}: job indices are not complete and ordered")
    for key in ("method", "mode", "rate_hz", "schedule_kind"):
        if key not in ready:
            raise ValueError(f"{path}: ready lacks {key}")
        if declared and key in declared and declared[key] != ready[key]:
            raise ValueError(f"{path}: declared {key} differs from receipt")
    if declared and "jobs" in declared and declared["jobs"] != count:
        raise ValueError(f"{path}: declared jobs differs from receipt")
    if ready["method"] not in METHODS or ready["mode"] not in MODES or ready["rate_hz"] not in RATES:
        raise ValueError(f"{path}: unsupported phase identity")
    if complete.get("mode") != ready["mode"]:
        raise ValueError(f"{path}: terminal mode mismatch")
    status_counts = defaultdict(int)
    case_ids: list[str] = []
    for index, job in enumerate(jobs):
        status = job.get("status")
        if status not in ("processed", "dropped_queue_full", "detector_failed"):
            raise ValueError(f"{path}: job {index} invalid status")
        status_counts[status] += 1
        case_id = job.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{path}: job {index} missing case_id")
        case_ids.append(case_id)
        _finite(job.get("arrival_ms"), f"{path}: arrival", nonnegative=True)
        _finite(job.get("ready_ms"), f"{path}: ready", nonnegative=True)
        if status == "processed":
            for name in ("start_ms", "end_ms", "consumer_thread_cpu_ms"):
                _finite(job.get(name), f"{path}: {name}", nonnegative=True)
            if job["end_ms"] < job["start_ms"] or job["start_ms"] < job["ready_ms"]:
                raise ValueError(f"{path}: job {index} impossible service timestamps")
            _canonical_science(job)
        else:
            if job.get("receivers") is not None:
                raise ValueError(f"{path}: unprocessed job carries scientific output")
    case_count = ready.get("case_count")
    if type(case_count) is not int or case_count < 1:
        raise ValueError(f"{path}: invalid case_count")
    prefix = min(case_count, count)
    if len(set(case_ids[:prefix])) != prefix or any(
        case_id != case_ids[index % case_count] for index, case_id in enumerate(case_ids)
    ):
        raise ValueError(f"{path}: case order is not the announced cyclic workload")
    fields = {
        "processed": status_counts["processed"],
        "dropped_queue_full": status_counts["dropped_queue_full"],
        "detector_failed": status_counts["detector_failed"],
    }
    receipt_names = {"processed": "processed", "dropped_queue_full": "dropped_queue_full", "detector_failed": "detector_failures"}
    for name, observed in fields.items():
        if complete.get(receipt_names[name]) != observed:
            raise ValueError(f"{path}: terminal {receipt_names[name]} differs from rows")
    if complete.get("pending") != 0 or complete.get("consumed") != fields["processed"] + fields["detector_failed"]:
        raise ValueError(f"{path}: terminal consumer accounting mismatch")
    if complete.get("dropped_queue_full") != complete.get("queue_full_overruns"):
        raise ValueError(f"{path}: queue-full counters differ")
    return {"path": str(path), "ready": ready, "complete": complete, "jobs": jobs, "counts": fields}


def _phase_metrics(phase: dict[str, Any]) -> dict[str, Any]:
    processed = [job for job in phase["jobs"] if job["status"] == "processed"]
    service = [job["end_ms"] - job["start_ms"] for job in processed]
    queue = [job["start_ms"] - job["ready_ms"] for job in processed]
    response = [job["end_ms"] - job["arrival_ms"] for job in processed]
    capture_late = [job["ready_ms"] - job["capture_complete_due_ms"] for job in phase["jobs"]]
    cpu = [job["consumer_thread_cpu_ms"] for job in processed]
    first_last = lambda values: {
        "first_50_mean": sum(values[:50]) / len(values[:50]) if values[:50] else None,
        "last_50_mean": sum(values[-50:]) / len(values[-50:]) if values[-50:] else None,
        "final": values[-1] if values else None,
    }
    complete = phase["complete"]
    producer_window_ms = (
        complete["producer_end_ms"] - complete["arrival_epoch_ms"]
        if phase["ready"]["mode"] == "concurrent"
        else complete["timed_end_ms"] - complete["timed_start_ms"]
    )
    consumer_cpu = _finite(complete.get("consumer_thread_cpu_ms"), "consumer_thread_cpu_ms", nonnegative=True)
    return {
        "denominators": {"planned": len(phase["jobs"]), **phase["counts"], "completed": len(processed)},
        "service_ms": _distribution(service),
        "queue_ms": _distribution(queue),
        "response_ms": _distribution(response),
        "capture_late_ms": _distribution(capture_late),
        "consumer_job_cpu_ms": _distribution(cpu),
        "queue_trend": first_last(queue),
        "producer": {
            "thread_cpu_ms": complete.get("producer_thread_cpu_ms"),
            "late_chunks_over_1ms": complete.get("producer_late_chunks_over_1ms"),
            "max_chunk_late_ms": complete.get("producer_max_chunk_late_ms"),
            "ring_occupied_highwater": complete.get("ring_occupied_highwater"),
            "ready_queue_highwater": complete.get("ready_queue_highwater"),
        },
        "consumer": {"thread_cpu_ms": complete.get("consumer_thread_cpu_ms"), "process_cpu_ms": complete.get("process_cpu_ms")},
        "consumer_thread_cpu_budget": {
            "window_ms": producer_window_ms,
            "thread_cpu_ms": consumer_cpu,
            "thread_cpu_fraction_of_window": consumer_cpu / producer_window_ms if producer_window_ms > 0 else None,
            "unused_fraction_of_window": 1.0 - consumer_cpu / producer_window_ms if producer_window_ms > 0 else None,
            "scope": "benchmark consumer thread only; not whole-core headroom",
        },
        "actual_overlap_headroom": _headroom(complete) if phase["ready"]["mode"] == "concurrent" else {"available": False, "reason": "isolated phase"},
    }


def _isolated_case_references(phase: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[int]]:
    """Collapse repeated isolated cases only after proving their exact repeatability."""
    references: dict[str, dict[str, Any]] = {}
    repeat_mismatches: list[int] = []
    for job in phase["jobs"]:
        if job["status"] != "processed":
            continue
        observation = _canonical_science(job)
        previous = references.setdefault(job["case_id"], observation)
        if previous != observation:
            repeat_mismatches.append(job["index"])
    return references, repeat_mismatches


def _pair_exact(isolated: dict[str, Any], concurrent: dict[str, Any]) -> dict[str, Any]:
    references, reference_repeat_mismatches = _isolated_case_references(isolated)
    missing_reference, mismatches, unavailable = [], [], []
    for job in concurrent["jobs"]:
        reference = references.get(job["case_id"])
        if reference is None:
            missing_reference.append(job["index"])
        elif job["status"] != "processed":
            unavailable.append(job["index"])
        elif reference != _canonical_science(job):
            mismatches.append(job["index"])
    return {
        "isolated_jobs": len(isolated["jobs"]), "concurrent_planned": len(concurrent["jobs"]),
        "isolated_case_references": len(references),
        "isolated_reference_repeat_mismatches": reference_repeat_mismatches,
        "concurrent_processed": len(concurrent["jobs"]) - len(unavailable),
        "unavailable_or_dropped": unavailable, "missing_isolated_reference": missing_reference,
        "exact_mismatches": mismatches,
        "passed": not reference_repeat_mismatches and not unavailable and not missing_reference and not mismatches,
    }


def _pair_d_gate(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if len(reference["jobs"]) != len(candidate["jobs"]):
        raise ValueError("D/candidate job denominators differ")
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    cases: dict[str, dict[str, Any]] = {}
    unavailable: list[int] = []
    for d_job, g_job in zip(reference["jobs"], candidate["jobs"], strict=True):
        if d_job["index"] != g_job["index"] or d_job["case_id"] != g_job["case_id"]:
            raise ValueError("D/candidate job identity differs")
        if d_job["status"] != "processed" or g_job["status"] != "processed":
            unavailable.append(d_job["index"])
            continue
        case_id = f"{d_job['case_id']}@{d_job['index']}"
        cases[case_id] = {"rate_hz": reference["ready"]["rate_hz"]}
        rows[case_id, "D"] = {"science": _science_rows(d_job)}
        rows[case_id, "goal40mag"] = {"science": _science_rows(g_job)}
    identity = prior.identity(rows, cases, set(cases), "D", "goal40mag") if cases else None
    decisions = (
        all(
            d["positive"] == g["positive"]
            for case_id in cases
            for d, g in zip(rows[case_id, "D"]["science"], rows[case_id, "goal40mag"]["science"], strict=True)
        )
        if cases else False
    )
    return {
        "planned": len(reference["jobs"]), "both_processed": len(cases),
        "unavailable_or_dropped": unavailable, "identity": identity,
        "decision_equality": decisions,
        "passed": not unavailable and identity is not None and identity["all_identity_gates_pass"] and decisions,
        "scope": "inherited native rank6/confirm1 gate; not full-server 11x8 recovery",
    }


def evaluate(run_directory: Path) -> dict[str, Any]:
    run_directory = run_directory.resolve()
    receipt = _load_json(run_directory / "run.json")
    if receipt.get("complete") is not True:
        raise ValueError("run receipt is incomplete")
    if not isinstance(receipt.get("source_hashes"), dict) or not receipt["source_hashes"]:
        raise ValueError("run receipt lacks source hashes")
    declared = receipt.get("phases")
    if not isinstance(declared, list) or not declared:
        raise ValueError("run receipt lacks explicit phase inventory")
    phases: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in declared:
        if not isinstance(item, dict):
            raise ValueError("invalid phase inventory")
        filename = item.get("file")
        if not isinstance(filename, str) or Path(filename).is_absolute() or ".." in Path(filename).parts:
            raise ValueError("phase file must be a relative path")
        phase = _read_phase(run_directory / filename, item)
        if item.get("returncode") != 0:
            raise ValueError(f"{filename}: runner return code is not zero")
        if not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
            raise ValueError(f"{filename}: missing phase SHA256")
        if hashlib.sha256((run_directory / filename).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"{filename}: phase SHA256 differs from inventory")
        ready = phase["ready"]
        name = item.get("name")
        matched = re.search(r"-r([0-9]+)$", name) if isinstance(name, str) else None
        if not matched:
            raise ValueError(f"{filename}: phase name must end in -rN")
        repeat = int(matched.group(1))
        key = (ready["method"], ready["mode"], ready["rate_hz"], ready["schedule_kind"], repeat)
        if key in phases:
            raise ValueError(f"duplicate phase {key}")
        phases[key] = phase
    phase_summaries = {"/".join(map(str, key)): _phase_metrics(value) for key, value in phases.items()}
    comparisons: dict[str, Any] = {}
    groups = sorted({(key[2], key[3]) for key in phases})
    for rate, schedule in groups:
        group = {(key[0], key[1], key[4]): phase for key, phase in phases.items() if key[2:4] == (rate, schedule)}
        label = f"rate={rate}/schedule={schedule}"
        exact = {}
        d_gate = {}
        for method in METHODS:
            isolated = group.get((method, "isolated", 0))
            repeats = {}
            if isolated:
                for (found_method, found_mode, repeat), concurrent in group.items():
                    if found_method == method and found_mode == "concurrent":
                        repeats[f"concurrent_repeat_{repeat}"] = _pair_exact(isolated, concurrent)
            if repeats:
                exact[method] = repeats
        for mode in MODES:
            repeats = {}
            for repeat in sorted({key[2] for key in group}):
                if ("D", mode, repeat) in group and ("goal40mag", mode, repeat) in group:
                    repeats[f"repeat_{repeat}"] = _pair_d_gate(group["D", mode, repeat], group["goal40mag", mode, repeat])
            if repeats:
                d_gate[mode] = repeats
        comparisons[label] = {"same_binary_isolated_vs_concurrent_exact": exact, "D_vs_goal40mag_inherited_gate": d_gate}
    return {
        "schema": "org.leo.research.arm-ram-pipeline-summary/v1",
        "run_directory": str(run_directory),
        "run_receipt": receipt,
        "phase_count": len(phases),
        "phases": phase_summaries,
        "comparisons": comparisons,
        "limitations": [
            "The 80%/90% individual-positive full-server recovery targets are not measured by the reduced ARM rank6/confirm1 workload.",
            "The RAM producer models paced CPU writes, not DMA, IIO, interrupts, or live adaptive feedback.",
            "A 40% headroom result is unavailable unless the receipt supplies producer-overlap per-core counters.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summary = evaluate(args.run_directory)
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
