"""Frozen TG11 phase-one paired cost gate on four development visits."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
# Pin the current repository before native_engine can prepend deployment paths.
sys.path[:0] = [str(ROOT / "src"), str(HERE)]

import numpy as np
import leo
import leo.analysis.starlink.acquisition as acquisition
import leo.analysis.starlink.pilot_methods as pilot_methods
import leo.analysis.starlink.templates as templates
import leo.scanner.detector as scanner_detector
from leo.scanner.models import ScannerConfiguration, current_low_band_targets

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("phase one must use the current repository leo package")
if Path(templates.__file__).resolve() != ROOT / "src/leo/analysis/starlink/templates.py":
    raise RuntimeError("phase one must use the current repository templates")

from decision import CacheKey, TG11Detector
from native_engine import NativeTG11
import tg11_dataset as dataset

THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)
METHODS = ("application", "tg11")
CPU_BUDGET_MS = {2_500_000: 143.427, 5_000_000: 389.020}
TIMEOUT_SECONDS = 120


def digest(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def output_hash(value) -> str:
    return hashlib.sha256(stable_json(value).encode()).hexdigest()


def make_key(case, receiver: int) -> CacheKey:
    return CacheKey(case.session, receiver, case.channel, case.edge, case.rate,
                    case.tuning_identity, case.calibration_identity)


def configuration(case) -> ScannerConfiguration:
    target = next(
        item for item in current_low_band_targets()
        if item.channel == case.channel and item.edge.value == case.edge
    )
    return ScannerConfiguration(
        sample_rate_hz=case.rate, bandwidth_hz=case.rate, dwell_ms=120,
        receiver_ids=(0, 1), maximum_acquisition_candidates=10,
        targets=(target,),
    )


def application_call(raw: np.ndarray, case):
    samples = np.empty(raw.shape[:2], dtype=np.complex64)
    samples.real = raw[:, :, 0]
    samples.imag = raw[:, :, 1]
    samples.setflags(write=False)
    return scanner_detector.analyze_glrt64_dwell(
        samples, configuration(case), edge=case.edge
    )


def candidate_call(raw: np.ndarray, case, detector: TG11Detector):
    decisions = tuple(
        detector.process(raw, make_key(case, receiver),
                         start_counter=case.source_counter,
                         visit_index=int(case.visit_index))
        for receiver in (0, 1)
    )
    # Match the comparator's visit-level objective: either receiver may supply
    # the active pair. Deterministic receiver order resolves simultaneous hits.
    selected = next((item for item in decisions if item.active), decisions[0])
    return decisions, selected


def timed(function):
    cpu = time.process_time_ns()
    wall = time.perf_counter_ns()
    result = function()
    return result, {
        "process_cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def serialize_application(result) -> dict:
    payload = asdict(result)
    payload["first"] = None if result.first is None else result.first.model_dump(mode="json")
    return payload


def serialize_candidate(value) -> dict:
    decisions, selected = value
    return {"receiver_decisions": [asdict(item) for item in decisions],
            "selected": asdict(selected)}


def scientific_comparison(case, analysis, candidate) -> dict:
    inventory = dataset.reference_positive_pair_inventory(analysis, case)
    decisions, selected = candidate
    reference_active = bool(inventory)
    analysis_active = analysis.first is not None
    if reference_active != analysis_active:
        raise ValueError("full comparator inventory disagrees with its first decision")
    receiver_comparisons = []
    for receiver, decision in enumerate(decisions):
        receiver_inventory = tuple(item for item in inventory if item.receiver == receiver)
        association = dataset.associate_candidate_to_reference(
            decision, receiver_inventory, case
        )
        receiver_comparisons.append({
            "receiver": receiver,
            "reference_pair_count": len(receiver_inventory),
            "candidate_active": bool(decision.active),
            "association": asdict(association),
            "active_pair_associated": not decision.active or association.matched,
        })
    candidate_active = any(item.active for item in decisions)
    all_active_associated = all(
        item["active_pair_associated"] for item in receiver_comparisons
    )
    retained = candidate_active if reference_active else not candidate_active
    passed = retained and all_active_associated
    return {
        "reference_active": reference_active,
        "analysis_first_present": analysis_active,
        "inventory_decision_invariant": True,
        "reference_pair_count": len(inventory),
        "candidate_active": candidate_active,
        "selected_receiver": selected.pair.receiver if selected.pair is not None else None,
        "receiver_comparisons": receiver_comparisons,
        "all_active_pairs_associated": all_active_associated,
        "visit_activity_retained": retained,
        "passed": passed,
    }


def source_files() -> dict[str, str]:
    stage0 = json.loads((HERE / "source_lock_stage0.json").read_text())
    for name, expected in stage0["files"].items():
        if digest(name) != expected:
            raise ValueError(f"stage-zero source changed: {name}")
    stage0_result = json.loads((HERE / "control_results.json").read_text())
    if not stage0_result.get("scientific_gate_passed"):
        raise ValueError("stage-zero scientific gate did not pass")
    paths = {
        HERE / "run_phase1_cost.py", HERE / "test_phase1_cost.py",
        HERE / "source_lock_stage0.json", HERE / "control_results.json",
        HERE / "RUN_PROTOCOL.md", HERE / "design.json", HERE / "decision.py",
        HERE / "native_engine.py", HERE / "tg11_dataset.py",
        HERE / "libtg11.so", HERE / "libtg11.so.build.json",
        Path(scanner_detector.__file__), Path(acquisition.__file__),
        Path(pilot_methods.__file__), Path(templates.__file__),
        ROOT / "src/leo/scanner/models.py",
    }
    paths |= set(dataset.SOURCE_HASHES)
    return {str(path.resolve()): digest(path) for path in sorted(paths)}


def verify_lock(lock: dict) -> None:
    if lock["membership_digest"] != dataset.membership_digest():
        raise ValueError("phase-one membership changed")
    if [case.id for case in dataset.timing_cases()] != lock["selected_case_ids"]:
        raise ValueError("phase-one selected cases changed")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"phase-one source changed: {name}")
    if digest(HERE / "control_results.json") != lock["stage0_control_result_sha256"]:
        raise ValueError("stage-zero result changed")


def summarize(rows: list[dict]) -> dict:
    output = {}
    for rate in dataset.RATES:
        selected = [row for row in rows if row["rate_hz"] == rate]
        application = [measurement["process_cpu_ms"] for row in selected
                       for measurement in row["measurements"]
                       if measurement["method"] == "application"]
        tg11 = [measurement["process_cpu_ms"] for row in selected
                for measurement in row["measurements"]
                if measurement["method"] == "tg11"]
        app_wall = [measurement["wall_ms"] for row in selected
                    for measurement in row["measurements"]
                    if measurement["method"] == "application"]
        tg_wall = [measurement["wall_ms"] for row in selected
                   for measurement in row["measurements"]
                   if measurement["method"] == "tg11"]
        if len(application) != 6 or len(tg11) != 6:
            output[str(rate)] = {"complete": False, "cost_gate_passed": False}
            continue
        application_median = statistics.median(application)
        tg11_median = statistics.median(tg11)
        speedup = application_median / tg11_median
        output[str(rate)] = {
            "complete": True,
            "application_median_process_cpu_ms": application_median,
            "tg11_median_process_cpu_ms": tg11_median,
            "application_median_wall_ms": statistics.median(app_wall),
            "tg11_median_wall_ms": statistics.median(tg_wall),
            "process_cpu_speedup": speedup,
            "absolute_budget_ms": CPU_BUDGET_MS[rate],
            "speedup_gate_passed": speedup >= 10.0,
            "absolute_gate_passed": tg11_median < CPU_BUDGET_MS[rate],
            "cost_gate_passed": speedup >= 10.0 and tg11_median < CPU_BUDGET_MS[rate],
        }
    return output


def execute_case(case, detector: TG11Detector) -> dict:
    raw = dataset.load_iq(case)
    original_hash = hashlib.sha256(raw).hexdigest()
    snapshot = detector.snapshot()

    # One warmup for each method. Candidate warmup cannot advance causal state.
    warm_application = application_call(raw, case)
    detector.restore(snapshot)
    warm_candidate = candidate_call(raw, case, detector)
    detector.restore(snapshot)
    expected_application = output_hash(serialize_application(warm_application))
    expected_candidate = output_hash(serialize_candidate(warm_candidate))

    measurements = []
    observed_application = warm_application
    observed_candidate = warm_candidate
    for repeat in range(3):
        order = METHODS[repeat % 2:] + METHODS[:repeat % 2]
        for method in order:
            if method == "application":
                observed_application, timing = timed(lambda: application_call(raw, case))
                serialized = serialize_application(observed_application)
                expected = expected_application
            else:
                detector.restore(snapshot)
                observed_candidate, timing = timed(lambda: candidate_call(raw, case, detector))
                detector.restore(snapshot)
                serialized = serialize_candidate(observed_candidate)
                expected = expected_candidate
            result_hash = output_hash(serialized)
            if result_hash != expected:
                raise ValueError(f"{method} repeated output changed for {case.id}")
            measurements.append({"repeat": repeat, "method": method,
                                 "output_sha256": result_hash, **timing})

    # Advance state exactly once for this physical visit.
    detector.restore(snapshot)
    committed = candidate_call(raw, case, detector)
    committed_serialized = serialize_candidate(committed)
    if output_hash(committed_serialized) != expected_candidate:
        raise ValueError("committed candidate differs from timed candidate")
    comparison = scientific_comparison(case, observed_application, committed)
    input_immutable = (
        hashlib.sha256(raw).hexdigest() == original_hash
        and digest(case.raw_path) == case.raw_sha256.removeprefix("sha256:")
    )
    if not input_immutable:
        raise ValueError("phase-one input changed")
    summary = {
        method: {
            "median_process_cpu_ms": statistics.median(
                row["process_cpu_ms"] for row in measurements if row["method"] == method
            ),
            "median_wall_ms": statistics.median(
                row["wall_ms"] for row in measurements if row["method"] == method
            ),
        }
        for method in METHODS
    }
    return {
        "case_id": case.id, "rate_hz": case.rate, "edge": case.edge,
        "channel": case.channel, "session_id": case.session,
        "visit_index": case.visit_index, "source_counter": case.source_counter,
        "raw_sha256": case.raw_sha256, "input_immutable": input_immutable,
        "warmup_output_sha256": {"application": expected_application,
                                  "tg11": expected_candidate},
        "measurements": measurements, "summary": summary,
        "application_output": serialize_application(observed_application),
        "candidate_output": committed_serialized,
        "candidate_route_counts": {
            route: sum(item.route == route for item in committed[0])
            for route in sorted({item.route for item in committed[0]})
        },
        "scientific": comparison,
        "repeat_outputs_deterministic": True,
        "candidate_state_commits": 1,
    }


def main() -> None:
    lock_path = HERE / "source_lock_phase1.json"
    result_path = HERE / "phase1_cost_results.json"
    if sys.argv[1:] == ["--freeze"]:
        if lock_path.exists():
            raise ValueError("preserve existing phase-one source lock")
        selected = dataset.timing_cases()
        payload = {
            "stage": "frozen_before_phase_one_real_outcomes",
            "files": source_files(),
            "membership_digest": dataset.membership_digest(),
            "selected_case_ids": [case.id for case in selected],
            "stage0_control_result_sha256": digest(HERE / "control_results.json"),
            "per_rate_summary_rule": "median of six calls: two cases times three repetitions",
            "cost_gates": {str(rate): {"minimum_cpu_speedup": 10.0,
                                         "maximum_tg11_cpu_ms": budget}
                           for rate, budget in CPU_BUDGET_MS.items()},
        }
        with lock_path.open("x") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
        return
    if sys.argv[1:]:
        raise ValueError("unexpected arguments")
    if result_path.exists():
        raise ValueError("preserve existing phase-one result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread counts must equal one")
    lock = json.loads(lock_path.read_text())
    verify_lock(lock)
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    rows, status, error = [], "complete", None
    started = time.perf_counter()
    previous = signal.signal(signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("120 second phase-one bound")))
    signal.alarm(TIMEOUT_SECONDS)
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            geometries = sorted({(case.rate, case.edge) for case in dataset.timing_cases()})
            engines = {geometry: stack.enter_context(
                NativeTG11(*geometry, library=HERE / "libtg11.so"))
                for geometry in geometries}
            detectors = {geometry: TG11Detector(engine) for geometry, engine in engines.items()}
            for case in dataset.timing_cases():
                row = execute_case(case, detectors[(case.rate, case.edge)])
                rows.append(row)
                print(json.dumps({"case": case.id, "rate": case.rate,
                                  "application_cpu_ms": row["summary"]["application"]["median_process_cpu_ms"],
                                  "tg11_cpu_ms": row["summary"]["tg11"]["median_process_cpu_ms"]}),
                      flush=True)
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    source_stable = all(digest(name) == expected for name, expected in lock["files"].items())
    per_rate = summarize(rows)
    complete = (
        status == "complete" and len(rows) == 4 and source_stable
        and all(len(row["measurements"]) == 6 and row["repeat_outputs_deterministic"]
                and row["input_immutable"] and row["candidate_state_commits"] == 1
                for row in rows)
    )
    scientific = complete and all(row["scientific"]["passed"] for row in rows)
    cost = complete and all(per_rate.get(str(rate), {}).get("cost_gate_passed", False)
                            for rate in dataset.RATES)
    stage0 = json.loads((HERE / "control_results.json").read_text())
    authorized = bool(stage0.get("scientific_gate_passed") and complete and scientific and cost)
    payload = {
        "schema": "org.leo.research.tg11-phase1-cost/v1",
        "status": status, "error": error, "source_lock": lock,
        "source_lock_stable": source_stable,
        "stage0_control_result_sha256": digest(HERE / "control_results.json"),
        "thread_environment": environment, "affinity_cpu": 0,
        "affinity_restored": sorted(affinity), "timeout_seconds": TIMEOUT_SECONDS,
        "selected_case_ids": lock["selected_case_ids"], "rows": rows,
        "per_rate_summary": per_rate, "complete_gate_passed": complete,
        "scientific_gate_passed": scientific, "cost_gate_passed": cost,
        "phase2_authorized": authorized, "holdout_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    with result_path.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": status, "complete": complete, "science": scientific,
                      "cost": cost, "phase2_authorized": authorized}), flush=True)


if __name__ == "__main__":
    main()
