"""Frozen constructed-control and sequence gate for canonical tracking."""

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
REPORT = HERE.parent
ROOT = HERE.parents[2]
TG11 = REPORT / "tg11"
sys.path[:0] = [str(ROOT / "src"), str(TG11), str(HERE)]

import numpy as np
import leo
import leo.analysis.starlink.pilot_methods as pilot_methods
import leo.analysis.starlink.templates as templates

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("canonical controls must use current repository leo")
if Path(templates.__file__).resolve() != ROOT / "src/leo/analysis/starlink/templates.py":
    raise RuntimeError("canonical controls must use current repository templates")

from canonical_detector import CanonicalTrackingDetector
from decision import CacheKey
from native_engine import NativeTG11
import tg11_dataset as dataset

THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)
METHODS = ("cached", "all_blind")
TIMEOUT_SECONDS = 120


def digest(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def stable_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def make_key(case, receiver: int) -> CacheKey:
    return CacheKey(case.session, receiver, case.channel, case.edge, case.rate,
                    case.tuning_identity, case.calibration_identity)


def adapt_observation(observation) -> dict:
    return {
        "receiver": observation.receiver,
        "probe_index": observation.probe_index,
        "probe_start_sample": observation.probe_start_sample,
        "local_epoch_sample": observation.local_epoch_sample,
        "dwell_epoch_sample": observation.dwell_epoch_sample,
        "tracking_cfo_hz": observation.tracking_cfo_hz,
        "margin": observation.margin,
        "supported": observation.supported,
        "support_frames": observation.support_frames,
        "fractional_complete": observation.fractional_complete,
    }


def adapt_decision(decision) -> dict:
    pair = None
    if decision.pair is not None:
        pair = {
            "receiver": decision.pair.receiver,
            "first": adapt_observation(decision.pair.first),
            "second": adapt_observation(decision.pair.second),
        }
    return {"active": decision.active, "pair": pair}


def process_visit(detector, raw, case, visit_index: int):
    return tuple(
        detector.process(raw, make_key(case, receiver),
                         start_counter=case.source_counter,
                         visit_index=visit_index)
        for receiver in (0, 1)
    )


def truth_gates(case, decisions) -> list[dict]:
    return [dataset.control_gate(case, receiver, adapt_decision(decision))
            for receiver, decision in enumerate(decisions)]


def sequence_route_gate(sequence_id: str, step_index: int, decision) -> tuple[bool, str]:
    if sequence_id in ("pilot-dropout", "changed-pilot") and step_index == 1:
        return decision.route == "guided", "repeated identical pilot must guide"
    if sequence_id == "changed-pilot" and step_index == 2:
        return decision.route == "discovery_guided_failure", "wrong track must fail open"
    if sequence_id == "quiet-to-pilot" and step_index == 2:
        return decision.route.startswith("discovery_"), "first pilot must be discovered"
    if sequence_id == "pilot-dropout" and step_index in (2, 3):
        return not decision.active, "dropout must remain inactive"
    return True, "no additional route requirement"


def sequence_comparison(case, cached, all_blind) -> list[dict]:
    cached_gates = truth_gates(case, cached)
    blind_gates = truth_gates(case, all_blind)
    comparisons = []
    for receiver in (0, 1):
        same_activity = cached[receiver].active == all_blind[receiver].active
        cached_trajectory = cached_gates[receiver]["matched_trajectory"]
        blind_trajectory = blind_gates[receiver]["matched_trajectory"]
        same_association = cached_trajectory == blind_trajectory
        comparisons.append({
            "receiver": receiver, "same_activity": same_activity,
            "same_association": same_association,
            "cached_truth_passed": cached_gates[receiver]["passed"],
            "all_blind_truth_passed": blind_gates[receiver]["passed"],
            "cached_trajectory": cached_trajectory,
            "all_blind_trajectory": blind_trajectory,
            "passed": same_activity and same_association
                and cached_gates[receiver]["passed"] and blind_gates[receiver]["passed"],
        })
    return comparisons


def serialize(decisions) -> list[dict]:
    return [asdict(item) for item in decisions]


def timed(function):
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    result = function()
    return result, {"process_cpu_ms": (time.process_time_ns() - cpu) / 1e6,
                    "wall_ms": (time.perf_counter_ns() - wall) / 1e6}


def run_sequence_inventory(sequence_items, engine, *, cached_detector=None,
                           all_blind=False):
    outputs = []
    for sequence_id, step_index, case, raw in sequence_items:
        detector = CanonicalTrackingDetector(engine) if all_blind else cached_detector
        if detector is None:
            raise ValueError("cached sequence detector required")
        decisions = process_visit(detector, raw, case, step_index)
        outputs.append((sequence_id, step_index, case, decisions))
    return outputs


def sequence_output_hash(outputs) -> str:
    return stable_hash([
        {"sequence": sequence, "step": step, "case_id": case.id,
         "decisions": serialize(decisions)}
        for sequence, step, case, decisions in outputs
    ])


def source_files() -> dict[str, str]:
    paths = {
        HERE / "CONTROL_PROTOCOL.md", HERE / "run_controls.py",
        HERE / "test_canonical_control_runner.py", HERE / "canonical_detector.py",
        HERE / "test_canonical_detector.py",
        TG11 / "native_engine.py", TG11 / "decision.py", TG11 / "tg11_dataset.py",
        TG11 / "libtg11.so", TG11 / "libtg11.so.build.json",
        Path(pilot_methods.__file__), Path(templates.__file__),
        ROOT / "src/leo/analysis/starlink/acquisition.py",
    }
    paths |= set(dataset.SOURCE_HASHES)
    receipt = json.loads((TG11 / "libtg11.so.build.json").read_text())
    if digest(TG11 / "libtg11.so") != receipt["binary_sha256"]:
        raise ValueError("native binary changed")
    for name, expected in receipt["sources_sha256"].items():
        if digest(name) != expected:
            raise ValueError(f"native dependency changed: {name}")
        paths.add(Path(name))
    return {str(path.resolve()): digest(path) for path in sorted(paths)}


def verify_lock(lock: dict) -> None:
    if lock["membership_digest"] != dataset.membership_digest():
        raise ValueError("canonical control membership changed")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"canonical control source changed: {name}")


def main() -> None:
    lock_path = HERE / "source_lock.json"
    result_path = HERE / "control_results.json"
    if sys.argv[1:] == ["--freeze"]:
        if lock_path.exists():
            raise ValueError("preserve canonical control source lock")
        controls = dataset.controls()
        sequences = dataset.sequences()
        payload = {
            "stage": "frozen_before_canonical_constructed_controls",
            "files": source_files(), "membership_digest": dataset.membership_digest(),
            "inventory": {"base_physical": len(controls),
                          "sequence_physical": sum(len(item.steps) for item in sequences),
                          "cached_receiver_rows": 2 * (len(controls) + sum(len(item.steps) for item in sequences)),
                          "all_blind_sequence_receiver_rows": 2 * sum(len(item.steps) for item in sequences)},
            "timing": "whole ten-step sequence inventory, both RX, one warmup plus three counterbalanced repeats",
            "timeout_seconds": TIMEOUT_SECONDS, "holdout": False,
        }
        lock_path.write_text(json.dumps(payload, indent=2) + "\n")
        return
    if sys.argv[1:]:
        raise ValueError("unexpected arguments")
    if result_path.exists():
        raise ValueError("preserve canonical control result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread counts must equal one")
    lock = json.loads(lock_path.read_text())
    verify_lock(lock)
    controls, sequences = dataset.controls(), dataset.sequences()
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    base_rows, sequence_rows, measurements = [], [], []
    status, error = "complete", None
    started = time.perf_counter()
    previous = signal.signal(signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("120 second canonical control bound")))
    signal.alarm(TIMEOUT_SECONDS)
    try:
        # Loading and all source/input hashing are outside timed detector calls.
        raw_by_id = {case.id: dataset.load_iq(case) for case in controls}
        sequence_items = [
            (sequence.id, index, step.case, dataset.load_iq(step.case))
            for sequence in sequences for index, step in enumerate(sequence.steps)
        ]
        sequence_input_hashes = {
            case.id: hashlib.sha256(raw).hexdigest()
            for _sequence, _step, case, raw in sequence_items
        }
        os.sched_setaffinity(0, {0})
        geometries = sorted({(case.rate, case.edge) for case in controls})
        with ExitStack() as stack:
            engines = {geometry: stack.enter_context(
                NativeTG11(*geometry, library=TG11 / "libtg11.so"))
                for geometry in geometries}
            base_detectors = {geometry: CanonicalTrackingDetector(engine)
                              for geometry, engine in engines.items()}
            for index, case in enumerate(controls):
                raw = raw_by_id[case.id]
                before = hashlib.sha256(raw).hexdigest()
                decisions = process_visit(
                    base_detectors[(case.rate, case.edge)], raw, case, 0
                )
                gates = truth_gates(case, decisions)
                if hashlib.sha256(raw).hexdigest() != before:
                    raise ValueError("base control input mutated")
                base_rows.append({"case_id": case.id, "rate_hz": case.rate,
                                  "edge": case.edge, "input_immutable": True,
                                  "decisions": serialize(decisions), "gates": gates,
                                  "passed": all(item["passed"] for item in gates)})
                print(json.dumps({"base": index + 1, "case": case.id,
                                  "passed": base_rows[-1]["passed"]}), flush=True)

            sequence_engine = engines[(2_500_000, "lower")]
            cached_detector = CanonicalTrackingDetector(sequence_engine)
            empty = cached_detector.snapshot()
            # Warmups do not advance the scientific state.
            run_sequence_inventory(sequence_items, sequence_engine,
                                   cached_detector=cached_detector)
            cached_detector.restore(empty)
            run_sequence_inventory(sequence_items, sequence_engine, all_blind=True)
            expected = {}
            for repeat in range(3):
                order = METHODS[repeat % 2:] + METHODS[:repeat % 2]
                for method in order:
                    if method == "cached":
                        cached_detector.restore(empty)
                        outputs, timing = timed(lambda: run_sequence_inventory(
                            sequence_items, sequence_engine,
                            cached_detector=cached_detector))
                        cached_detector.restore(empty)
                    else:
                        outputs, timing = timed(lambda: run_sequence_inventory(
                            sequence_items, sequence_engine, all_blind=True))
                    result_hash = sequence_output_hash(outputs)
                    if method in expected and expected[method] != result_hash:
                        raise ValueError(f"{method} sequence timing output changed")
                    expected.setdefault(method, result_hash)
                    measurements.append({"repeat": repeat, "method": method,
                                         "output_sha256": result_hash, **timing})

            # Commit each cached sequence visit exactly once after timing.
            cached_detector.restore(empty)
            cached_outputs = run_sequence_inventory(
                sequence_items, sequence_engine, cached_detector=cached_detector
            )
            blind_outputs = run_sequence_inventory(
                sequence_items, sequence_engine, all_blind=True
            )
            if (sequence_output_hash(cached_outputs) != expected["cached"]
                    or sequence_output_hash(blind_outputs) != expected["all_blind"]):
                raise ValueError("committed sequence differs from timed repetitions")
            for cached_item, blind_item in zip(cached_outputs, blind_outputs, strict=True):
                sequence_id, step_index, case, cached = cached_item
                if blind_item[:3] != cached_item[:3]:
                    raise ValueError("sequence method inventories differ")
                blind = blind_item[3]
                raw = next(item[3] for item in sequence_items
                           if item[0] == sequence_id and item[1] == step_index)
                if hashlib.sha256(raw).hexdigest() != sequence_input_hashes[case.id]:
                    raise ValueError("sequence control input mutated")
                cached_gates = truth_gates(case, cached)
                blind_gates = truth_gates(case, blind)
                comparisons = sequence_comparison(case, cached, blind)
                route_gates = []
                for receiver, decision in enumerate(cached):
                    passed, reason = sequence_route_gate(sequence_id, step_index, decision)
                    route_gates.append({"receiver": receiver, "route": decision.route,
                                        "passed": passed, "reason": reason})
                sequence_rows.append({
                    "sequence": sequence_id, "step": step_index, "case_id": case.id,
                    "input_immutable": True,
                    "cached_decisions": serialize(cached),
                    "all_blind_decisions": serialize(blind),
                    "cached_truth_gates": cached_gates,
                    "all_blind_truth_gates": blind_gates,
                    "comparisons": comparisons, "route_gates": route_gates,
                    "passed": all(item["passed"] for item in comparisons + route_gates),
                })
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    stable = all(digest(name) == expected for name, expected in lock["files"].items())
    timing_summary = {}
    for method in METHODS:
        selected = [item for item in measurements if item["method"] == method]
        timing_summary[method] = {
            "median_process_cpu_ms": statistics.median(item["process_cpu_ms"] for item in selected) if selected else None,
            "median_wall_ms": statistics.median(item["wall_ms"] for item in selected) if selected else None,
        }
    complete = (status == "complete" and len(base_rows) == 32
                and len(sequence_rows) == 10 and len(measurements) == 6 and stable)
    scientific = complete and all(item["passed"] for item in base_rows + sequence_rows)
    route_counts = {}
    for row in base_rows:
        for decision in row["decisions"]:
            route_counts[decision["route"]] = route_counts.get(decision["route"], 0) + 1
    for row in sequence_rows:
        for decision in row["cached_decisions"]:
            route_counts[decision["route"]] = route_counts.get(decision["route"], 0) + 1
    payload = {
        "schema": "org.leo.research.canonical-tracking-controls/v1",
        "status": status, "error": error, "source_lock": lock,
        "source_lock_stable": stable, "thread_environment": environment,
        "affinity_cpu": 0, "affinity_restored": sorted(affinity),
        "base_rows": base_rows, "sequence_rows": sequence_rows,
        "timing_measurements": measurements, "timing_summary": timing_summary,
        "route_counts_cached_84_receiver_rows": route_counts,
        "complete_gate_passed": complete, "scientific_gate_passed": scientific,
        "real_replay_authorized": False,
        "real_replay_not_in_scope": True, "holdout_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    result_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": status, "complete": complete,
                      "scientific": scientific, "routes": route_counts}), flush=True)


if __name__ == "__main__":
    main()
