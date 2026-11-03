#!/usr/bin/env python3
"""Strictly summarize native scanner JSON telemetry and run receipts."""

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

SAMPLE_RATE_HZ = 2_500_000
EVENT_COMMON = {
    "schema",
    "kind",
    "visit",
    "target",
    "profile",
    "frequency_hz",
    "attested_profile_crc32",
    "valid_start",
    "valid_end",
    "feedback_outcome",
    "power_dbfs",
    "detector_status",
    "fractional_server_parity_qualified",
}
EVENT_V2 = EVENT_COMMON | {
    "selection_counter",
    "transition_counter_before",
    "transition_counter_after",
    "recalled",
    "energy_sum",
    "energy_sample_count",
    "windows_emitted",
    "detector_enqueued_monotonic_ns",
    "detector_started_monotonic_ns",
    "detector_finished_monotonic_ns",
    "detector_queue_ns",
    "detector_runtime_ns",
    "detector_row_count",
}
CANDIDATE_V2 = {
    "receiver_id",
    "probe_index",
    "candidate_index",
    "epoch",
    "tracking_cfo_hz",
    "margin",
    "fractional_status",
    "fractional_offset_samples",
    "fractional_tracking_cfo_hz",
    "fractional_margin",
}
SUMMARY_V1 = {
    "schema",
    "visits",
    "intact",
    "incomplete",
    "detector_completed",
    "queue_drops",
    "candidates",
    "fractional_server_parity_qualified",
}
SUMMARY_V2 = SUMMARY_V1 | {
    "windows_emitted",
    "detector_accepted",
    "detector_failures",
    "detector_rows",
    "detector_queue_high_water",
    "feedback_active",
    "feedback_quiet",
    "feedback_unknown",
    "feedback_rejected",
    "policy_acks",
    "missing_samples",
    "stop_reason",
    "stop_status",
    "final_reason",
    "run_status",
    "source_close_status",
    "owner_deactivate_status",
    "radio_restore_status",
    "owner_release_status",
    "detector_destroy_status",
    "block_ms",
}
KINDS = {
    "visit",
    "queue_drop",
    "detector_failure",
    "detector_result",
    "candidate",
    "policy_ack",
}
OUTCOMES = {0: "unknown", 1: "active", 2: "quiet"}
PRE_EXECUTION_EVIDENCE_FIELDS = {
    "kind",
    "requested_watchdog_seconds",
    "maximum_watchdog_seconds",
    "disassembly_path",
    "disassembly_sha256",
    "binary_sha256",
    "detail",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_loads(text, source):
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid strict JSON in {source}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON record is not an object: {source}")
    return value


def load_document(path):
    return strict_loads(path.read_text(), path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integer(value, field, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def finite(value, field):
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return float(value)


def exact_keys(row, expected, source):
    actual = set(row)
    if actual != expected:
        raise ValueError(
            f"{source} keys differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def validate_event(row, source):
    schema = row.get("schema")
    kind = row.get("kind")
    if schema not in {"leo-native-scanner-event/v1", "leo-native-scanner-event/v2"}:
        raise ValueError(f"unsupported event schema in {source}: {schema}")
    if kind not in KINDS:
        raise ValueError(f"unsupported event kind in {source}: {kind}")
    expected = set(EVENT_COMMON if schema.endswith("/v1") else EVENT_V2)
    if kind == "candidate":
        expected |= CANDIDATE_V2
    exact_keys(row, expected, source)
    for field in (
        "visit",
        "target",
        "profile",
        "frequency_hz",
        "attested_profile_crc32",
        "valid_start",
        "valid_end",
        "feedback_outcome",
        "detector_status",
    ):
        integer(
            row[field], f"{source}:{field}", minimum=-(2**31) if field == "detector_status" else 0
        )
    if row["feedback_outcome"] not in OUTCOMES:
        raise ValueError(f"invalid feedback outcome in {source}")
    if type(row["fractional_server_parity_qualified"]) is not bool:
        raise ValueError(f"invalid parity flag in {source}")
    if row["power_dbfs"] is not None:
        finite(row["power_dbfs"], f"{source}:power_dbfs")
    if schema.endswith("/v2"):
        for field in EVENT_V2 - EVENT_COMMON:
            if field == "recalled":
                if type(row[field]) is not bool:
                    raise ValueError(f"{source}:{field} must be boolean")
            else:
                integer(row[field], f"{source}:{field}")


def validate_summary(row, source):
    schema = row.get("schema")
    expected = {
        "leo-native-scanner-summary/v1": SUMMARY_V1,
        "leo-native-scanner-summary/v2": SUMMARY_V2,
    }.get(schema)
    if expected is None:
        raise ValueError(f"unsupported summary schema in {source}: {schema}")
    exact_keys(row, expected, source)
    for field in expected - {
        "schema",
        "stop_reason",
        "final_reason",
        "fractional_server_parity_qualified",
    }:
        integer(
            row[field],
            f"{source}:{field}",
            minimum=-(2**31) if field.endswith("status") else 0,
        )
    if type(row["fractional_server_parity_qualified"]) is not bool:
        raise ValueError(f"invalid summary parity flag in {source}")


def percentile(values, probability):
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def distribution(values, unit):
    return {
        "count": len(values),
        "unit": unit,
        "percentile_method": "nearest rank (ceil(p*n))",
        "mean": sum(values) / len(values) if values else None,
        "minimum": min(values) if values else None,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "maximum": max(values) if values else None,
    }


def counter_ms(value):
    return value * 1000.0 / SAMPLE_RATE_HZ


def process_metrics(stderr):
    metrics = []
    cleanup = None
    pattern = re.compile(
        r"scanner failed: run=(-?\d+) close=(-?\d+) deactivate=(-?\d+) "
        r"radio_restore=(-?\d+) owner=(-?\d+) detector=(-?\d+)"
    )
    for number, line in enumerate(stderr.splitlines(), 1):
        match = pattern.fullmatch(line)
        if match:
            cleanup = dict(
                zip(
                    (
                        "run_status",
                        "source_close_status",
                        "owner_deactivate_status",
                        "radio_restore_status",
                        "owner_release_status",
                        "detector_destroy_status",
                    ),
                    map(int, match.groups()),
                    strict=True,
                )
            )
        elif line.startswith("{"):
            value = strict_loads(line, f"stderr line {number}")
            if value.get("scope") == "whole_process":
                metrics.append(value)
    if len(metrics) > 1:
        raise ValueError("multiple whole-process metric records")
    return (metrics[0] if metrics else None), cleanup


def monitor_metrics(receipt):
    temperatures = []
    raw_bindings = []
    rss_kib = []
    hwm_kib = []
    memory_available_kib = []
    for index, sample in enumerate(receipt.get("monitor", [])):
        if set(sample) != {"host_monotonic_s", "raw"}:
            raise ValueError(f"monitor sample {index} has unsupported fields")
        finite(sample["host_monotonic_s"], f"monitor {index}:host_monotonic_s")
        lines = sample["raw"].splitlines()
        if len(lines) < 4:
            raise ValueError(f"monitor sample {index} is truncated")
        uptime = lines[0].split()
        if len(uptime) != 2:
            raise ValueError(f"monitor sample {index} has invalid /proc/uptime")
        finite(float(uptime[0]), f"monitor {index}:uptime")
        finite(float(uptime[1]), f"monitor {index}:idle")
        try:
            raw = int(lines[1])
            offset = int(lines[2])
            scale = float(lines[3])
        except ValueError as error:
            raise ValueError(f"monitor sample {index} has invalid XADC binding") from error
        temperature = (raw + offset) * scale / 1000.0
        temperatures.append(temperature)
        raw_bindings.append({"raw": raw, "offset": offset, "scale": scale})
        for line in lines[4:]:
            if line.startswith("MemAvailable:"):
                memory_available_kib.append(int(line.split()[1]))
            elif line.startswith("VmRSS:"):
                rss_kib.append(int(line.split()[1]))
            elif line.startswith("VmHWM:"):
                hwm_kib.append(int(line.split()[1]))
    explicit = {}
    for key, value in receipt.items():
        normalized = key.lower()
        if any(token in normalized for token in ("xadc", "temperature", "vccint", "vccaux")):
            explicit[key] = value
    return {
        "available": bool(temperatures or explicit),
        "xadc_temperature_celsius": distribution(temperatures, "degrees Celsius"),
        "xadc_bindings": raw_bindings,
        "scanner_rss_kib": distribution(rss_kib, "KiB from /proc/PID/status"),
        "scanner_hwm_kib": distribution(hwm_kib, "KiB from /proc/PID/status"),
        "memory_available_kib": distribution(memory_available_kib, "KiB from /proc/meminfo"),
        "radio_before": receipt.get("radio_before"),
        "radio_after": receipt.get("radio_after"),
        "radio_settings_restored": receipt.get("radio_settings_restored"),
        "explicit_receipt_fields": explicit,
    }


def load_records(path):
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank JSONL line: {path}:{number}")
        row = strict_loads(line, f"{path}:{number}")
        if row.get("schema", "").startswith("leo-native-scanner-event/"):
            validate_event(row, f"{path}:{number}")
        else:
            validate_summary(row, f"{path}:{number}")
        rows.append(row)
    return rows


def pre_execution_summary(directory, receipt_path, receipt, required, jsonl_path, stderr_path):
    evidence = receipt["pre_execution_rejection"]
    if not isinstance(evidence, dict) or set(evidence) != PRE_EXECUTION_EVIDENCE_FIELDS:
        raise ValueError("pre-execution evidence fields differ")
    if evidence["kind"] != "watchdog_limit_rejected_before_fork":
        raise ValueError("unknown pre-execution evidence kind")
    requested = integer(
        evidence["requested_watchdog_seconds"],
        "pre_execution_rejection:requested_watchdog_seconds",
        minimum=1,
    )
    maximum = integer(
        evidence["maximum_watchdog_seconds"],
        "pre_execution_rejection:maximum_watchdog_seconds",
        minimum=1,
    )
    if requested <= maximum:
        raise ValueError("pre-execution watchdog request does not exceed maximum")
    if not isinstance(evidence["detail"], str) or not evidence["detail"]:
        raise ValueError("pre-execution evidence detail is empty")
    for field in ("disassembly_sha256", "binary_sha256"):
        if not isinstance(evidence[field], str) or not SHA256_PATTERN.fullmatch(evidence[field]):
            raise ValueError(f"invalid pre-execution {field}")
    proof_relative = Path(evidence["disassembly_path"])
    if proof_relative.is_absolute() or ".." in proof_relative.parts:
        raise ValueError("pre-execution proof path must remain inside report directory")
    proof_path = directory / proof_relative
    if not proof_path.is_file() or sha256(proof_path) != evidence["disassembly_sha256"]:
        raise ValueError("pre-execution proof file/hash differs")
    if (
        receipt["exit_code"] == 0
        or receipt["event_count"] != 0
        or receipt["summaries"] != []
        or receipt["stderr"] != ""
        or jsonl_path.read_bytes() != b""
        or stderr_path.read_bytes() != b""
    ):
        raise ValueError("pre-execution rejection contains scanner output")
    unavailable = {"available": False, "reason": "scanner_not_executed"}
    artifacts = {
        "jsonl": {"path": jsonl_path.name, "sha256": sha256(jsonl_path)},
        "stderr": {"path": stderr_path.name, "sha256": sha256(stderr_path)},
        "receipt": {"path": receipt_path.name, "sha256": sha256(receipt_path)},
        "pre_execution_proof": {
            "path": str(proof_relative),
            "sha256": evidence["disassembly_sha256"],
        },
    }
    return {
        "name": receipt["name"],
        "release_id": receipt["release_id"],
        "execution_scope": "pre_execution_rejection",
        "exit_code": receipt["exit_code"],
        "elapsed_wall_s": finite(receipt["elapsed_wall_s"], "elapsed_wall_s"),
        "successful_exit": False,
        "schemas": [],
        "artifacts": artifacts,
        "pre_execution_evidence": evidence,
        "visits": unavailable,
        "event_kind_counts": None,
        "dwell_ms": unavailable,
        "dwell_counts_by_ms": None,
        "feedback_state_counts": None,
        "target_visit_counts": None,
        "start_cadence_ms": unavailable,
        "completed_visit_valid_window_duty": unavailable,
        "transition_gap_ms": unavailable,
        "target_revisit_ms": unavailable,
        "target_revisit_over_3000ms": None,
        "detector": unavailable,
        "gaps_and_stop": unavailable,
        "cleanup": unavailable,
        "process": unavailable,
        "environment": monitor_metrics(receipt),
        "raw_iq_transferred": receipt["raw_iq_transferred"],
        "receipt_extra_fields": sorted(set(receipt) - required),
    }


def summarize_run(directory, receipt_path):
    receipt = load_document(receipt_path)
    required = {
        "name",
        "exit_code",
        "elapsed_wall_s",
        "event_count",
        "summaries",
        "stderr",
        "raw_iq_transferred",
        "release_id",
    }
    if not required <= set(receipt):
        raise ValueError(f"receipt missing fields: {sorted(required - set(receipt))}")
    integer(receipt["exit_code"], "receipt:exit_code", minimum=-(2**31))
    integer(receipt["event_count"], "receipt:event_count")
    if type(receipt["raw_iq_transferred"]) is not bool:
        raise ValueError("receipt:raw_iq_transferred must be boolean")
    if receipt.get("malformed_json_lines"):
        raise ValueError("receipt records malformed JSONL lines")
    name = receipt["name"]
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError(f"invalid receipt name: {name!r}")
    jsonl_path = directory / f"{name}.jsonl"
    stderr_path = directory / f"{name}.stderr"
    if not jsonl_path.is_file() or not stderr_path.is_file():
        raise ValueError(f"run artifacts missing for {name}")
    if "pre_execution_rejection" in receipt:
        return pre_execution_summary(
            directory, receipt_path, receipt, required, jsonl_path, stderr_path
        )
    records = load_records(jsonl_path)
    events = [row for row in records if "kind" in row]
    summaries = [row for row in records if "kind" not in row]
    if len(summaries) != 1 or receipt["summaries"] != summaries:
        raise ValueError(f"summary authority differs for {name}")
    if receipt["event_count"] != len(records):
        raise ValueError(f"event count differs for {name}")
    if receipt["stderr"] != stderr_path.read_text():
        raise ValueError(f"stderr authority differs for {name}")
    summary = summaries[0]
    visits = [row for row in events if row["kind"] == "visit"]
    visit_ids = [row["visit"] for row in visits]
    if len(set(visit_ids)) != len(visit_ids):
        raise ValueError(f"duplicate visit events for {name}")
    missing_visit_ids = sorted(set(range(summary["visits"])) - set(visit_ids))
    extra_visit_ids = sorted(set(visit_ids) - set(range(summary["visits"])))
    if extra_visit_ids or len(missing_visit_ids) != summary["visits"] - len(visits):
        raise ValueError(f"visit accounting differs for {name}")
    ordered = sorted(visits, key=lambda row: row["visit"])
    if any(row["valid_end"] < row["valid_start"] for row in ordered):
        raise ValueError(f"negative dwell span for {name}")
    dwell_ms = [counter_ms(row["valid_end"] - row["valid_start"]) for row in ordered]
    start_ms = [
        counter_ms(b["valid_start"] - a["valid_start"])
        for a, b in zip(ordered, ordered[1:], strict=False)
    ]
    transition_ms = [
        counter_ms(b["valid_start"] - a["valid_end"])
        for a, b in zip(ordered, ordered[1:], strict=False)
    ]
    by_target = defaultdict(list)
    for row in ordered:
        by_target[row["target"]].append(row)
    revisits = [
        counter_ms(b["valid_start"] - a["valid_start"])
        for rows in by_target.values()
        for a, b in zip(rows, rows[1:], strict=False)
    ]
    outcomes = Counter(OUTCOMES[row["feedback_outcome"]] for row in visits)
    kinds = Counter(row["kind"] for row in events)
    detector_results = [row for row in events if row["kind"] == "detector_result"]
    v2_results = [row for row in detector_results if row["schema"].endswith("/v2")]
    if (
        summary["visits"] != len(visits)
        or summary["visits"] != summary["intact"] + summary["incomplete"]
        or summary["detector_completed"] != kinds["detector_result"]
        or summary["queue_drops"] != kinds["queue_drop"]
        or summary["candidates"] != kinds["candidate"]
    ):
        raise ValueError(f"summary/event counters differ for {name}")
    if summary["schema"].endswith("/v2") and (
        summary["detector_failures"] != kinds["detector_failure"]
        or summary["policy_acks"] != kinds["policy_ack"]
        or summary["feedback_active"] != outcomes["active"]
        or summary["feedback_quiet"] != outcomes["quiet"]
        or summary["feedback_unknown"] != outcomes["unknown"]
    ):
        raise ValueError(f"v2 summary/event counters differ for {name}")
    queue_ms = [row["detector_queue_ns"] / 1e6 for row in v2_results]
    runtime_ms = [row["detector_runtime_ns"] / 1e6 for row in v2_results]
    completed_visit_ids = {row["visit"] for row in detector_results}
    completed_visits = [row for row in ordered if row["visit"] in completed_visit_ids]
    if completed_visits:
        completed_span_ms = counter_ms(
            completed_visits[-1]["valid_end"] - completed_visits[0]["valid_start"]
        )
        completed_valid_ms = sum(
            counter_ms(row["valid_end"] - row["valid_start"]) for row in completed_visits
        )
    else:
        completed_span_ms = completed_valid_ms = 0.0
    process, stderr_cleanup = process_metrics(receipt["stderr"])
    cleanup = {
        field: summary.get(field)
        for field in (
            "run_status",
            "source_close_status",
            "owner_deactivate_status",
            "radio_restore_status",
            "owner_release_status",
            "detector_destroy_status",
        )
        if field in summary
    }
    if stderr_cleanup is not None and cleanup and stderr_cleanup != cleanup:
        raise ValueError(f"cleanup receipt differs for {name}")
    if not cleanup:
        cleanup = stderr_cleanup
    return {
        "name": name,
        "release_id": receipt["release_id"],
        "execution_scope": "scanner_execution",
        "exit_code": receipt["exit_code"],
        "elapsed_wall_s": finite(receipt["elapsed_wall_s"], "elapsed_wall_s"),
        "successful_exit": receipt["exit_code"] == 0,
        "schemas": sorted({row["schema"] for row in records}),
        "artifacts": {
            "jsonl": {"path": jsonl_path.name, "sha256": sha256(jsonl_path)},
            "stderr": {"path": stderr_path.name, "sha256": sha256(stderr_path)},
            "receipt": {"path": receipt_path.name, "sha256": sha256(receipt_path)},
        },
        "visits": {
            "started": summary["visits"],
            "event_records": len(visits),
            "intact": summary["intact"],
            "failed_or_incomplete": summary["incomplete"],
            "missing_event_visit_ids": missing_visit_ids,
            "extra_event_visit_ids": extra_visit_ids,
        },
        "event_kind_counts": dict(sorted(kinds.items())),
        "dwell_ms": distribution(dwell_ms, "ms from 2.5 MS/s device counters"),
        "dwell_counts_by_ms": {
            str(int(value) if value.is_integer() else value): count
            for value, count in sorted(Counter(dwell_ms).items())
        },
        "feedback_state_counts": {key: outcomes.get(key, 0) for key in OUTCOMES.values()},
        "target_visit_counts": {
            str(target): len(rows) for target, rows in sorted(by_target.items())
        },
        "start_cadence_ms": distribution(start_ms, "ms from 2.5 MS/s device counters"),
        "completed_visit_valid_window_duty": {
            "completed_visits": len(completed_visits),
            "span_ms": completed_span_ms,
            "valid_window_ms": completed_valid_ms,
            "fraction": completed_valid_ms / completed_span_ms if completed_span_ms else None,
            "source": "2.5 MS/s valid_start/valid_end counters for detector-completed visits",
        },
        "transition_gap_ms": distribution(
            transition_ms, "ms from prior valid_end to next valid_start"
        ),
        "target_revisit_ms": distribution(
            revisits, "ms between valid_start counters for the same target"
        ),
        "target_revisit_over_3000ms": sum(value > 3000.0 for value in revisits),
        "detector": {
            "completed": summary["detector_completed"],
            "queue_drops": summary["queue_drops"],
            "failures": summary.get("detector_failures"),
            "candidates": summary["candidates"],
            "queue_ms": distribution(queue_ms, "ms"),
            "runtime_ms": distribution(runtime_ms, "ms"),
            "timing_available": bool(v2_results),
            "fractional_server_parity_qualified": summary["fractional_server_parity_qualified"],
        },
        "gaps_and_stop": {
            "missing_samples": summary.get("missing_samples"),
            "stop_reason": summary.get("stop_reason"),
            "stop_status": summary.get("stop_status"),
            "final_reason": summary.get("final_reason"),
        },
        "cleanup": cleanup,
        "process": process,
        "environment": monitor_metrics(receipt),
        "raw_iq_transferred": receipt["raw_iq_transferred"],
        "receipt_extra_fields": sorted(set(receipt) - required),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    output = args.output or directory / "summary.json"
    budget_path = directory / "budget.json"
    budget = load_document(budget_path) if budget_path.is_file() else None
    receipt_paths = {
        path.stem.removesuffix("-receipt"): path for path in directory.glob("*-receipt.json")
    }
    order = []
    if budget is not None:
        for row in budget.get("runs", []):
            if row.get("name") in receipt_paths and row["name"] not in order:
                order.append(row["name"])
    order.extend(sorted(set(receipt_paths) - set(order)))
    runs = [summarize_run(directory, receipt_paths[name]) for name in order]
    document = {
        "schema": "org.leo.native-adaptive-live-telemetry-summary/v1",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "run_count": len(runs),
        "zero_exit_runs": sum(run["successful_exit"] for run in runs),
        "nonzero_exit_runs": sum(not run["successful_exit"] for run in runs),
        "runs": runs,
        "budget": budget,
        "budget_sha256": sha256(budget_path) if budget is not None else None,
        "scientific_scope": {
            "candidate_counts_are_operational_telemetry": True,
            "candidate_recovery_or_ground_truth_available": False,
            "statement": (
                "Live candidate counts have no recovery denominator or ground truth and do not "
                "qualify detector science or server parity."
            ),
        },
    }
    output.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"output": str(output), "runs": len(runs)}))


if __name__ == "__main__":
    main()
