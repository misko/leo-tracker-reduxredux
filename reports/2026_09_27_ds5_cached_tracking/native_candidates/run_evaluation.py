"""Frozen staged evaluation for one- and two-candidate native detection.

This runner owns only orchestration and receipts.  It reuses the frozen native
tradeoff controller, corpus adapter, comparator, and assessment helpers.  One
common source lock is created before any outcome stage, and later stages require
complete integrity receipts without treating quality failures as stop gates.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import statistics
import sys
import time
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
TG11 = REPORT / "tg11"
TRADEOFF = REPORT / "native_tradeoff"
sys.path[:0] = [str(ROOT / "src"), str(HERE), str(TG11), str(TRADEOFF)]

import numpy as np  # noqa: E402

import leo  # noqa: E402
import leo.analysis.starlink.acquisition as acquisition  # noqa: E402

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("native candidate evaluation must use this checkout")


def _load_common() -> Any:
    path = TRADEOFF / "run_evaluation.py"
    spec = importlib.util.spec_from_file_location(
        "native_candidates_frozen_tradeoff_runner", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen native tradeoff helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


common = _load_common()
dataset = common.dataset

from native_candidates import NativeCandidates  # noqa: E402
from native_engine import NativeTG11  # noqa: E402
from native_tradeoff_detector import NativeTradeoffDetector  # noqa: E402


STAGES = ("controls", "diagnostic", "real")
NATIVE_METHODS = ("native_k1_blind", "native_k2_blind", "native_k2_tracked")
METHODS = {
    "controls": NATIVE_METHODS,
    "diagnostic": ("application",) + NATIVE_METHODS,
    "real": ("application",) + NATIVE_METHODS,
}
TIMEOUT_SECONDS = {"controls": 120, "diagnostic": 300, "real": 300}
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
SOURCE_LOCK = HERE / "source_lock.json"


def digest(path: str | Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


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
    encoded = json.dumps(
        jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def cases_for_stage(stage: str) -> tuple[Any, ...]:
    cases = tuple(common.cases_for_stage(stage))
    expected = {"controls": 42, "diagnostic": 26, "real": 64}[stage]
    if len(cases) != expected or any(case.split != "development" for case in cases):
        raise ValueError(f"invalid {stage} development membership")
    return cases


def membership(cases: tuple[Any, ...]) -> str:
    return stable_hash([
        {
            "id": case.id,
            "rate": case.rate,
            "edge": case.edge,
            "channel": case.channel,
            "session": case.session,
            "source_counter": case.source_counter,
            "raw_sha256": case.raw_sha256,
        }
        for case in cases
    ])


def result_path(stage: str) -> Path:
    return HERE / f"results.{stage}.json"


def rotated_methods(stage: str, case_index: int) -> tuple[str, ...]:
    methods = METHODS[stage]
    offset = case_index % len(methods)
    return methods[offset:] + methods[:offset]


def _candidate_build_inventory() -> dict[str, str]:
    paths = {
        HERE / "native_candidates.py",
        HERE / "candidates_native.c",
        HERE / "candidates_native.h",
    }
    for budget in (1, 2):
        binary = HERE / f"libtg11_candidates_k{budget}.so"
        receipt_path = binary.with_name(binary.name + ".build.json")
        if not binary.exists() or not receipt_path.exists():
            raise ValueError(f"missing K{budget} native candidate build")
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("binary_sha256") != digest(binary):
            raise ValueError(f"K{budget} binary differs from build receipt")
        recorded_budget = receipt.get("candidate_budget", receipt.get("maximum_candidates"))
        if recorded_budget is not None and recorded_budget != budget:
            raise ValueError(f"K{budget} build receipt has wrong candidate budget")
        for name, expected in receipt.get("sources_sha256", {}).items():
            path = Path(name)
            if digest(path) != expected:
                raise ValueError(f"K{budget} dependency changed: {path}")
            paths.add(path)
        paths.update((binary, receipt_path))
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise ValueError(f"missing native candidate sources: {missing}")
    engine_lock_path = HERE / "ENGINE_LOCK.json"
    engine_lock = json.loads(engine_lock_path.read_text())
    for relative, expected in engine_lock.get("artifacts_sha256", {}).items():
        path = HERE / relative
        if digest(path) != expected:
            raise ValueError(f"engine-lock artifact changed: {path}")
        paths.add(path)
    paths.add(engine_lock_path)
    return {str(path.resolve()): digest(path) for path in sorted(paths)}


def source_files() -> dict[str, str]:
    files = dict(common.source_files())
    required = {
        HERE / "EVAL_DESIGN.md",
        HERE / "ENGINE.md",
        HERE / "run_evaluation.py",
        HERE / "test_candidate_evaluation.py",
        HERE / "test_original_candidate_regression.py",
    }
    missing = [path for path in required if not path.exists()]
    if missing:
        raise ValueError(f"missing native candidate evaluation sources: {missing}")
    files.update({str(path.resolve()): digest(path) for path in required})
    files.update(_candidate_build_inventory())
    return dict(sorted(files.items()))


def freeze() -> None:
    if SOURCE_LOCK.exists():
        raise ValueError("preserve existing common source lock")
    stages = {
        stage: {
            "case_ids": [case.id for case in cases_for_stage(stage)],
            "membership_sha256": membership(cases_for_stage(stage)),
            "methods": list(METHODS[stage]),
            "timeout_seconds": TIMEOUT_SECONDS[stage],
        }
        for stage in STAGES
    }
    all_cases = tuple(case for stage in STAGES for case in cases_for_stage(stage))
    if len(all_cases) != 132 or len({case.id for case in all_cases}) != 132:
        raise ValueError("candidate evaluation membership must contain 132 unique cases")
    payload = {
        "schema": "org.leo.research.native-candidates-source-lock/v1",
        "frozen_before_any_outcomes": True,
        "files": source_files(),
        "stages": stages,
        "adapter_membership_sha256": dataset.membership_sha256(),
        "application_native_backend": acquisition._folded_anchor_score_grid_backend(),
        "stage_order": list(STAGES),
        "holdout_opened": False,
        "validation_opened": False,
    }
    with SOURCE_LOCK.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def verify_lock(stage: str, cases: tuple[Any, ...]) -> dict[str, Any]:
    lock = json.loads(SOURCE_LOCK.read_text())
    if lock.get("stage_order") != list(STAGES):
        raise ValueError("invalid native candidate stage order")
    expected = lock["stages"][stage]
    if (
        expected["case_ids"] != [case.id for case in cases]
        or expected["membership_sha256"] != membership(cases)
        or expected["methods"] != list(METHODS[stage])
        or expected["timeout_seconds"] != TIMEOUT_SECONDS[stage]
    ):
        raise ValueError(f"{stage} configuration differs from common source lock")
    if lock["adapter_membership_sha256"] != dataset.membership_sha256():
        raise ValueError("adapter membership changed")
    for name, expected_hash in lock["files"].items():
        if digest(name) != expected_hash:
            raise ValueError(f"frozen source changed: {name}")
    return lock


def predecessor_receipts(stage: str, lock: dict[str, Any]) -> list[dict[str, Any]]:
    prior_stages = STAGES[: STAGES.index(stage)]
    output = []
    for prior_stage in prior_stages:
        path = result_path(prior_stage)
        if not path.exists():
            raise ValueError(f"complete {prior_stage} receipt is required")
        payload = json.loads(path.read_text())
        expected_cases = len(lock["stages"][prior_stage]["case_ids"])
        if (
            not payload.get("complete")
            or payload.get("status") != "complete"
            or payload.get("source_lock") != lock
            or payload.get("source_lock_sha256") != digest(SOURCE_LOCK)
            or not payload.get("source_lock_stable")
            or len(payload.get("rows", ())) != expected_cases
        ):
            raise ValueError(f"{prior_stage} integrity receipt is incomplete")
        output.append({
            "stage": prior_stage,
            "path": str(path.resolve()),
            "sha256": digest(path),
            "quality_was_not_a_stage_gate": True,
        })
    return output


class RecordingEngine:
    """Reference-only capture of native calls made inside a timed controller call."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.events: list[tuple[Any, ...]] = []

    def reset(self) -> None:
        self.events.clear()

    def screen(self, raw: Any, *, receiver: int) -> Any:
        result = self.engine.screen(raw, receiver=receiver)
        self.events.append(("screen", result))
        return result

    def blind(self, raw: Any, *, receiver: int, screen: Any) -> tuple[Any, ...]:
        result = self.engine.blind(raw, receiver=receiver, screen=screen)
        self.events.append(("blind", receiver, result))
        return result

    def guided(
        self,
        raw: Any,
        *,
        receiver: int,
        probe_index: int,
        predicted_local_epoch_sample: float,
        scoring_cfo_hz: float,
        expected_physical_cfo_hz: float,
    ) -> Any:
        result = self.engine.guided(
            raw,
            receiver=receiver,
            probe_index=probe_index,
            predicted_local_epoch_sample=predicted_local_epoch_sample,
            scoring_cfo_hz=scoring_cfo_hz,
            expected_physical_cfo_hz=expected_physical_cfo_hz,
        )
        self.events.append((
            "guided",
            receiver,
            probe_index,
            predicted_local_epoch_sample,
            scoring_cfo_hz,
            expected_physical_cfo_hz,
            result,
        ))
        return result

    def serialize(self) -> list[dict[str, Any]]:
        output = []
        for event in self.events:
            if event[0] == "screen":
                screen = event[1]
                output.append({
                    "kind": "screen",
                    "receiver": screen.receiver,
                    "windows": jsonable(screen.windows),
                    "selected_projection": screen.selected_projection,
                    "projection_contrast": jsonable(screen.projection_contrast),
                    "fold_cpu_ms": screen.fold_cpu_ms,
                    "correlation_cpu_ms": screen.correlation_cpu_ms,
                    "total_cpu_ms": screen.total_cpu_ms,
                    "total_wall_ms": screen.total_wall_ms,
                })
            elif event[0] == "blind":
                output.append({
                    "kind": "blind",
                    "receiver": event[1],
                    "observations": jsonable(event[2]),
                })
            else:
                output.append({
                    "kind": "guided",
                    "receiver": event[1],
                    "probe_index": event[2],
                    "predicted_local_epoch_sample": event[3],
                    "scoring_cfo_hz": event[4],
                    "expected_physical_cfo_hz": event[5],
                    "observation": jsonable(event[6]),
                })
        return output


def sources_stable(lock: dict[str, Any]) -> bool:
    try:
        return all(digest(name) == expected for name, expected in lock["files"].items())
    except (OSError, ValueError):
        return False


def native_call(
    detector: NativeTradeoffDetector,
    raw: np.ndarray,
    case: Any,
    *,
    force_discovery: bool,
) -> tuple[Any, Any]:
    return common.native_call(
        detector, raw, case, force_discovery=force_discovery
    )


def timed(function: Callable[[], Any]) -> tuple[Any, dict[str, float]]:
    cpu = time.process_time_ns()
    wall = time.perf_counter_ns()
    result = function()
    return result, {
        "process_cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def _matched(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("matched", value.get("passed", False)))
    return bool(getattr(value, "matched", getattr(value, "passed", False)))


def assess_methods(
    outputs: dict[str, Any], reference: tuple[Any, ...], case: Any
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    assessments = {
        method: common.assess_native(outputs[method], reference, case)
        for method in NATIVE_METHODS
    }
    visits: dict[str, Any] = {}
    for method, rows in assessments.items():
        reference_active = any(item["reference_active"] for item in rows)
        candidate_active = any(item["candidate_active"] for item in rows)
        matched = any(item["matched_reference"] for item in rows)
        visits[method] = {
            "reference_active": reference_active,
            "candidate_active": candidate_active,
            "matched_reference": matched,
            "lost_reference_visit": reference_active and not matched,
            "additional_or_mismatched_visit": candidate_active and not matched,
        }
    comparisons = []
    for receiver in (0, 1):
        k1 = assessments["native_k1_blind"][receiver]
        k2 = assessments["native_k2_blind"][receiver]
        tracked = assessments["native_k2_tracked"][receiver]
        k1_pair = getattr(outputs["native_k1_blind"][receiver], "pair", None)
        k2_pair = getattr(outputs["native_k2_blind"][receiver], "pair", None)
        k2_to_k1 = dataset.associate_pair_to_reference(
            outputs["native_k2_blind"][receiver],
            () if k1_pair is None else (k1_pair,),
            case,
            receiver,
        )
        tracked_to_k2 = dataset.associate_pair_to_reference(
            outputs["native_k2_tracked"][receiver],
            () if k2_pair is None else (k2_pair,),
            case,
            receiver,
        )
        comparisons.append({
            "receiver": receiver,
            "k1_k2_same_activity": k1["candidate_active"] == k2["candidate_active"],
            "k2_associates_to_k1": (
                not k1["candidate_active"] and not k2["candidate_active"]
            ) or _matched(k2_to_k1),
            "k2_to_k1_association": jsonable(k2_to_k1),
            "k2_tracked_same_activity": (
                k2["candidate_active"] == tracked["candidate_active"]
            ),
            "k2_tracked_associates_to_blind": (
                not k2["candidate_active"] and not tracked["candidate_active"]
            ) or _matched(tracked_to_k2),
            "k2_tracked_to_blind_association": jsonable(tracked_to_k2),
        })
    return assessments, visits, comparisons


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "values_ms": []}
    return {
        "count": len(values),
        "sum_ms": sum(values),
        "minimum_ms": min(values),
        "median_ms": statistics.median(values),
        "maximum_ms": max(values),
        "below_120ms_count": sum(value < 120.0 for value in values),
        "below_120ms_fraction": sum(value < 120.0 for value in values) / len(values),
        "values_ms": values,
    }


def _quality(method: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    assessments = [item for row in rows for item in row["native_assessments"][method]]
    visits = [row["visit_assessments"][method] for row in rows]
    decisions = [item for row in rows for item in row["outputs"][method]]
    reference = sum(item["reference_active"] for item in assessments)
    matched = sum(item["matched_reference"] for item in assessments)
    lost = sum(item["lost_reference"] for item in assessments)
    outcomes: dict[str, int] = {}
    policy = {"passed": 0, "failed": 0, "report_only": 0}
    for item in assessments:
        outcome = str(item["physical_outcome"])
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        value = item["activity_policy_passed"]
        policy["passed" if value is True else "failed" if value is False else "report_only"] += 1
    return {
        "receiver_rows": len(assessments),
        "reference_positive_receivers": reference,
        "matched_reference_receivers": matched,
        "lost_reference_receivers": lost,
        "additional_or_mismatched_active_receivers": sum(
            item["additional_or_mismatched"] for item in assessments
        ),
        "candidate_active_receivers": sum(item["candidate_active"] for item in assessments),
        "reference_positive_visits": sum(item["reference_active"] for item in visits),
        "matched_reference_visits": sum(item["matched_reference"] for item in visits),
        "lost_reference_visits": sum(item["lost_reference_visit"] for item in visits),
        "additional_or_mismatched_active_visits": sum(
            item["additional_or_mismatched_visit"] for item in visits
        ),
        "physical_outcomes": outcomes,
        "required_policy_passed_receivers": policy["passed"],
        "required_policy_failed_receivers": policy["failed"],
        "report_only_receivers": policy["report_only"],
        "miss_band": common._loss_band(lost, reference),
        "work_counts": {
            name: sum(int(decision[name]) for decision in decisions)
            for name in (
                "screened_probe_count",
                "guided_probe_count",
                "blind_probe_count",
                "proposal_count",
                "scoring_count",
            )
        },
    }


def summarize(stage: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"by_rate": {}, "route_counts": {}}
    for rate in sorted({row["rate_hz"] for row in rows}):
        selected = [row for row in rows if row["rate_hz"] == rate]
        methods = {
            method: {
                "process_cpu": _distribution([
                    row["timings"][method]["process_cpu_ms"] for row in selected
                ]),
                "wall": _distribution([
                    row["timings"][method]["wall_ms"] for row in selected
                ]),
            }
            for method in METHODS[stage]
        }
        if "application" in methods:
            application_cpu = methods["application"]["process_cpu"]["sum_ms"]
            for method in NATIVE_METHODS:
                candidate_cpu = methods[method]["process_cpu"]["sum_ms"]
                methods[method]["aggregate_cpu_speedup_vs_application"] = (
                    application_cpu / candidate_cpu if candidate_cpu else None
                )
        comparisons = [item for row in selected for item in row["candidate_comparisons"]]
        summary["by_rate"][str(rate)] = {
            "case_count": len(selected),
            "methods": methods,
            "quality": {method: _quality(method, selected) for method in NATIVE_METHODS},
            "candidate_comparisons": {
                "receiver_rows": len(comparisons),
                "k1_k2_same_activity": sum(item["k1_k2_same_activity"] for item in comparisons),
                "k2_associates_to_k1": sum(item["k2_associates_to_k1"] for item in comparisons),
                "k2_tracked_same_activity": sum(
                    item["k2_tracked_same_activity"] for item in comparisons
                ),
                "k2_tracked_associates_to_blind": sum(
                    item["k2_tracked_associates_to_blind"] for item in comparisons
                ),
            },
        }
    for row in rows:
        for method in NATIVE_METHODS:
            for decision in row["outputs"][method]:
                key = f"{method}:{decision['route']}"
                summary["route_counts"][key] = summary["route_counts"].get(key, 0) + 1
    return summary


def execute_stage(stage: str) -> None:
    output = result_path(stage)
    if output.exists():
        raise ValueError(f"preserve existing {stage} result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread counts must equal one before launch")
    cases = cases_for_stage(stage)
    lock = verify_lock(stage, cases)
    lock_sha256 = digest(SOURCE_LOCK)
    prior = predecessor_receipts(stage, lock)
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    rows: list[dict[str, Any]] = []
    status, error = "complete", None
    started = time.perf_counter()
    previous_handler = signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(
            TimeoutError(f"{TIMEOUT_SECONDS[stage]} second {stage} bound")
        ),
    )
    signal.alarm(TIMEOUT_SECONDS[stage])
    try:
        raw_by_id = {case.id: dataset.load_iq(case) for case in cases}
        input_hashes = {
            case.id: hashlib.sha256(raw_by_id[case.id]).hexdigest() for case in cases
        }
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            geometries = sorted({(case.rate, case.edge) for case in cases})
            k1_engines = {
                geometry: stack.enter_context(
                    NativeTG11(*geometry, library=TG11 / "libtg11.so")
                )
                for geometry in geometries
            }
            k2_engines = {
                geometry: stack.enter_context(
                    NativeCandidates(
                        *geometry,
                        candidate_budget=2,
                        library=HERE / "libtg11_candidates_k2.so",
                    )
                )
                for geometry in geometries
            }
            recorders = {
                "native_k1_blind": {
                    geometry: RecordingEngine(engine)
                    for geometry, engine in k1_engines.items()
                },
                "native_k2_blind": {
                    geometry: RecordingEngine(engine)
                    for geometry, engine in k2_engines.items()
                },
                "native_k2_tracked": {
                    geometry: RecordingEngine(engine)
                    for geometry, engine in k2_engines.items()
                },
            }
            detectors = {
                method: {
                    geometry: NativeTradeoffDetector(recorder)
                    for geometry, recorder in by_geometry.items()
                }
                for method, by_geometry in recorders.items()
            }
            for case_index, case in enumerate(cases):
                raw = raw_by_id[case.id]
                method_order = rotated_methods(stage, case_index)
                outputs: dict[str, Any] = {}
                timings: dict[str, Any] = {}
                engine_calls: dict[str, Any] = {}
                for method in method_order:
                    geometry = case.rate, case.edge
                    if method == "application":
                        value, timing = timed(
                            lambda raw=raw, case=case: common.application_call(raw, case)
                        )
                    else:
                        detector = detectors[method][geometry]
                        recorder = recorders[method][geometry]
                        recorder.reset()
                        value, timing = timed(
                            lambda detector=detector, raw=raw, case=case, method=method: native_call(
                                detector,
                                raw,
                                case,
                                force_discovery=method != "native_k2_tracked",
                            )
                        )
                        engine_calls[method] = recorder.serialize()
                    outputs[method] = value
                    timings[method] = timing
                if hashlib.sha256(raw).hexdigest() != input_hashes[case.id]:
                    raise ValueError(f"detector mutated input: {case.id}")
                reference = (
                    common.application_inventory(outputs["application"], case)
                    if "application" in outputs
                    else ()
                )
                assessments, visits, comparisons = assess_methods(outputs, reference, case)
                row = {
                    "case_id": case.id,
                    "origin": case.origin,
                    "cohort": case.cohort,
                    "rate_hz": case.rate,
                    "edge": case.edge,
                    "channel": case.channel,
                    "session_id": case.session,
                    "visit_index": case.visit_index,
                    "source_counter": case.source_counter,
                    "sequence_id": case.sequence_id,
                    "sequence_index": case.sequence_index,
                    "raw_sha256": case.raw_sha256,
                    "input_array_sha256": input_hashes[case.id],
                    "input_immutable": True,
                    "truth": jsonable(case.receivers),
                    "activity_policy": case.activity_policy,
                    "expected_active": case.expected_active,
                    "method_order": list(method_order),
                    "timings": timings,
                    "outputs": {name: jsonable(value) for name, value in outputs.items()},
                    "engine_calls": engine_calls,
                    "output_sha256": {name: stable_hash(value) for name, value in outputs.items()},
                    "application_pair_inventory": jsonable(reference),
                    "application_truth_assessments": (
                        common.assess_application_truth(reference, case)
                        if "application" in outputs
                        else []
                    ),
                    "native_assessments": assessments,
                    "visit_assessments": visits,
                    "candidate_comparisons": comparisons,
                }
                rows.append(row)
                print(json.dumps({
                    "stage": stage,
                    "case": case.id,
                    "complete_cases": len(rows),
                    "timings_ms": timings,
                }), flush=True)
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        os.sched_setaffinity(0, affinity)
    source_stable = sources_stable(lock) and digest(SOURCE_LOCK) == lock_sha256
    complete = status == "complete" and len(rows) == len(cases) and source_stable
    payload = {
        "schema": "org.leo.research.native-candidates-evaluation/v1",
        "stage": stage,
        "status": status,
        "error": error,
        "complete": complete,
        "source_lock": lock,
        "source_lock_sha256": lock_sha256,
        "source_lock_stable": source_stable,
        "prior_complete_receipts": prior,
        "thread_environment": environment,
        "affinity_cpu": 0,
        "affinity_restored": sorted(affinity),
        "timeout_seconds": TIMEOUT_SECONDS[stage],
        "rows": rows,
        "summary": summarize(stage, rows),
        "quality_failures_are_report_only": True,
        "holdout_opened": False,
        "validation_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({
        "stage": stage,
        "status": status,
        "complete": complete,
        "cases": len(rows),
    }), flush=True)


def main() -> None:
    args = sys.argv[1:]
    if args == ["--freeze"]:
        freeze()
        return
    if len(args) == 2 and args[0] == "--stage" and args[1] in STAGES:
        execute_stage(args[1])
        return
    raise ValueError(
        "usage: run_evaluation.py --freeze | --stage controls|diagnostic|real"
    )


if __name__ == "__main__":
    main()
