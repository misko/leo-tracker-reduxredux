"""Evaluate the bounded V3 guided-CFO support guard change.

The runner has two fixed lanes: direct guided calls at the 42 coordinates from
the immutable reference-point lock, and causal tracking over the 42 legacy
control/sequence occurrences.  It never runs the full application analyzer.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
TG11 = REPORT / "tg11"
TRADEOFF = REPORT / "native_tradeoff"
REFERENCE = REPORT / "native_reference_points"
REFERENCE_LOCK = REFERENCE / "source_lock.json"
REFERENCE_RESULT = REFERENCE / "results.json"
EXPECTED_REFERENCE_LOCK_SHA256 = "b11f505a456e422310e98465768bee6d4a0669162ce1824ce01c7d7a2fc5dced"
EXPECTED_REFERENCE_RESULT_SHA256 = "c7ef20785c9331e7caaec97009dc33491b5bf9afc67f1d94619a49cc7a5a4cd2"
SOURCE_LOCK = HERE / "source_lock.json"
RESULT = HERE / "results.json"
TIMEOUT_SECONDS = 120
GUARD_TOLERANCE_HZ = 1e-6
RESIDUAL_SUPPORT_HZ = 0.5 / 4.4e-6
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)

sys.path[:0] = [str(ROOT / "src"), str(HERE), str(TG11), str(TRADEOFF)]

import numpy as np  # noqa: E402
import leo  # noqa: E402
from native_engine import NativeTG11  # noqa: E402
from native_tradeoff_detector import NativeTradeoffDetector  # noqa: E402

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("guided-boundary evaluation must use this checkout")


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tradeoff = _load_module(
    "native_guided_boundary_frozen_tradeoff", TRADEOFF / "run_evaluation.py"
)
dataset = tradeoff.dataset


def boundary_engine_class() -> type:
    module = importlib.import_module("native_guided_boundary")
    return module.NativeGuidedBoundary


def digest(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return jsonable(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite value cannot enter a scientific receipt")
    return value


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def without_timings(value: Any) -> Any:
    value = jsonable(value)
    if isinstance(value, dict):
        return {
            key: without_timings(item) for key, item in value.items()
            if key not in {"total_cpu_ms", "total_wall_ms", "fold_cpu_ms", "correlation_cpu_ms"}
        }
    if isinstance(value, list):
        return [without_timings(item) for item in value]
    return value


def load_reference() -> tuple[dict[str, Any], dict[str, Any]]:
    if digest(REFERENCE_LOCK) != EXPECTED_REFERENCE_LOCK_SHA256:
        raise ValueError("reference-point source lock changed")
    if digest(REFERENCE_RESULT) != EXPECTED_REFERENCE_RESULT_SHA256:
        raise ValueError("reference-point result changed")
    lock = json.loads(REFERENCE_LOCK.read_text())
    result = json.loads(REFERENCE_RESULT.read_text())
    if (
        not result.get("complete") or result.get("status") != "complete"
        or not result.get("source_lock_stable") or result.get("source_lock") != lock
        or result.get("source_lock_sha256") != EXPECTED_REFERENCE_LOCK_SHA256
        or len(lock.get("files", {})) != 79
        or len(lock.get("membership", ())) != 16
        or sum(len(row["pairs"]) * 2 for row in lock["membership"]) != 42
    ):
        raise ValueError("reference-point result is incomplete")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"reference-point frozen source changed: {name}")
    return lock, result


def point_membership(reference_lock: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for receiver_row in reference_lock["membership"]:
        for pair in receiver_row["pairs"]:
            for coordinate in pair["coordinates"]:
                points.append({
                    "case_id": receiver_row["case_id"],
                    "rate_hz": receiver_row["rate_hz"],
                    "edge": receiver_row["edge"],
                    "receiver": receiver_row["receiver"],
                    "category": receiver_row["category"],
                    "pair_inventory_index": pair["pair_inventory_index"],
                    "pair_role": pair["pair_role"],
                    "coordinate": coordinate,
                })
    if len(points) != 42:
        raise ValueError("reference coordinate membership changed")
    return points


def control_cases() -> tuple[Any, ...]:
    cases = tuple(dataset.legacy_controls()) + tuple(dataset.legacy_sequence_occurrences())
    if len(cases) != 42 or any(case.split != "development" for case in cases):
        raise ValueError("legacy control membership changed")
    return cases


def case_token(case: Any, index: int) -> dict[str, Any]:
    return {
        "occurrence_index": index, "case_id": case.id, "rate_hz": case.rate,
        "edge": case.edge, "session_id": case.session, "channel": case.channel,
        "source_counter": case.source_counter, "visit_index": case.visit_index,
        "sequence_id": case.sequence_id, "sequence_index": case.sequence_index,
        "raw_sha256": case.raw_sha256, "activity_policy": case.activity_policy,
        "expected_active": case.expected_active,
    }


def _engine_inventory() -> dict[str, str]:
    engine_lock_path = HERE / "ENGINE_LOCK.json"
    engine_lock = json.loads(engine_lock_path.read_text())
    artifacts = engine_lock.get("artifacts_sha256", engine_lock.get("files", {}))
    if not artifacts:
        raise ValueError("boundary engine lock has no artifact inventory")
    files = {str(engine_lock_path.resolve()): digest(engine_lock_path)}
    for name, expected in artifacts.items():
        path = Path(name)
        if not path.is_absolute():
            path = HERE / path
        if digest(path) != expected:
            raise ValueError(f"boundary engine artifact changed: {path}")
        files[str(path.resolve())] = expected
        if path.name.endswith(".so.build.json"):
            receipt = json.loads(path.read_text())
            if (
                receipt.get("support_guard_hz") != GUARD_TOLERANCE_HZ
                or receipt.get("binary_sha256")
                != digest(HERE / "libtg11_guided_boundary.so")
            ):
                raise ValueError("guided-boundary build receipt is inconsistent")
            for dependency, dependency_hash in receipt.get("sources_sha256", {}).items():
                if digest(dependency) != dependency_hash:
                    raise ValueError(f"guided-boundary build dependency changed: {dependency}")
                files[str(Path(dependency).resolve())] = dependency_hash
    return files


def source_files() -> dict[str, str]:
    reference_lock, _ = load_reference()
    files = dict(reference_lock["files"])
    required = {
        REFERENCE_LOCK, REFERENCE_RESULT,
        REFERENCE / "boundary_api_audit.json",
        HERE / "EVAL_DESIGN.md", HERE / "run_evaluation.py",
        HERE / "test_guided_boundary_evaluation.py",
        TG11 / "libtg11.so",
    }
    missing = [path for path in required if not path.exists()]
    if missing:
        raise ValueError(f"missing guided-boundary evaluation sources: {missing}")
    for path in required:
        name, current = str(path.resolve()), digest(path)
        if name in files and files[name] != current:
            raise ValueError(f"required file differs from inherited pin: {path}")
        files[name] = current
    for name, current in _engine_inventory().items():
        if name in files and files[name] != current:
            raise ValueError(f"boundary engine dependency differs from inherited pin: {name}")
        files[name] = current
    return dict(sorted(files.items()))


def freeze() -> None:
    if SOURCE_LOCK.exists():
        raise ValueError("preserve existing guided-boundary source lock")
    reference_lock, _ = load_reference()
    points = point_membership(reference_lock)
    controls = control_cases()
    payload = {
        "schema": "org.leo.research.native-guided-boundary-source-lock/v1",
        "frozen_before_outcomes": True,
        "files": source_files(),
        "reference_lock_sha256": digest(REFERENCE_LOCK),
        "reference_result_sha256": digest(REFERENCE_RESULT),
        "points": points,
        "points_sha256": stable_hash(points),
        "controls": [case_token(case, index) for index, case in enumerate(controls)],
        "controls_sha256": stable_hash([
            case_token(case, index) for index, case in enumerate(controls)
        ]),
        "config": {
            "methods": ["original", "guard_1e_6hz"],
            "guard_tolerance_hz": GUARD_TOLERANCE_HZ,
            "residual_support_hz": RESIDUAL_SUPPORT_HZ,
            "direct_calls_per_point_per_method": 1,
            "timeout_seconds": TIMEOUT_SECONDS,
            "affinity_cpu": 0,
        },
        "holdout_opened": False,
        "validation_opened": False,
    }
    with SOURCE_LOCK.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def verify_lock() -> dict[str, Any]:
    lock = json.loads(SOURCE_LOCK.read_text())
    reference_lock, _ = load_reference()
    points = point_membership(reference_lock)
    controls = [case_token(case, index) for index, case in enumerate(control_cases())]
    if (
        lock.get("points") != points or lock.get("points_sha256") != stable_hash(points)
        or lock.get("controls") != controls
        or lock.get("controls_sha256") != stable_hash(controls)
        or lock.get("reference_lock_sha256") != digest(REFERENCE_LOCK)
        or lock.get("reference_result_sha256") != digest(REFERENCE_RESULT)
    ):
        raise ValueError("guided-boundary membership changed")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen source changed: {name}")
    return lock


def direct_guided(engine: Any, raw: np.ndarray, point: dict[str, Any]) -> Any:
    coordinate = point["coordinate"]
    return engine.guided(
        raw,
        receiver=int(coordinate["receiver"]),
        probe_index=int(coordinate["probe_index"]),
        predicted_local_epoch_sample=float(coordinate["local_epoch_sample"]),
        scoring_cfo_hz=float(coordinate["acquired_cfo_hz"]),
        expected_physical_cfo_hz=float(coordinate["tracking_cfo_hz"]),
    )


def boundary_classification(point: dict[str, Any]) -> dict[str, Any]:
    coordinate = point["coordinate"]
    difference = abs(float(coordinate["tracking_cfo_hz"]) - float(coordinate["acquired_cfo_hz"]))
    excess = difference - RESIDUAL_SUPPORT_HZ
    return {
        "expected_scoring_difference_hz": difference,
        "excess_over_original_support_hz": excess,
        "inside_new_guard_only": 0.0 < excess <= GUARD_TOLERANCE_HZ,
    }


def compare_direct(original: Any, tolerant: Any, point: dict[str, Any]) -> dict[str, Any]:
    boundary = boundary_classification(point)
    original_science, tolerant_science = without_timings(original), without_timings(tolerant)
    same = original_science == tolerant_science
    return {
        **boundary,
        "ordinary_point": not boundary["inside_new_guard_only"],
        "science_equal_excluding_timings": same,
        "ordinary_parity_passed": same if not boundary["inside_new_guard_only"] else None,
        "boundary_outcome_report_only": boundary["inside_new_guard_only"],
        "original_returned": original is not None,
        "guard_returned": tolerant is not None,
    }


def assess_direct_point(observation: Any, coordinate: dict[str, Any], rate: int) -> dict[str, Any]:
    if observation is None:
        return {
            "accepted": False, "reason": "unsupported", "native_full_gates_passed": False,
            "margin_passed": False, "timing_identity_passed": False,
            "physical_cfo_identity_passed": False,
        }
    value = jsonable(observation)
    period = rate / 750.0
    raw_timing = float(value["dwell_epoch_sample"]) - float(coordinate["dwell_epoch_sample"])
    timing_error = (raw_timing + period / 2) % period - period / 2
    physical_error = float(value["tracking_cfo_hz"]) - float(coordinate["tracking_cfo_hz"])
    full_gates = (
        int(value["status"]) == 0 and bool(value["supported"])
        and bool(value["valid_bounds"]) and int(value["support_frames"]) >= 2
        and bool(value["fractional_complete"])
    )
    margin = float(value["margin"]) >= 0.025
    timing = abs(timing_error) <= rate * 2e-6
    cfo = abs(physical_error) <= 8_000.0
    accepted = full_gates and margin and timing and cfo
    return {
        "accepted": accepted,
        "reason": "accepted" if accepted else "native_or_identity_gate_failed",
        "native_full_gates_passed": full_gates, "margin_passed": margin,
        "timing_error_samples": timing_error, "timing_identity_passed": timing,
        "physical_cfo_error_hz": physical_error, "physical_cfo_identity_passed": cfo,
    }


def pair_assessments(point_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in point_rows:
        key = (
            row["case_id"], row["receiver"], row["pair_inventory_index"], row["pair_role"]
        )
        grouped.setdefault(key, []).append(row)
    output = []
    for key, rows in grouped.items():
        if len(rows) != 2:
            raise ValueError("each frozen reference pair must contain exactly two points")
        rows.sort(key=lambda item: item["coordinate"]["probe_start_sample"])
        methods = {}
        for method in ("original", "guard_1e_6hz"):
            observations = [row["results"][method] for row in rows]
            assessments = [row["assessments"][method] for row in rows]
            if any(item is None for item in observations):
                pair_contract = False
            else:
                first, second = observations
                pair_contract = (
                    int(first["receiver"]) == int(second["receiver"]) == int(key[1])
                    and int(second["probe_start_sample"]) - int(first["probe_start_sample"])
                    >= int(rows[0]["rate_hz"]) // 50
                    and abs(float(second["tracking_cfo_hz"]) - float(first["tracking_cfo_hz"]))
                    <= 8_000.0
                )
            methods[method] = {
                "accepted": pair_contract and all(item["accepted"] for item in assessments),
                "pair_contract_passed": pair_contract,
                "point_assessments": assessments,
            }
        output.append({
            "case_id": key[0], "receiver": key[1], "pair_inventory_index": key[2],
            "pair_role": key[3], "methods": methods,
        })
    return output


def timed(call: Callable[[], Any]) -> tuple[Any, dict[str, float]]:
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    value = call()
    return value, {
        "cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def control_call(detector: Any, raw: np.ndarray, case: Any) -> tuple[Any, Any]:
    visit_index = case.sequence_index if case.sequence_index is not None else case.visit_index or 0
    return tuple(detector.process(
        raw, tradeoff.make_key(case, receiver), start_counter=case.source_counter,
        visit_index=int(visit_index), force_discovery=False,
    ) for receiver in (0, 1))  # type: ignore[return-value]


def assess_control(decisions: tuple[Any, Any], case: Any) -> list[dict[str, Any]]:
    return [jsonable(dataset.assess_receiver(
        decisions[receiver], (), case, receiver, profile="native_diverse"
    )) for receiver in (0, 1)]


def _control_science(value: Any) -> Any:
    return without_timings(value)


def run() -> None:
    if RESULT.exists():
        raise ValueError("preserve existing guided-boundary result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread counts must equal one")
    lock = verify_lock()
    cases_by_id = {case.id: case for case in dataset.real_prefix_cases()}
    controls = control_cases()
    selected_ids = {point["case_id"] for point in lock["points"]}
    selected_ids.update(case.id for case in controls)
    all_cases = {**cases_by_id, **{case.id: case for case in controls}}
    if any(all_cases[case_id].split != "development" for case_id in selected_ids):
        raise ValueError("only frozen development IQ may be opened")
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("CPU 0 unavailable")
    point_rows: list[dict[str, Any]] = []
    control_rows: list[dict[str, Any]] = []
    status, error = "complete", None
    started = time.perf_counter()
    previous_handler = signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("120 second guided-boundary bound")),
    )
    signal.alarm(TIMEOUT_SECONDS)
    try:
        raw_by_id = {case_id: dataset.load_iq(all_cases[case_id]) for case_id in selected_ids}
        input_hashes = {case_id: hashlib.sha256(raw).hexdigest()
                        for case_id, raw in raw_by_id.items()}
        os.sched_setaffinity(0, {0})
        engine_type = boundary_engine_class()
        geometries = sorted({(all_cases[case_id].rate, all_cases[case_id].edge)
                             for case_id in selected_ids})
        with ExitStack() as stack:
            original = {geometry: stack.enter_context(
                NativeTG11(*geometry, library=TG11 / "libtg11.so")
            ) for geometry in geometries}
            tolerant = {geometry: stack.enter_context(engine_type(*geometry))
                        for geometry in geometries}
            engines = {"original": original, "guard_1e_6hz": tolerant}
            point_counter = 0
            for point in lock["points"]:
                case, raw = all_cases[point["case_id"]], raw_by_id[point["case_id"]]
                order = ("original", "guard_1e_6hz") if point_counter % 2 == 0 else ("guard_1e_6hz", "original")
                point_counter += 1
                results, timings = {}, {}
                for method in order:
                    results[method], timings[method] = timed(
                        lambda method=method: direct_guided(engines[method][(case.rate, case.edge)], raw, point)
                    )
                point_rows.append({
                    **point, "method_order": list(order),
                    "results": {name: jsonable(value) for name, value in results.items()},
                    "timings": timings,
                    "assessments": {
                        method: assess_direct_point(results[method], point["coordinate"], case.rate)
                        for method in ("original", "guard_1e_6hz")
                    },
                    "comparison": compare_direct(results["original"], results["guard_1e_6hz"], point),
                })

            detectors = {
                method: {geometry: NativeTradeoffDetector(engine)
                         for geometry, engine in by_geometry.items()}
                for method, by_geometry in engines.items()
            }
            for index, case in enumerate(controls):
                raw = raw_by_id[case.id]
                order = ("original", "guard_1e_6hz") if index % 2 == 0 else ("guard_1e_6hz", "original")
                outputs, timings, assessments = {}, {}, {}
                for method in order:
                    outputs[method], timings[method] = timed(
                        lambda method=method: control_call(detectors[method][(case.rate, case.edge)], raw, case)
                    )
                    assessments[method] = assess_control(outputs[method], case)
                control_rows.append({
                    **case_token(case, index), "method_order": list(order),
                    "outputs": {name: jsonable(value) for name, value in outputs.items()},
                    "timings": timings, "assessments": assessments,
                    "science_equal_excluding_timings": (
                        _control_science(outputs["original"])
                        == _control_science(outputs["guard_1e_6hz"])
                    ),
                })
        for case_id, raw in raw_by_id.items():
            if hashlib.sha256(raw).hexdigest() != input_hashes[case_id]:
                raise ValueError(f"input mutated: {case_id}")
    except BaseException as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        os.sched_setaffinity(0, affinity)

    stable = all(digest(name) == expected for name, expected in lock["files"].items())
    ordinary_parity = all(
        row["comparison"]["ordinary_parity_passed"] is not False for row in point_rows
    )
    truth_gates = {
        method: all(item["activity_policy_passed"] is True
                    for row in control_rows for item in row["assessments"][method])
        for method in ("original", "guard_1e_6hz")
    }
    complete = (
        status == "complete" and stable and len(point_rows) == 42 and len(control_rows) == 42
    )
    direct_pairs = pair_assessments(point_rows) if len(point_rows) == 42 else []
    payload = {
        "schema": "org.leo.research.native-guided-boundary-result/v1",
        "status": status, "error": error, "complete": complete,
        "source_lock": lock, "source_lock_sha256": digest(SOURCE_LOCK),
        "source_lock_stable": stable, "thread_environment": environment,
        "affinity_cpu": 0, "affinity_restored": os.sched_getaffinity(0) == affinity,
        "point_rows": point_rows, "direct_pair_assessments": direct_pairs,
        "control_rows": control_rows,
        "summary": {
            "ordinary_point_parity_passed": ordinary_parity,
            "boundary_point_count": sum(row["comparison"]["inside_new_guard_only"] for row in point_rows),
            "control_truth_gates": truth_gates,
            "api_numerical_fix_only": True,
            "boundary_outcomes_are_report_only": True,
        },
        "holdout_opened": False, "validation_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    with RESULT.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if not complete:
        raise RuntimeError(error or "guided-boundary integrity failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--freeze", action="store_true")
    actions.add_argument("--run", action="store_true")
    args = parser.parse_args()
    freeze() if args.freeze else run()


if __name__ == "__main__":
    main()
