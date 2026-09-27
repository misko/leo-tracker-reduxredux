"""Bounded fixed same-CFO interference challenge after native state establishment."""

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
TG11 = HERE.parent / "tg11"
sys.path[:0] = [str(ROOT / "src"), str(HERE), str(TG11)]
import leo
if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("challenge must pin the current repository package")

from native_engine import NativeTG11
from native_tradeoff_detector import NativeTradeoffDetector
from decision import CacheKey
import cache_challenge_fixtures as fixtures

LOCK = HERE / "source_lock.cache_challenge.json"
OUTPUT = HERE / "results.cache_challenge.json"
THREAD_ENV = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
              "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_files(files):
    for name, expected in files.items():
        if digest(name) != expected:
            raise ValueError(f"frozen source changed: {name}")


def freeze():
    controls = json.loads((HERE / "results.controls.json").read_text())
    if not controls["complete"]:
        raise ValueError("complete Stage A integrity receipt required")
    previous = json.loads((HERE / "source_lock.controls.json").read_text())
    verify_files(previous["files"])
    files = dict(previous["files"])
    for path in (Path(__file__), HERE / "cache_challenge_fixtures.py",
                 HERE / "test_cache_challenge_fixtures.py",
                 HERE / "results.controls.json", HERE / "source_lock.controls.json"):
        files[str(path.resolve())] = digest(path)
    with LOCK.open("x") as stream:
        json.dump({"files": files, "expected_physical_steps": 14,
                   "methods": ["native_blind", "native_tracked"],
                   "same_cfo_replacement": True, "timeout_seconds": 120,
                   "holdout_opened": False, "validation_opened": False}, stream, indent=2)


def main():
    if sys.argv[1:] == ["--freeze"]:
        freeze()
        return
    if sys.argv[1:] or OUTPUT.exists():
        raise ValueError("unexpected arguments or existing receipt")
    lock = json.loads(LOCK.read_text())
    verify_files(lock["files"])
    if any(os.environ.get(name) != "1" for name in THREAD_ENV):
        raise ValueError("set numerical thread counts to one before import")
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    rows, status, error = [], "complete", None
    started = time.perf_counter()
    def timeout(*_):
        raise TimeoutError("120 second same-CFO challenge bound")
    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        os.sched_setaffinity(0, {0})
        for sequence in fixtures.sequences():
            case = sequence[0].case
            with NativeTG11(case.rate, case.edge, library=TG11 / "libtg11.so") as engine:
                methods = {name: NativeTradeoffDetector(engine) for name in lock["methods"]}
                for index, step in enumerate(sequence):
                    case = step.case
                    measurements = {}
                    ordered = lock["methods"][index % 2:] + lock["methods"][:index % 2]
                    for name in ordered:
                        cpu, wall = time.process_time_ns(), time.perf_counter_ns()
                        decisions = tuple(methods[name].process(
                            step.raw, CacheKey(case.session, receiver, case.channel, case.edge,
                                               case.rate, case.tuning_identity, case.calibration_identity),
                            start_counter=case.source_counter, visit_index=index,
                            force_discovery=name == "native_blind",
                        ) for receiver in (0, 1))
                        timing = {"cpu_ms": (time.process_time_ns() - cpu) / 1e6,
                                  "wall_ms": (time.perf_counter_ns() - wall) / 1e6}
                        gates = [
                            fixtures.dataset.control_gate(case, receiver, decision)
                            if step.expected_active else {
                                "receiver": receiver, "expected": "inactive",
                                "observed_active": decision.active,
                                "passed": not decision.active,
                                "reason": "generated noise plus tones contains no pilot",
                            }
                            for receiver, decision in enumerate(decisions)
                        ]
                        measurements[name] = {"decisions": [asdict(d) for d in decisions],
                                              "truth": gates, "timing_diagnostic": timing}
                    if hashlib.sha256(step.raw).hexdigest() != step.array_sha256:
                        raise ValueError("challenge input mutated")
                    rows.append({
                        "case_id": case.id, "rate_hz": case.rate, "edge": case.edge,
                        "step": index, "kind": step.kind, "source_counter": case.source_counter,
                        "input_array_sha256": step.array_sha256, "input_immutable": True,
                        "expected_active": step.expected_active, "noise_seeds": step.noise_seeds,
                        "tone_frequencies_hz": step.tone_frequencies_hz,
                        "carrier_phase_reset": step.carrier_phase_reset,
                        "reused_pilot_file_sha256": case.raw_sha256 if step.expected_active else None,
                        "virtual_counter_delta_samples": step.virtual_counter_delta_samples,
                        "methods": measurements,
                    })
                    print(json.dumps({"challenge": case.id,
                                      "passed": all(g["passed"] for m in measurements.values()
                                                    for g in m["truth"])}), flush=True)
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    stable = all(digest(name) == expected for name, expected in lock["files"].items())
    complete = status == "complete" and stable and len(rows) == lock["expected_physical_steps"]
    summary = {}
    for name in lock["methods"]:
        evaluated = [g for row in rows for g in row["methods"][name]["truth"]]
        summary[name] = {
            "receiver_rows": len(evaluated),
            "truth_failures": sum(not g["passed"] for g in evaluated),
            "negative_false_positives": sum(
                d["active"] for row in rows if not row["expected_active"]
                for d in row["methods"][name]["decisions"]),
            "route_counts": {route: sum(d["route"] == route for row in rows
                                         for d in row["methods"][name]["decisions"])
                             for route in sorted({d["route"] for row in rows
                                                  for d in row["methods"][name]["decisions"]})},
        }
    payload = {"schema": "org.leo.research.native-same-cfo-challenge/v1",
               "status": status, "error": error, "complete": complete,
               "source_lock": lock, "source_lock_stable": stable,
               "summary": summary, "rows": rows,
               "holdout_opened": False, "validation_opened": False,
               "elapsed_seconds": time.perf_counter() - started}
    with OUTPUT.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
    print(json.dumps({"complete": complete, "summary": summary}), flush=True)


if __name__ == "__main__":
    main()
