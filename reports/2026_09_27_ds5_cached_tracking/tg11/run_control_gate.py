"""Frozen, bounded TG11 constructed-control gate before costly real replay."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "src"), str(HERE)]

import numpy as np
import leo
if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("TG11 must use the current repository application package")
from decision import CacheKey, TG11Detector
from native_engine import NativeTG11
import tg11_dataset as dataset


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def source_files():
    paths = set(HERE.glob("*.py")) | set(HERE.glob("*.c")) | set(HERE.glob("*.h"))
    paths |= {HERE / "design.json", HERE / "RUN_PROTOCOL.md", HERE / "libtg11.so",
              HERE / "libtg11.so.build.json",
              HERE.parent / "application_coarse_alternatives/TRACK_GUIDED_DESIGN.md"}
    paths |= set(dataset.SOURCE_HASHES)
    paths |= {ROOT / "src/leo/analysis/starlink/templates.py",
              ROOT / "src/leo/scanner/detector.py",
              ROOT / "src/leo/analysis/starlink/acquisition.py",
              ROOT / "src/leo/analysis/starlink/pilot_methods.py",
              ROOT / "src/leo/scanner/models.py"}
    receipt = json.loads((HERE / "libtg11.so.build.json").read_text())
    for name, expected in receipt["sources_sha256"].items():
        if digest(name) != expected.removeprefix("sha256:"):
            raise ValueError(f"native build source changed: {name}")
        paths.add(Path(name))
    if digest(HERE / "libtg11.so") != receipt["binary_sha256"].removeprefix("sha256:"):
        raise ValueError("native binary changed")
    return {str(path.resolve()): digest(path) for path in sorted(paths)}


def verify_lock(lock):
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen TG11 source changed: {name}")
    dataset.verify_sources()
    if dataset.membership_digest() != lock["membership_digest"]:
        raise ValueError("TG11 membership changed")


def make_key(case, receiver):
    return CacheKey(case.session, receiver, case.channel, case.edge, case.rate,
                    case.tuning_identity, case.calibration_identity)


def gate_passed(status, rows, expected_rows, source_stable):
    return (status == "complete" and len(rows) == expected_rows
            and source_stable and all(row["passed"] for row in rows))


def execute_case(case, detector, *, visit_index, sequence=None, step=None):
    raw = dataset.load_iq(case)
    before = hashlib.sha256(raw).hexdigest()
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    decisions = tuple(detector.process(raw, make_key(case, receiver),
                                      start_counter=case.source_counter,
                                      visit_index=visit_index)
                      for receiver in (0, 1))
    measurement = {"cpu_ms": (time.process_time_ns()-cpu)/1e6,
                   "wall_ms": (time.perf_counter_ns()-wall)/1e6}
    if hashlib.sha256(raw).hexdigest() != before or digest(case.raw_path) != case.raw_sha256.removeprefix("sha256:"):
        raise ValueError("TG11 input mutated")
    gates = []
    for receiver, result in enumerate(decisions):
        gate = dataset.control_gate(case, receiver, result)
        gate["complete_fresh_measurement"] = (result.screen_windows == 11 and result.active == (result.pair is not None))
        gate["route_passed"] = True
        if step is not None:
            gate["route_passed"] = (
                result.active == step.expected_active
                and (step.expected_route is None or result.route.startswith(step.expected_route))
            )
            gate["expected_route"] = step.expected_route
        gate["passed"] = gate["passed"] and gate["complete_fresh_measurement"] and gate["route_passed"]
        gates.append(gate)
    return {"case_id": case.id, "rate_hz": case.rate, "edge": case.edge,
            "sequence": sequence, "visit_index": visit_index,
            "source_counter": case.source_counter, "raw_sha256": case.raw_sha256,
            "virtual_counter_delta_samples": case.virtual_counter_delta_samples,
            "frame_lattice_phase_offset_samples": case.frame_lattice_phase_offset_samples,
            "carrier_phase_reset": case.carrier_phase_reset,
            "carrier_phase_offsets_cycles": case.carrier_phase_offsets_cycles,
            "input_immutable": True, "measurement_diagnostic_only": measurement,
            "decisions": [asdict(item) for item in decisions], "gates": gates,
            "passed": all(gate["passed"] for gate in gates)}


def main():
    lock_path = HERE / "source_lock_stage0.json"
    if sys.argv[1:] == ["--freeze"]:
        dataset.verify_sources()
        payload = {"stage": "frozen_before_constructed_control_outcomes",
                   "files": source_files(), "membership_digest": dataset.membership_digest()}
        with lock_path.open("x") as stream:
            json.dump(payload, stream, indent=2)
        return
    if sys.argv[1:]:
        raise ValueError("unexpected arguments")
    lock = json.loads(lock_path.read_text())
    verify_lock(lock)
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(f"{name} must equal one before numerical imports")
    output = HERE / "control_results.json"
    if output.exists():
        raise ValueError("preserve existing control result")
    controls, sequences = dataset.controls(), dataset.sequences()
    if len(controls) != 32 or len(sequences) != 3:
        raise ValueError("frozen control inventory changed")
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    rows, status, error = [], "complete", None
    started = time.perf_counter()
    def timeout(*_):
        raise TimeoutError("120 second TG11 control budget reached")
    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            geometries = sorted({(case.rate, case.edge) for case in controls})
            engines = {geometry: stack.enter_context(NativeTG11(*geometry, library=HERE / "libtg11.so"))
                       for geometry in geometries}
            for index, case in enumerate(controls):
                rows.append(execute_case(case, TG11Detector(engines[(case.rate, case.edge)]),
                                         visit_index=0))
                print(json.dumps({"control": index+1, "case": case.id, "passed": rows[-1]["passed"]}), flush=True)
            for sequence in sequences:
                geometry = (sequence.steps[0].case.rate, sequence.steps[0].case.edge)
                detector = TG11Detector(engines[geometry])
                for index, step in enumerate(sequence.steps):
                    if (step.case.rate, step.case.edge) != geometry:
                        raise ValueError("sequence geometry changed")
                    rows.append(execute_case(step.case, detector, visit_index=index,
                                             sequence=sequence.id, step=step))
                print(json.dumps({"sequence": sequence.id, "steps": len(sequence.steps)}), flush=True)
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    source_stable = all(digest(name) == expected for name, expected in lock["files"].items())
    expected_rows = 32 + sum(len(sequence.steps) for sequence in sequences)
    passed = gate_passed(status, rows, expected_rows, source_stable)
    payload = {"schema": "org.leo.research.tg11-control-gate/v1", "status": status, "error": error,
               "source_lock": lock, "source_lock_stable": source_stable,
               "scientific_gate_passed": passed,
               "real_replay_authorized_by_gate": passed,
               "expected_physical_rows": expected_rows, "completed_physical_rows": len(rows),
               "base_control_receiver_rows": 64, "holdout_opened": False,
               "elapsed_seconds": time.perf_counter()-started, "rows": rows}
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
    print(json.dumps({"status": status, "scientific_gate_passed": passed, "rows": len(rows)}), flush=True)


if __name__ == "__main__":
    main()
