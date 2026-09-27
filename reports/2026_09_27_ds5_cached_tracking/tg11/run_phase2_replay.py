"""Bounded causal TG11 replay against the complete application comparator.

This runner is deliberately separate from the frozen constructed-control and
cost stages.  ``--freeze`` is available only after those receipts authorize
phase two; the default invocation verifies that lock and then evaluates the
fixed 64-visit development prefix exactly once.
"""

from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "src"), str(HERE)]

import numpy as np
import leo

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("TG11 must use the current repository application package")

from leo.scanner.detector import analyze_glrt64_dwell
from leo.scanner.models import ScannerConfiguration, current_low_band_targets

from decision import CacheKey, DecisionResult, TG11Detector
from native_engine import NativeTG11
import tg11_dataset as dataset


STAGE0_LOCK = HERE / "source_lock_stage0.json"
STAGE0_RESULT = HERE / "control_results.json"
PHASE1_LOCK = HERE / "source_lock_phase1.json"
PHASE1_RESULT = HERE / "phase1_cost_results.json"
PHASE2_LOCK = HERE / "source_lock_phase2.json"
OUTPUT = HERE / "phase2_replay_results.json"
EXPECTED_CASES = 64
EXPECTED_STAGE0_ROWS = 42
EXPECTED_REPEATS = 3
METHODS = ("application", "tg11")


def digest(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def json_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verify_file_map(files: dict[str, str], *, label: str) -> None:
    if not isinstance(files, dict) or not files:
        raise ValueError(f"{label} has no frozen files")
    for name, expected in files.items():
        if not isinstance(name, str) or not isinstance(expected, str):
            raise ValueError(f"{label} contains an invalid file entry")
        if digest(name) != expected.removeprefix("sha256:"):
            raise ValueError(f"{label} source changed: {name}")


def validate_stage0(receipt: dict[str, Any]) -> None:
    if (
        receipt.get("status") != "complete"
        or receipt.get("source_lock_stable") is not True
        or receipt.get("scientific_gate_passed") is not True
        or receipt.get("real_replay_authorized_by_gate") is not True
        or receipt.get("completed_physical_rows") != EXPECTED_STAGE0_ROWS
        or receipt.get("expected_physical_rows") != EXPECTED_STAGE0_ROWS
        or receipt.get("holdout_opened") is not False
        or len(receipt.get("rows", ())) != EXPECTED_STAGE0_ROWS
        or not all(row.get("passed") is True for row in receipt.get("rows", ()))
    ):
        raise ValueError("stage-zero constructed-control gate is incomplete or failed")
    lock = _load_json(STAGE0_LOCK)
    if receipt.get("source_lock") != lock:
        raise ValueError("stage-zero receipt does not embed the frozen stage-zero lock")
    verify_file_map(lock.get("files", {}), label="stage-zero lock")
    if dataset.membership_digest() != lock.get("membership_digest"):
        raise ValueError("stage-zero membership changed")


def _measurement_schedule(row: dict[str, Any]) -> set[tuple[str, int]]:
    measurements = row.get("measurements")
    if not isinstance(measurements, list):
        return set()
    schedule: set[tuple[str, int]] = set()
    for item in measurements:
        if not isinstance(item, dict):
            return set()
        method, repeat = item.get("method"), item.get("repeat")
        cpu, wall = item.get("process_cpu_ms"), item.get("wall_ms")
        output_sha = item.get("output_sha256")
        if (
            method not in METHODS
            or type(repeat) is not int
            or not isinstance(cpu, (int, float))
            or not isinstance(wall, (int, float))
            or not math.isfinite(float(cpu))
            or not math.isfinite(float(wall))
            or cpu < 0
            or wall < 0
            or not isinstance(output_sha, str)
        ):
            return set()
        schedule.add((method, repeat))
    return schedule


def validate_phase1(
    receipt: dict[str, Any], expected_case_ids: tuple[str, ...]
) -> None:
    expected_schedule = {
        (method, repeat)
        for method in METHODS
        for repeat in range(EXPECTED_REPEATS)
    }
    rows = receipt.get("rows", ())
    if (
        receipt.get("status") != "complete"
        or receipt.get("source_lock_stable") is not True
        or receipt.get("complete_gate_passed") is not True
        or receipt.get("scientific_gate_passed") is not True
        or receipt.get("cost_gate_passed") is not True
        or receipt.get("phase2_authorized") is not True
        or receipt.get("holdout_opened") is not False
        or tuple(receipt.get("selected_case_ids", ())) != expected_case_ids
        or not isinstance(rows, list)
        or len(rows) != len(expected_case_ids)
        or tuple(row.get("case_id") for row in rows) != expected_case_ids
    ):
        raise ValueError("phase-one cost/science gate is incomplete or failed")
    if receipt.get("stage0_control_result_sha256", "").removeprefix("sha256:") != digest(
        STAGE0_RESULT
    ):
        raise ValueError("phase-one receipt references another stage-zero result")
    lock = _load_json(PHASE1_LOCK)
    if receipt.get("source_lock") != lock:
        raise ValueError("phase-one receipt does not embed the frozen phase-one lock")
    verify_file_map(lock.get("files", {}), label="phase-one lock")
    for row in rows:
        if (
            not isinstance(row.get("scientific"), dict)
            or row["scientific"].get("passed") is not True
            or row.get("input_immutable") is not True
            or row.get("repeat_outputs_deterministic") is not True
            or row.get("candidate_state_commits") != 1
            or _measurement_schedule(row) != expected_schedule
        ):
            raise ValueError("phase-one row is incomplete, non-deterministic, or failed")
        measurements = row["measurements"]
        for method in METHODS:
            hashes = {
                item["output_sha256"]
                for item in measurements
                if item["method"] == method
            }
            if len(hashes) != 1:
                raise ValueError("phase-one repeated scientific outputs differ")
    summaries = receipt.get("per_rate_summary")
    if not isinstance(summaries, dict) or {
        int(rate) for rate in summaries
    } != set(dataset.RATES):
        raise ValueError("phase-one per-rate summary is incomplete")
    for summary in summaries.values():
        if not isinstance(summary, dict) or summary.get("cost_gate_passed") is not True:
            raise ValueError("phase-one per-rate cost gate failed")


def source_files() -> dict[str, str]:
    paths = set(HERE.glob("*.py")) | set(HERE.glob("*.c")) | set(HERE.glob("*.h"))
    paths |= {
        HERE / "design.json",
        HERE / "RUN_PROTOCOL.md",
        HERE / "libtg11.so",
        HERE / "libtg11.so.build.json",
        HERE.parent / "application_coarse_alternatives/TRACK_GUIDED_DESIGN.md",
        STAGE0_LOCK,
        STAGE0_RESULT,
        PHASE1_LOCK,
        PHASE1_RESULT,
    }
    paths |= set(dataset.SOURCE_HASHES)
    paths |= {
        ROOT / "src/leo/analysis/starlink/templates.py",
        ROOT / "src/leo/scanner/detector.py",
        ROOT / "src/leo/analysis/starlink/acquisition.py",
        ROOT / "src/leo/analysis/starlink/pilot_methods.py",
        ROOT / "src/leo/scanner/models.py",
    }
    build = _load_json(HERE / "libtg11.so.build.json")
    for name, expected in build["sources_sha256"].items():
        if digest(name) != expected.removeprefix("sha256:"):
            raise ValueError(f"native build source changed: {name}")
        paths.add(Path(name))
    if digest(HERE / "libtg11.so") != build["binary_sha256"].removeprefix("sha256:"):
        raise ValueError("native binary changed")
    return {str(path.resolve()): digest(path) for path in sorted(paths)}


def verify_phase2_lock(lock: dict[str, Any]) -> None:
    verify_file_map(lock.get("files", {}), label="phase-two lock")
    if dataset.membership_digest() != lock.get("membership_digest"):
        raise ValueError("phase-two membership changed")
    expected = {
        "stage0_lock_sha256": digest(STAGE0_LOCK),
        "stage0_result_sha256": digest(STAGE0_RESULT),
        "phase1_lock_sha256": digest(PHASE1_LOCK),
        "phase1_result_sha256": digest(PHASE1_RESULT),
    }
    if any(lock.get(name) != value for name, value in expected.items()):
        raise ValueError("phase-two prerequisite receipt changed")


def make_key(case: dataset.Case, receiver: int) -> CacheKey:
    return CacheKey(
        case.session,
        receiver,
        case.channel,
        case.edge,
        case.rate,
        case.tuning_identity,
        case.calibration_identity,
    )


def configuration(case: dataset.Case) -> ScannerConfiguration:
    target = next(
        item
        for item in current_low_band_targets()
        if item.channel == case.channel and item.edge.value == case.edge
    )
    return ScannerConfiguration(
        sample_rate_hz=case.rate,
        bandwidth_hz=case.rate,
        dwell_ms=120,
        receiver_ids=(0, 1),
        maximum_acquisition_candidates=10,
        targets=(target,),
    )


def complex_frame(raw: np.ndarray) -> np.ndarray:
    values = np.empty(raw.shape[:2], dtype=np.complex64)
    values.real = raw[:, :, 0]
    values.imag = raw[:, :, 1]
    values.setflags(write=False)
    return values


def serialize_comparator(analysis: Any) -> dict[str, Any]:
    return {
        "first": (
            None
            if analysis.first is None
            else analysis.first.model_dump(mode="json")
        ),
        "decision_best_margin": analysis.decision_best_margin,
        "full_best_margin": analysis.full_best_margin,
        "reason": analysis.reason,
        "probes": [asdict(probe) for probe in analysis.probes],
    }


def timed(function):
    cpu = time.process_time_ns()
    wall = time.perf_counter_ns()
    result = function()
    return result, {
        "process_cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def run_comparator(raw: np.ndarray, case: dataset.Case):
    # CI16-to-complex conversion is intentionally inside the complete call.
    values = complex_frame(raw)
    return analyze_glrt64_dwell(values, configuration(case), edge=case.edge)


def run_candidate(
    raw: np.ndarray,
    case: dataset.Case,
    detector: TG11Detector,
) -> tuple[DecisionResult, DecisionResult]:
    if case.visit_index is None:
        raise ValueError("real TG11 replay requires a physical visit index")
    return tuple(
        detector.process(
            raw,
            make_key(case, receiver),
            start_counter=case.source_counter,
            visit_index=case.visit_index,
        )
        for receiver in (0, 1)
    )  # type: ignore[return-value]


def classify_receiver(
    result: DecisionResult,
    inventory: tuple[dataset.ReferencePair, ...],
    case: dataset.Case,
    receiver: int,
) -> dict[str, Any]:
    references = tuple(pair for pair in inventory if pair.receiver == receiver)
    association = dataset.associate_candidate_to_reference(result, references, case)
    if result.active:
        if references and association.matched:
            outcome = "active_associated"
            passed = True
        elif references:
            outcome = "active_unassociated"
            passed = False
        else:
            outcome = "extra"
            passed = False
    elif references:
        # Activity retention is a visit-level objective: the other receiver may
        # supply the associated pair. Preserve this receiver-level fact without
        # turning it into an independent loss.
        outcome = "reference_positive_candidate_inactive"
        passed = True
    else:
        outcome = "both_inactive"
        passed = True
    return {
        "receiver": receiver,
        "reference_pair_count": len(references),
        "reference_active": bool(references),
        "candidate_active": result.active,
        "outcome": outcome,
        "association": asdict(association),
        "passed": passed,
    }


def execute_case(
    case: dataset.Case,
    detector: TG11Detector,
    *,
    candidate_first: bool,
) -> dict[str, Any]:
    raw = dataset.load_iq(case)
    before_memory = hashlib.sha256(raw).hexdigest()
    calls = {
        "baseline": lambda: run_comparator(raw, case),
        "tg11": lambda: run_candidate(raw, case, detector),
    }
    order = ("tg11", "baseline") if candidate_first else ("baseline", "tg11")
    results: dict[str, Any] = {}
    measurements: dict[str, dict[str, float]] = {}
    for method in order:
        results[method], measurements[method] = timed(calls[method])
    analysis = results["baseline"]
    decisions = results["tg11"]
    comparator = serialize_comparator(analysis)
    candidate = [asdict(result) for result in decisions]
    inventory = dataset.reference_positive_pair_inventory(analysis, case)
    if bool(inventory) != (analysis.first is not None):
        raise ValueError("full comparator inventory disagrees with its first decision")
    receiver_rows = [
        classify_receiver(decisions[receiver], inventory, case, receiver)
        for receiver in (0, 1)
    ]
    reference_active = bool(inventory)
    candidate_active = any(result.active for result in decisions)
    visit_activity_retained = (
        candidate_active if reference_active else not candidate_active
    )
    all_active_pairs_associated = all(row["passed"] for row in receiver_rows)
    if reference_active and not candidate_active:
        visit_outcome = "loss"
    elif not reference_active and candidate_active:
        visit_outcome = "extra"
    elif candidate_active and not all_active_pairs_associated:
        visit_outcome = "active_unassociated"
    elif candidate_active:
        visit_outcome = "retained_associated"
    else:
        visit_outcome = "both_inactive"
    after_memory = hashlib.sha256(raw).hexdigest()
    file_hash = digest(case.raw_path)
    expected_hash = case.raw_sha256.removeprefix("sha256:")
    immutable = before_memory == after_memory == file_hash == expected_hash
    if not immutable:
        raise ValueError(f"TG11 replay input changed: {case.id}")
    return {
        "case_id": case.id,
        "rate_hz": case.rate,
        "edge": case.edge,
        "channel": case.channel,
        "session_id": case.session,
        "visit_index": case.visit_index,
        "source_start_counter": case.source_counter,
        "raw_sha256": case.raw_sha256,
        "verified_raw_file_sha256": "sha256:" + file_hash,
        "memory_sha256_before": "sha256:" + before_memory,
        "memory_sha256_after": "sha256:" + after_memory,
        "execution_order": list(order),
        "measurements": measurements,
        "comparator": comparator,
        "comparator_output_sha256": json_digest(comparator),
        "reference_pair_count": len(inventory),
        "reference_active": reference_active,
        "candidate": candidate,
        "candidate_output_sha256": json_digest(candidate),
        "candidate_active": candidate_active,
        "receiver_comparisons": receiver_rows,
        "visit_outcome": visit_outcome,
        "visit_activity_retained": visit_activity_retained,
        "all_active_pairs_associated": all_active_pairs_associated,
        "input_immutable": True,
        "scientific_passed": visit_activity_retained and all_active_pairs_associated,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(
        comparison["outcome"]
        for row in rows
        for comparison in row["receiver_comparisons"]
    )
    routes = Counter(
        decision["route"] for row in rows for decision in row["candidate"]
    )
    visits = Counter(row["visit_outcome"] for row in rows)
    return {
        "physical_visits": len(rows),
        "receiver_rows": 2 * len(rows),
        "reference_positive_receivers": sum(
            comparison["reference_active"]
            for row in rows
            for comparison in row["receiver_comparisons"]
        ),
        "candidate_positive_receivers": sum(
            comparison["candidate_active"]
            for row in rows
            for comparison in row["receiver_comparisons"]
        ),
        "outcomes": dict(sorted(outcomes.items())),
        "visit_outcomes": dict(sorted(visits.items())),
        "routes": dict(sorted(routes.items())),
        "scientific_passed_rows": sum(row["scientific_passed"] for row in rows),
    }


def _fixed_cases() -> tuple[dataset.Case, ...]:
    cases = dataset.real_cases()
    if len(cases) != EXPECTED_CASES or len({case.id for case in cases}) != EXPECTED_CASES:
        raise ValueError("TG11 fixed real inventory changed")
    for rate in dataset.RATES:
        selected = [case for case in cases if case.rate == rate]
        if len(selected) != 32 or [case.visit_index for case in selected] != sorted(
            case.visit_index for case in selected
        ):
            raise ValueError("TG11 real visits are not chronological within rate/session")
    return cases


def _prerequisites() -> tuple[dict[str, Any], dict[str, Any], tuple[dataset.Case, ...]]:
    dataset.verify_sources()
    cases = _fixed_cases()
    stage0 = _load_json(STAGE0_RESULT)
    validate_stage0(stage0)
    phase1 = _load_json(PHASE1_RESULT)
    expected_timing = tuple(case.id for case in dataset.timing_cases())
    validate_phase1(phase1, expected_timing)
    return stage0, phase1, cases


def main() -> None:
    if sys.argv[1:] == ["--freeze"]:
        _, _, cases = _prerequisites()
        payload = {
            "stage": "frozen_before_phase2_real_replay_outcomes",
            "files": source_files(),
            "membership_digest": dataset.membership_digest(),
            "case_ids": [case.id for case in cases],
            "stage0_lock_sha256": digest(STAGE0_LOCK),
            "stage0_result_sha256": digest(STAGE0_RESULT),
            "phase1_lock_sha256": digest(PHASE1_LOCK),
            "phase1_result_sha256": digest(PHASE1_RESULT),
        }
        with PHASE2_LOCK.open("x") as stream:
            json.dump(payload, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return
    if sys.argv[1:]:
        raise ValueError("unexpected arguments")
    for name in (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        if os.environ.get(name) != "1":
            raise ValueError(f"{name} must equal one before numerical imports")
    _, phase1, cases = _prerequisites()
    lock = _load_json(PHASE2_LOCK)
    verify_phase2_lock(lock)
    if lock.get("case_ids") != [case.id for case in cases]:
        raise ValueError("phase-two real membership differs from its lock")
    if OUTPUT.exists():
        raise ValueError("preserve existing phase-two replay result")
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    rows: list[dict[str, Any]] = []
    status, error = "complete", None
    started = time.perf_counter()

    def timeout(*_):
        raise TimeoutError("300 second TG11 phase-two budget reached")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(300)
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            geometries = sorted({(case.rate, case.edge) for case in cases})
            detectors = {
                geometry: TG11Detector(
                    stack.enter_context(
                        NativeTG11(*geometry, library=HERE / "libtg11.so")
                    )
                )
                for geometry in geometries
            }
            for index, case in enumerate(cases):
                row = execute_case(
                    case,
                    detectors[(case.rate, case.edge)],
                    candidate_first=bool(index % 2),
                )
                rows.append(row)
                print(
                    json.dumps(
                        {
                            "visit": index + 1,
                            "of": EXPECTED_CASES,
                            "case": case.id,
                            "route": [item["route"] for item in row["candidate"]],
                            "scientific_passed": row["scientific_passed"],
                        }
                    ),
                    flush=True,
                )
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)

    source_stable = all(
        digest(name) == expected.removeprefix("sha256:")
        for name, expected in lock["files"].items()
    )
    complete = (
        status == "complete"
        and len(rows) == EXPECTED_CASES
        and source_stable
        and all(row["input_immutable"] for row in rows)
    )
    summary = summarize(rows)
    payload = {
        "schema": "org.leo.research.tg11-phase2-real-replay/v1",
        "status": status,
        "error": error,
        "source_lock": lock,
        "source_lock_stable": source_stable,
        "stage0_control_result_sha256": "sha256:" + digest(STAGE0_RESULT),
        "phase1_cost_result_sha256": "sha256:" + digest(PHASE1_RESULT),
        "phase1_authorized": phase1["phase2_authorized"],
        "expected_physical_visits": EXPECTED_CASES,
        "completed_physical_visits": len(rows),
        "complete_gate_passed": complete,
        "scientific_gate_passed": complete
        and all(row["scientific_passed"] for row in rows),
        "holdout_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
        "summary": summary,
        "rows": rows,
    }
    with OUTPUT.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "status": status,
                "visits": len(rows),
                "complete": complete,
                "scientific_gate_passed": payload["scientific_gate_passed"],
                "routes": summary["routes"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
