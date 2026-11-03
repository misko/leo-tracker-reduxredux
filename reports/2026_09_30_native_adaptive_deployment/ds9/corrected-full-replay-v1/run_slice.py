#!/usr/bin/env python3
"""Run a bounded, resumable corrected-geometry DS9 wrapper comparison slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import zstandard

SESSION = "scan-fw-3cfdaa6d75762cad"
BINDING = "4ff246ba978647e28e725a2c55066b8f79aa685b3310df6f4ca7e4006d4bd702"
RECORDING_MANIFEST = "sha256:5b8755586b9a84444ea3caf1bcb5cb0f6c6d80b7c9e3087666331608883de2bd"
RATE = 7_500_000
PROBE_SAMPLES = RATE // 50
GATE = 0.025
FALLBACK_ANCHORS = tuple(range(2, 302, 14))
FLOAT_TOLERANCE = 1e-10
CFO_TOLERANCE_HZ = 1e-6


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def bytes_sha256(value) -> str:
    return hashlib.sha256(memoryview(value).cast("B")).hexdigest()


def recording_event_sha256(event) -> str:
    return canonical_sha256(event.model_dump(mode="json"))


def classify_outcome(passed_by_receiver: dict[int, bool]) -> str:
    rx0 = bool(passed_by_receiver.get(0, False))
    rx1 = bool(passed_by_receiver.get(1, False))
    if rx0 and rx1:
        return "both_active"
    if rx0:
        return "rx0_only"
    if rx1:
        return "rx1_only"
    return "both_quiet"


def build_full_selection(capture_manifest: Path, projection_inputs: Path) -> list[dict]:
    """Build full visit coverage from timing/RF authority and persisted gate labels."""

    capture = json.loads(capture_manifest.read_text())
    events = {item["visit_index"]: item for item in capture["receipt"]["events"]}
    passed = {(visit, receiver): False for visit in events for receiver in (0, 1)}
    for line in projection_inputs.read_text().splitlines():
        item = json.loads(line)
        source = item["source"]
        if source["probe_index"] != 0 or source["visit"] not in events:
            continue
        if item["candidate"]["complete"] and item["candidate"]["margin"] >= GATE:
            passed[source["visit"], source["receiver"]] = True
    result = []
    for visit, event in sorted(events.items()):
        result.append(
            {
                "visit": visit,
                "channel": event["target"]["channel"],
                "edge": event["target"]["edge"],
                "persisted_outcome": classify_outcome(
                    {receiver: passed[visit, receiver] for receiver in (0, 1)}
                ),
            }
        )
    return result


def derive_geometry(
    *,
    pilot_if_hz: float,
    tuned_if_hz: float,
    sample_rate_hz: float,
    bandwidth_hz: float,
    template_min_hz: float,
    template_max_hz: float,
    policy_half_width_hz: float = 800_000.0,
) -> tuple[float, float, float]:
    """Mirror the maintained adaptive visit geometry using source authority."""

    center_hz = float(pilot_if_hz - tuned_if_hz)
    half_usable_hz = min(sample_rate_hz, bandwidth_hz) / 2.0
    observable_hz = min(
        center_hz + template_min_hz + half_usable_hz,
        half_usable_hz - center_hz - template_max_hz,
    )
    if not all(math.isfinite(value) for value in (center_hz, observable_hz)):
        raise ValueError("non-finite compiled geometry")
    if observable_hz <= 0:
        raise ValueError("selected pilot template is not completely observable")
    half_width_hz = min(policy_half_width_hz, observable_hz)
    return center_hz, -half_width_hz, half_width_hz


def load_result(stdout: str) -> dict:
    calls = []
    for line in stdout.splitlines():
        item = json.loads(line)
        result = item.get("result")
        if isinstance(result, dict) and result.get("kind") == "call":
            calls.append(result)
    if len(calls) != 1:
        raise ValueError(f"expected one native call, received {len(calls)}")
    return calls[0]


def native_candidates(call: dict) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {}
    for row in call["rows"]:
        candidates = []
        for rank, candidate in enumerate(row["candidates"]):
            fractional = candidate["fractional_epoch"]
            candidates.append(
                {
                    "rank": rank,
                    "integer_epoch": candidate["epoch"],
                    "acquired_cfo_hz": candidate["acquired_cfo_hz"],
                    "integer_tracking_cfo_hz": candidate["tracking_cfo_hz"],
                    "integer_exact_score": candidate["exact_score"],
                    "integer_control_score": candidate["control_score"],
                    "integer_margin": candidate["margin"],
                    "fractional_status": fractional["status"],
                    "fractional_offset": fractional.get("offset_samples"),
                    "tracking_cfo_hz": fractional.get("tracking_cfo_hz"),
                    "exact_score": fractional.get("exact_score"),
                    "control_score": fractional.get("control_score"),
                    "margin": fractional.get("margin"),
                }
            )
        result[row["receiver_id"]] = candidates
    return result


def server_candidates(analysis) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {}
    for probe in analysis.probes:
        candidates = []
        for candidate in probe.candidates:
            candidates.append(
                {
                    "rank": candidate.candidate_rank,
                    "integer_epoch": candidate.epoch_sample,
                    "acquired_cfo_hz": candidate.acquired_cfo_hz,
                    "integer_tracking_cfo_hz": candidate.tracking_cfo_hz,
                    "integer_exact_score": candidate.exact_score,
                    "integer_control_score": candidate.control_score,
                    "integer_margin": candidate.margin,
                    "fractional_status": candidate.fractional_epoch_status,
                    "fractional_offset": candidate.fractional_epoch_offset_samples,
                    "tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
                    "exact_score": candidate.fractional_exact_score,
                    "control_score": candidate.fractional_control_score,
                    "margin": candidate.fractional_margin,
                    "integer_residual_cfo_hz": candidate.residual_cfo_hz,
                    "fractional_residual_cfo_hz": candidate.fractional_residual_cfo_hz,
                }
            )
        result[probe.receiver_id] = candidates
    return result


def compare_native_server(native: dict[int, list[dict]], server: dict[int, list[dict]]) -> dict:
    numeric = (
        "acquired_cfo_hz",
        "integer_tracking_cfo_hz",
        "integer_exact_score",
        "integer_control_score",
        "integer_margin",
        "fractional_offset",
        "tracking_cfo_hz",
        "exact_score",
        "control_score",
        "margin",
    )
    maximum = {field: 0.0 for field in numeric}
    comparisons = []
    structure_equal = set(native) == set(server)
    numeric_finite = True
    gate_decisions_equal = True
    gate_decisions_compared = 0
    native_passing_candidates = 0
    server_passing_candidates = 0
    for receiver in sorted(set(native) | set(server)):
        left_rows = native.get(receiver, [])
        right_rows = server.get(receiver, [])
        structure_equal &= len(left_rows) == len(right_rows)
        for left, right in zip(left_rows, right_rows, strict=False):
            row = {
                "receiver_id": receiver,
                "rank": right["rank"],
                "rank_equal": left["rank"] == right["rank"],
                "integer_epoch_equal": left["integer_epoch"] == right["integer_epoch"],
                "fractional_status_equal": (
                    left["fractional_status"] == right["fractional_status"]
                ),
                "deltas": {},
            }
            structure_equal &= (
                row["rank_equal"] and row["integer_epoch_equal"] and row["fractional_status_equal"]
            )
            for field in numeric:
                left_value, right_value = left[field], right[field]
                if left_value is None or right_value is None:
                    equal = left_value is None and right_value is None
                    row["deltas"][field] = None if equal else "null-mismatch"
                    structure_equal &= equal
                    continue
                delta = abs(float(left_value) - float(right_value))
                finite = math.isfinite(float(left_value)) and math.isfinite(float(right_value))
                numeric_finite &= finite
                row.setdefault("finite", {})[field] = finite
                if not finite:
                    delta = math.inf
                maximum[field] = max(maximum[field], delta)
                row["deltas"][field] = delta
            if left["fractional_status"] == "complete" and right["fractional_status"] == "complete":
                left_gate = float(left["margin"]) >= GATE
                right_gate = float(right["margin"]) >= GATE
                row["gate_equal"] = left_gate == right_gate
                gate_decisions_equal &= row["gate_equal"]
                gate_decisions_compared += 1
                native_passing_candidates += left_gate
                server_passing_candidates += right_gate
            comparisons.append(row)
    within_tolerance = (
        structure_equal
        and numeric_finite
        and all(
            delta <= (CFO_TOLERANCE_HZ if "cfo_hz" in field else FLOAT_TOLERANCE)
            for field, delta in maximum.items()
        )
    )
    return {
        "structure_equal": structure_equal,
        "numeric_values_finite": numeric_finite,
        "within_frozen_tolerance": within_tolerance,
        "all_gate_decisions_equal": gate_decisions_equal,
        "gate_decisions_compared": gate_decisions_compared,
        "native_passing_candidates": native_passing_candidates,
        "server_passing_candidates": server_passing_candidates,
        "maximum_absolute_delta": maximum,
        "comparisons": comparisons,
    }


def compare_persisted(
    document: dict,
    server: dict[int, list[dict]],
    *,
    valid_start_counter: int,
    session_first_counter: int,
) -> dict:
    float_fields = {
        "acquired_cfo_hz": "acquired_cfo_hz",
        "integer_tracking_cfo_hz": "integer_tracking_cfo_hz",
        "integer_residual_cfo_hz": "integer_residual_cfo_hz",
        "integer_exact_score": "integer_exact_score",
        "integer_control_score": "integer_control_score",
        "integer_margin": "integer_margin",
        "fractional_epoch_offset_samples": "fractional_offset",
        "fractional_tracking_cfo_hz": "tracking_cfo_hz",
        "fractional_residual_cfo_hz": "fractional_residual_cfo_hz",
        "fractional_exact_score": "exact_score",
        "fractional_control_score": "control_score",
        "fractional_margin": "margin",
    }
    exact = True
    rows = []
    gate_count = 0
    gate_decisions_compared = 0
    for probe in document["probes"]:
        receiver = probe["receiver_id"]
        actual = {item["rank"]: item for item in server[receiver]}
        persisted = {item["candidate_rank"]: item for item in probe["candidates"]}
        unavailable = {item["candidate_rank"]: item for item in probe["unavailable_candidates"]}
        exact &= probe["candidate_count"] == len(actual) == 8
        passed = {}
        for rank, candidate in actual.items():
            row = {"receiver_id": receiver, "rank": rank, "deltas": {}}
            if candidate["fractional_status"] == "complete":
                expected = persisted.get(rank)
                row["availability_equal"] = expected is not None
                exact &= row["availability_equal"]
                if expected is None:
                    rows.append(row)
                    continue
                row["integer_epoch_equal"] = (
                    expected["integer_epoch_sample"] == candidate["integer_epoch"]
                )
                exact &= row["integer_epoch_equal"]
                for persisted_name, actual_name in float_fields.items():
                    delta = abs(float(expected[persisted_name]) - float(candidate[actual_name]))
                    row["deltas"][persisted_name] = delta
                    exact &= delta == 0.0
                device_counter = valid_start_counter + candidate["integer_epoch"]
                session_sample = device_counter - session_first_counter
                fractional_time = (session_sample + float(candidate["fractional_offset"])) / RATE
                row["integer_device_counter_equal"] = (
                    int(expected["integer_device_sample_counter"]) == device_counter
                )
                row["integer_session_sample_equal"] = (
                    int(expected["integer_session_sample"]) == session_sample
                )
                row["fractional_time_equal"] = expected["fractional_time_s"] == fractional_time
                passed_gate = float(candidate["margin"]) >= GATE
                row["gate_equal"] = expected["passed_fractional_margin_gate"] == passed_gate
                exact &= all(
                    row[key]
                    for key in (
                        "integer_device_counter_equal",
                        "integer_session_sample_equal",
                        "fractional_time_equal",
                        "gate_equal",
                    )
                )
                passed[rank] = passed_gate
                gate_count += passed_gate
                gate_decisions_compared += 1
            else:
                expected = unavailable.get(rank)
                row["availability_equal"] = (
                    expected is not None
                    and expected["fractional_epoch_status"] == candidate["fractional_status"]
                )
                exact &= row["availability_equal"]
            rows.append(row)
        expected_winner = max(
            passed,
            key=lambda rank: actual[rank]["margin"],
            default=None,
        )
        exact &= expected_winner == probe["winning_candidate_rank"]
    return {
        "all_persisted_fields_exact": exact,
        "gate_decisions_compared": gate_decisions_compared,
        "passing_candidates": gate_count,
        "rows": rows,
    }


@dataclass(frozen=True)
class Task:
    visit: int
    channel: int
    edge: str
    persisted_outcome: str
    output_dir: str
    bulk_root: str
    analysis_root: str
    detector: str
    exact_template: str
    control_template: str
    task_digest: str


def current_source_authority(task: Task) -> dict:
    """Re-read immutable source bytes before accepting a resumable receipt."""

    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    store = AdaptiveHopIqStore(task.bulk_root, read_only=True)
    session = store.inspect(SESSION)
    if session.manifest_sha256 != RECORDING_MANIFEST:
        raise ValueError("recording input-manifest binding changed")
    with store.reader(SESSION, expected=session) as reader:
        visit, values = reader.read_visit_ci16(task.visit)
    event = visit.event
    analysis_file = Path(task.analysis_root) / f"visit-{task.visit:06d}.v9.json.zst"
    return {
        "actual_lo_frequency_hz": event.actual_lo_frequency_hz,
        "channel": event.target.channel,
        "edge": event.target.edge.value,
        "recording_event_sha256": recording_event_sha256(event),
        "raw_sha256": bytes_sha256(values),
        "recording_manifest_sha256": session.manifest_sha256,
        "analysis_visit_compressed_sha256": sha256(analysis_file),
        "source_store": {
            "adapter": "leo.storage.adaptive_hop.AdaptiveHopIqStore",
            "root": task.bulk_root,
            "read_only": True,
        },
    }


def resume_receipt_matches(task: Task, previous: dict, authority: dict) -> bool:
    recorded = previous.get("source_authority", {})
    return (
        previous.get("task_digest") == task.task_digest
        and previous.get("status") == "pass"
        and authority["channel"] == task.channel
        and authority["edge"] == task.edge
        and all(
            recorded.get(key) == authority[key]
            for key in (
                "actual_lo_frequency_hz",
                "recording_event_sha256",
                "raw_sha256",
                "recording_manifest_sha256",
                "analysis_visit_compressed_sha256",
                "source_store",
            )
        )
    )


def run_task(task: Task) -> dict:
    output_path = Path(task.output_dir) / "visits" / f"visit-{task.visit:06d}.json"
    if output_path.exists():
        previous = json.loads(output_path.read_text())
        authority = current_source_authority(task)
        if resume_receipt_matches(task, previous, authority):
            return previous

    from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
    from leo.contracts.starlink_frequency import (
        starlink_edge_rf_center_frequency_hz,
    )
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    from leo.analysis.starlink.templates import edge_frequencies_hz
    from leo.scanner.detector import Glrt64SearchGeometry, analyze_glrt64_dwell

    started = time.monotonic()
    store = AdaptiveHopIqStore(task.bulk_root, read_only=True)
    session = store.inspect(SESSION)
    if session.manifest_sha256 != RECORDING_MANIFEST:
        raise ValueError("recording input-manifest binding changed")
    with store.reader(SESSION, expected=session) as reader:
        visit, values = reader.read_visit_ci16(task.visit)
    event = visit.event
    if (
        event.visit_index != task.visit
        or event.target.channel != task.channel
        or event.target.edge.value != task.edge
    ):
        raise ValueError(f"recording authority changed for visit {task.visit}")
    capture = session.manifest.receipt.plan.geometry
    offsets = edge_frequencies_hz(event.target.edge)
    pilot_if_hz = (
        starlink_edge_rf_center_frequency_hz(event.target.channel, event.target.edge)
        - capture.lnb_lo_hz
    )
    center_hz, residual_min_hz, residual_max_hz = derive_geometry(
        pilot_if_hz=pilot_if_hz,
        tuned_if_hz=event.actual_lo_frequency_hz,
        sample_rate_hz=capture.sample_rate_hz,
        bandwidth_hz=capture.bandwidth_hz,
        template_min_hz=float(offsets.min()),
        template_max_hz=float(offsets.max()),
    )
    calibrations = tuple(
        compile_pilot_search_geometry(
            receiver_id=receiver,
            starlink_channel=event.target.channel,
            edge=event.target.edge,
            tuned_center_frequency_hz=event.actual_lo_frequency_hz,
            sample_rate_hz=capture.sample_rate_hz,
            rf_bandwidth_hz=capture.bandwidth_hz,
            residual_cfo_min_hz=residual_min_hz,
            residual_cfo_max_hz=residual_max_hz,
            lnb_lo_hz=capture.lnb_lo_hz,
        ).frequency_reference
        for receiver in capture.receiver_ids
    )
    if any(item.center_hz != center_hz for item in calibrations):
        raise ValueError("receiver calibration center differs from compiled source geometry")

    metadata = {
        "dataset_id": "DS9",
        "session_id": SESSION,
        "visit_index": task.visit,
        "recording_manifest_sha256": session.manifest_sha256,
    }
    with tempfile.TemporaryDirectory(prefix=f"leo-ds9-corrected-{task.visit:06d}-") as temp:
        temp = Path(temp)
        raw = temp / "visit.ci16"
        raw.write_bytes(memoryview(values).cast("B"))
        raw_hash = bytes_sha256(values)
        metadata["raw_sha256"] = raw_hash
        schedule = temp / "schedule.tsv"
        schedule.write_text(
            "\t".join(
                map(
                    str,
                    (
                        0,
                        capture.sample_rate_hz,
                        120,
                        120,
                        task.exact_template,
                        task.control_template,
                        raw,
                        calibrations[0].center_hz,
                        calibrations[1].center_hz,
                        residual_min_hz,
                        residual_max_hz,
                        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                    ),
                )
            )
            + "\n"
        )
        native_started = time.monotonic()
        replay = subprocess.run(
            [
                task.detector,
                "--manifest",
                str(schedule),
                "--deployed-server-interval-fractional",
                "--thermal-path",
                "/nonexistent",
                "--thermal-scale",
                "1",
                "--thermal-offset",
                "0",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        native_wall = time.monotonic() - native_started
    call = load_result(replay.stdout)

    samples = values[:, :, 0].astype(np.float32) + 1j * values[:, :, 1].astype(np.float32)
    configuration = SimpleNamespace(
        dwell_samples=len(samples),
        probe_samples=PROBE_SAMPLES,
        probe_stride_ms=120,
        probe_stride_samples=RATE * 120 // 1000,
        scheduled_probe_count=1,
        sample_rate_hz=RATE,
        receiver_ids=tuple(capture.receiver_ids),
        probe_ms=20,
        glrt64_margin_gate=GATE,
        maximum_acquisition_candidates=8,
    )
    server_started = time.monotonic()
    analysis = analyze_glrt64_dwell(
        samples,
        configuration,
        edge=event.target.edge,
        search_geometry=Glrt64SearchGeometry(
            receiver_calibrations=calibrations,
            residual_cfo_min_hz=residual_min_hz,
            residual_cfo_max_hz=residual_max_hz,
            fallback_anchor_symbols=FALLBACK_ANCHORS,
        ),
    )
    server_wall = time.monotonic() - server_started
    native = native_candidates(call)
    server = server_candidates(analysis)

    analysis_file = Path(task.analysis_root) / f"visit-{task.visit:06d}.v9.json.zst"
    compressed = analysis_file.read_bytes()
    persisted = json.loads(zstandard.ZstdDecompressor().decompress(compressed))["document"]
    persisted_passed = {
        probe["receiver_id"]: any(
            candidate["passed_fractional_margin_gate"] for candidate in probe["candidates"]
        )
        for probe in persisted["probes"]
    }
    if classify_outcome(persisted_passed) != task.persisted_outcome:
        raise ValueError(f"persisted outcome changed for visit {task.visit}")
    native_server = compare_native_server(native, server)
    persisted_server = compare_persisted(
        persisted,
        server,
        valid_start_counter=event.valid_start_counter,
        session_first_counter=session.manifest.receipt.terminal.first_counter,
    )
    status = (
        "pass"
        if native_server["within_frozen_tolerance"]
        and native_server["all_gate_decisions_equal"]
        and persisted_server["all_persisted_fields_exact"]
        else "fail"
    )
    result = {
        "schema": "org.leo.ds9-corrected-wrapper-slice-visit/v1",
        "status": status,
        "task_digest": task.task_digest,
        "visit": task.visit,
        "channel": task.channel,
        "edge": task.edge,
        "persisted_outcome": task.persisted_outcome,
        "source_authority": {
            "actual_lo_frequency_hz": event.actual_lo_frequency_hz,
            "recording_event_sha256": recording_event_sha256(event),
            "pilot_if_hz": pilot_if_hz,
            "receiver_center_hz": [item.center_hz for item in calibrations],
            "residual_cfo_min_hz": residual_min_hz,
            "residual_cfo_max_hz": residual_max_hz,
            "raw_sha256": raw_hash,
            "recording_manifest_sha256": session.manifest_sha256,
            "analysis_visit_compressed_sha256": sha256(analysis_file),
            "source_store": {
                "adapter": "leo.storage.adaptive_hop.AdaptiveHopIqStore",
                "root": task.bulk_root,
                "read_only": True,
            },
        },
        "native_vs_current_server": native_server,
        "persisted_vs_current_server": persisted_server,
        "native": native,
        "current_server": server,
        "timing_s": {
            "native": native_wall,
            "current_server": server_wall,
            "whole_visit": time.monotonic() - started,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output_path)
    if status != "pass":
        raise ValueError(f"visit {task.visit} comparison failed")
    return result


def write_failure_receipt(output_dir: Path, task: Task, kind: str, detail: str) -> None:
    path = output_dir / "failures" / f"visit-{task.visit:06d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "schema": "org.leo.ds9-corrected-wrapper-replay-failure/v1",
        "status": "fail",
        "kind": kind,
        "detail": detail,
        "visit": task.visit,
        "task_digest": task.task_digest,
    }
    temporary = path.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def write_partial_summary(
    output_dir: Path,
    *,
    kind: str,
    detail: str,
    tasks: list[Task],
    completed: list[dict],
    failed_visits: list[int],
) -> None:
    completed_visits = sorted(item["visit"] for item in completed)
    unfinished = sorted(
        task.visit for task in tasks if task.visit not in set(completed_visits) | set(failed_visits)
    )
    value = {
        "schema": "org.leo.ds9-corrected-wrapper-replay-partial/v1",
        "status": "fail",
        "kind": kind,
        "detail": detail,
        "completed_visits": completed_visits,
        "failed_visits": sorted(failed_visits),
        "unfinished_visits": unfinished,
        "task_count": len(tasks),
        "task_digests": sorted({task.task_digest for task in tasks}),
    }
    path = output_dir / "partial.json"
    temporary = path.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def terminate_executor(executor: ProcessPoolExecutor) -> None:
    """Terminate each worker process group, including its native child."""

    processes = list(getattr(executor, "_processes", {}).values())
    worker_process_groups = []
    for process in processes:
        if process.is_alive():
            try:
                if os.getpgid(process.pid) == process.pid:
                    worker_process_groups.append(process.pid)
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass
    for process in processes:
        process.join(timeout=2.0)
        if process.is_alive() and process.pid not in worker_process_groups:
            with suppress(ProcessLookupError):
                process.kill()
            process.join(timeout=2.0)
    for process_group in worker_process_groups:
        with suppress(ProcessLookupError):
            os.killpg(process_group, signal.SIGKILL)
    executor.shutdown(wait=False, cancel_futures=True)


def initialize_worker_process_group() -> None:
    """Contain native replay children so a hard deadline cleans the whole tree."""

    os.setsid()


def run_tasks_bounded(
    tasks: list[Task],
    *,
    workers: int,
    deadline_seconds: float,
    output_dir: Path,
    runner=run_task,
) -> list[dict]:
    executor = ProcessPoolExecutor(
        max_workers=workers,
        initializer=initialize_worker_process_group,
    )
    futures = {executor.submit(runner, task): task for task in tasks}
    pending = set(futures)
    results: list[dict] = []
    started = time.monotonic()
    try:
        while pending:
            remaining = deadline_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("replay exceeded hard deadline")
            done, pending = wait(
                pending,
                timeout=remaining,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                raise TimeoutError("replay exceeded hard deadline")
            failures: list[tuple[Task, str, Exception]] = []
            for future in done:
                task = futures[future]
                try:
                    results.append(future.result())
                except Exception as error:
                    detail = f"{type(error).__name__}: {error}"
                    write_failure_receipt(output_dir, task, "worker_exception", detail)
                    failures.append((task, detail, error))
            if failures:
                first_task, first_detail, first_error = failures[0]
                write_partial_summary(
                    output_dir,
                    kind="worker_exception",
                    detail=first_detail,
                    tasks=tasks,
                    completed=results,
                    failed_visits=[task.visit for task, _, _ in failures],
                )
                terminate_executor(executor)
                raise RuntimeError(
                    f"visit {first_task.visit} worker failed: {first_detail}"
                ) from first_error
    except TimeoutError as error:
        write_partial_summary(
            output_dir,
            kind="deadline",
            detail=str(error),
            tasks=tasks,
            completed=results,
            failed_visits=[],
        )
        terminate_executor(executor)
        raise
    executor.shutdown(wait=True)
    return results


def main() -> None:
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("slice", "full"), default="slice")
    parser.add_argument("--selection", type=Path, default=here / "selection.json")
    parser.add_argument("--output-dir", type=Path, default=here / "slice-output")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--deadline-seconds", type=float, default=600.0)
    parser.add_argument("--bulk-root", default="/srv/bulk/leo")
    parser.add_argument(
        "--capture-manifest",
        type=Path,
        default=(
            root / "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "location-source-inventory/capture-manifest.json"
        ),
    )
    parser.add_argument(
        "--projection-inputs",
        type=Path,
        default=(
            root / "reports/2026_09_30_native_adaptive_deployment/tracking/projection-inputs.jsonl"
        ),
    )
    parser.add_argument(
        "--analysis-root",
        default=(f"/srv/bulk/leo/scanner-adaptive-analysis/{SESSION}/{BINDING}"),
    )
    parser.add_argument(
        "--detector",
        type=Path,
        default=(
            root / "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "receiver-authority-ablation-v1/wideband-research/artifacts/host/"
            "leo-native-adaptive-replay"
        ),
    )
    parser.add_argument(
        "--exact-template",
        type=Path,
        default=(
            root / "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "location-templates/lower-exact.c128"
        ),
    )
    parser.add_argument(
        "--control-template",
        type=Path,
        default=(
            root / "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "location-templates/lower-control.c128"
        ),
    )
    args = parser.parse_args()
    started = time.monotonic()
    selection = json.loads(args.selection.read_text())
    selected_visits = (
        selection["visits"]
        if args.scope == "slice"
        else build_full_selection(args.capture_manifest, args.projection_inputs)
    )
    reference_root = Path("/var/tmp/leo-arm-realtime-publication")
    reference_status = subprocess.check_output(
        ["git", "-C", str(reference_root), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    )
    if reference_status:
        raise ValueError("maintained reference checkout has tracked modifications")
    reference_sources = (
        "src/leo/analysis/starlink/acquisition.py",
        "src/leo/analysis/starlink/pilot_search_geometry.py",
        "src/leo/analysis/starlink/templates.py",
        "src/leo/contracts/starlink_frequency.py",
        "src/leo/scanner/detector.py",
        "src/leo/scanner/adaptive_hop_analysis.py",
    )
    dependencies = {
        "harness_sha256": sha256(Path(__file__).resolve()),
        "selection_sha256": sha256(args.selection),
        "selected_visits_sha256": canonical_sha256(selected_visits),
        "capture_manifest_sha256": sha256(args.capture_manifest),
        "projection_inputs_sha256": sha256(args.projection_inputs),
        "bulk_store_adapter": "leo.storage.adaptive_hop.AdaptiveHopIqStore",
        "bulk_store_root": args.bulk_root,
        "bulk_store_read_only": True,
        "analysis_store_root": args.analysis_root,
        "detector_sha256": sha256(args.detector),
        "exact_template_sha256": sha256(args.exact_template),
        "control_template_sha256": sha256(args.control_template),
        "reference_git_head": subprocess.check_output(
            ["git", "-C", str(reference_root), "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "reference_tracked_checkout_clean": True,
        "reference_source_sha256": {
            name: sha256(reference_root / name) for name in reference_sources
        },
    }
    task_digest = canonical_sha256(dependencies)
    tasks = [
        Task(
            visit=item["visit"],
            channel=item["channel"],
            edge=item["edge"],
            persisted_outcome=item["persisted_outcome"],
            output_dir=str(args.output_dir),
            bulk_root=args.bulk_root,
            analysis_root=args.analysis_root,
            detector=str(args.detector.resolve()),
            exact_template=str(args.exact_template.resolve()),
            control_template=str(args.control_template.resolve()),
            task_digest=task_digest,
        )
        for item in selected_visits
    ]
    expected_count = 32 if args.scope == "slice" else 2215
    if len(tasks) != expected_count or len({task.visit for task in tasks}) != expected_count:
        raise ValueError(f"{args.scope} must contain {expected_count} distinct visits")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = run_tasks_bounded(
        tasks,
        workers=args.workers,
        deadline_seconds=max(
            0.0,
            args.deadline_seconds - (time.monotonic() - started),
        ),
        output_dir=args.output_dir,
    )
    results.sort(key=lambda item: item["visit"])
    maximum: dict[str, float] = {}
    for result in results:
        for field, delta in result["native_vs_current_server"]["maximum_absolute_delta"].items():
            maximum[field] = max(maximum.get(field, 0.0), delta)
    elapsed = time.monotonic() - started
    native_cpu_proxy = sum(item["timing_s"]["native"] for item in results)
    server_cpu_proxy = sum(item["timing_s"]["current_server"] for item in results)
    summary = {
        "schema": "org.leo.ds9-corrected-wrapper-replay-summary/v1",
        "status": "pass",
        "scope": args.scope,
        "visits": len(results),
        "receiver_windows": len(results) * 2,
        "channels": sorted({item["channel"] for item in results}),
        "edges": sorted({item["edge"] for item in results}),
        "outcomes": {
            outcome: sum(item["persisted_outcome"] == outcome for item in results)
            for outcome in ("both_active", "both_quiet", "rx0_only", "rx1_only")
        },
        "persisted_fields_exact_all_visits": all(
            item["persisted_vs_current_server"]["all_persisted_fields_exact"] for item in results
        ),
        "native_current_server_all_retained_within_tolerance": all(
            item["native_vs_current_server"]["within_frozen_tolerance"] for item in results
        ),
        "native_current_server_gate_decisions_compared": sum(
            item["native_vs_current_server"]["gate_decisions_compared"] for item in results
        ),
        "native_current_server_all_gate_decisions_equal": all(
            item["native_vs_current_server"]["all_gate_decisions_equal"] for item in results
        ),
        "persisted_passing_candidates": sum(
            item["persisted_vs_current_server"]["passing_candidates"] for item in results
        ),
        "persisted_gate_decisions_compared": sum(
            item["persisted_vs_current_server"]["gate_decisions_compared"] for item in results
        ),
        "native_passing_candidates": sum(
            item["native_vs_current_server"]["native_passing_candidates"] for item in results
        ),
        "maximum_absolute_delta": maximum,
        "dependencies": dependencies,
        "task_digest": task_digest,
        "workers": args.workers,
        "timing_s": {
            "wall": elapsed,
            "summed_native_process_wall": native_cpu_proxy,
            "summed_current_server_wall": server_cpu_proxy,
        },
        "full_replay_estimate": {
            "visit_count": 2215,
            "one_worker_wall_seconds": sum(item["timing_s"]["whole_visit"] for item in results)
            * 2215
            / len(results),
            "two_worker_idealized_wall_seconds": sum(
                item["timing_s"]["whole_visit"] for item in results
            )
            * 2215
            / len(results)
            / 2,
            "three_worker_idealized_wall_seconds": sum(
                item["timing_s"]["whole_visit"] for item in results
            )
            * 2215
            / len(results)
            / 3,
            "four_worker_idealized_wall_seconds": elapsed * 2215 / len(results),
            "retained_receipt_bytes": sum(
                (args.output_dir / "visits" / f"visit-{item['visit']:06d}.json").stat().st_size
                for item in results
            )
            * 2215
            // len(results),
            "raw_bytes_retained": 0,
            "estimate_is_not_a_run": True,
        },
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    if not summary["native_current_server_all_gate_decisions_equal"]:
        raise ValueError("rank-level native/current-server gate decisions differ")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
