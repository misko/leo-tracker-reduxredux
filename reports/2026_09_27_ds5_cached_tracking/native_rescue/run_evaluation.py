"""Frozen staged evaluation of one same-receiver rescue acquisition."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import fields, is_dataclass, replace
from enum import Enum
import hashlib
import importlib
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
CANDIDATES = REPORT / "native_candidates"
BOUNDARY = REPORT / "native_guided_boundary"
CANDIDATE_LOCK = CANDIDATES / "source_lock.json"
BOUNDARY_LOCK = BOUNDARY / "source_lock.json"
BOUNDARY_RESULT = BOUNDARY / "results.json"
EXPECTED_CANDIDATE_LOCK = "3c49f0e0f65659d500162fb57739498221fe0d481e4f2bfc65860847163796de"
EXPECTED_BOUNDARY_LOCK = "de43a9500bf40ba36f77d0150eb4e42f89069432c531f03659a7872588943f7b"
EXPECTED_BOUNDARY_RESULT = "a8cbd047d7185dda1056dcf798db0597937d33f8e4752d8d4bafcc0c0099664a"
SOURCE_LOCK = HERE / "source_lock.json"
STAGES = ("controls", "diagnostic", "real")
METHODS = {
    "controls": ("native_tracked", "native_rescue"),
    "diagnostic": ("application", "native_tracked", "native_rescue"),
    "real": ("application", "native_tracked", "native_rescue"),
}
TIMEOUT_SECONDS = {"controls": 120, "diagnostic": 120, "real": 300}
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)

sys.path[:0] = [str(ROOT / "src"), str(HERE), str(TG11), str(TRADEOFF), str(BOUNDARY)]

import numpy as np  # noqa: E402
import leo  # noqa: E402
from native_guided_boundary import NativeGuidedBoundary  # noqa: E402
from native_tradeoff_detector import NativeTradeoffDetector  # noqa: E402

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("native rescue evaluation must use this checkout")


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


candidate_common = _load_module(
    "native_rescue_frozen_candidate_runner", CANDIDATES / "run_evaluation.py"
)
common = candidate_common.common
dataset = candidate_common.dataset


def rescue_detector_class() -> type:
    return importlib.import_module("native_rescue_detector").SameRxRescueDetector


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


def cases_for_stage(stage: str) -> tuple[Any, ...]:
    cases = tuple(candidate_common.cases_for_stage(stage))
    expected = {"controls": 42, "diagnostic": 26, "real": 64}[stage]
    if len(cases) != expected or any(case.split != "development" for case in cases):
        raise ValueError(f"invalid {stage} development membership")
    return cases


def supplemental_negative_parents() -> tuple[Any, ...]:
    cases = tuple(
        case for case in dataset.legacy_controls()
        if case.sequence_id is None
        and case.activity_policy == "required_inactive"
        and case.expected_active is False
        and all(receiver.constructed_negative and not receiver.pilots
                for receiver in case.receivers)
    )
    cohorts = [case.cohort for case in cases]
    # The source IDs, rather than an outcome, distinguish the six white-noise
    # and six tone parents in the frozen legacy corpus.
    noise = sum("noise" in case.id for case in cases)
    tone = sum("tone" in case.id for case in cases)
    if (len(cases) != 12 or {rate: sum(case.rate == rate for case in cases)
                             for rate in (2_500_000, 5_000_000)}
            != {2_500_000: 6, 5_000_000: 6} or noise != 6 or tone != 6):
        raise ValueError(f"mirrored-negative membership changed: {len(cases)}, {noise}, {tone}, {cohorts}")
    return cases


def supplemental_descriptor(case: Any) -> dict[str, Any]:
    return {
        "id": case.id + "::rxswap-v1", "parent_case_id": case.id,
        "parent_raw_npy_sha256": case.raw_sha256,
        "receiver_permutation": [1, 0], "rate_hz": case.rate,
        "edge": case.edge, "channel": case.channel,
        "derived_tuning_identity": case.tuning_identity + "::rxswap-v1",
        "derived_session": case.session + "::rxswap-v1",
        "receiver_truth_permutation": [1, 0],
    }


def swapped_case(case: Any, payload_sha256: str) -> Any:
    receivers = (
        replace(case.receivers[1], receiver=0),
        replace(case.receivers[0], receiver=1),
    )
    return replace(
        case, id=case.id + "::rxswap-v1", session=case.session + "::rxswap-v1",
        tuning_identity=case.tuning_identity + "::rxswap-v1",
        raw_sha256="sha256:" + payload_sha256, receivers=receivers,
    )


def membership(cases: tuple[Any, ...]) -> str:
    return stable_hash([{
        "occurrence": index, "case_id": case.id, "rate_hz": case.rate,
        "edge": case.edge, "channel": case.channel, "session": case.session,
        "source_counter": case.source_counter, "visit_index": case.visit_index,
        "sequence_id": case.sequence_id, "sequence_index": case.sequence_index,
        "raw_sha256": case.raw_sha256,
    } for index, case in enumerate(cases)])


def result_path(stage: str) -> Path:
    return HERE / f"results.{stage}.json"


def rotated_methods(stage: str, index: int) -> tuple[str, ...]:
    methods = METHODS[stage]
    offset = index % len(methods)
    return methods[offset:] + methods[:offset]


def _load_inherited() -> dict[str, str]:
    if digest(CANDIDATE_LOCK) != EXPECTED_CANDIDATE_LOCK:
        raise ValueError("native-candidate source lock changed")
    if digest(BOUNDARY_LOCK) != EXPECTED_BOUNDARY_LOCK:
        raise ValueError("guided-boundary source lock changed")
    if digest(BOUNDARY_RESULT) != EXPECTED_BOUNDARY_RESULT:
        raise ValueError("guided-boundary qualification result changed")
    candidate = json.loads(CANDIDATE_LOCK.read_text())
    boundary = json.loads(BOUNDARY_LOCK.read_text())
    result = json.loads(BOUNDARY_RESULT.read_text())
    if (len(candidate.get("files", {})) != 74 or len(boundary.get("files", {})) != 93
            or not result.get("complete") or not result.get("source_lock_stable")
            or result.get("source_lock") != boundary):
        raise ValueError("inherited qualification is incomplete")
    files: dict[str, str] = {}
    for inherited in (candidate["files"], boundary["files"]):
        for name, expected in inherited.items():
            if digest(name) != expected:
                raise ValueError(f"inherited frozen source changed: {name}")
            if name in files and files[name] != expected:
                raise ValueError(f"inherited source locks disagree: {name}")
            files[name] = expected
    return files


def _rescue_inventory() -> dict[str, str]:
    engine_lock_path = HERE / "ENGINE_LOCK.json"
    lock = json.loads(engine_lock_path.read_text())
    artifacts = lock.get("artifacts_sha256", lock.get("files", {}))
    if not artifacts:
        raise ValueError("rescue engine lock has no artifact inventory")
    files = {str(engine_lock_path.resolve()): digest(engine_lock_path)}
    for name, expected in artifacts.items():
        path = Path(name)
        if not path.is_absolute():
            path = HERE / path
        if digest(path) != expected:
            raise ValueError(f"rescue engine artifact changed: {path}")
        files[str(path.resolve())] = expected
    return files


def source_files() -> dict[str, str]:
    files = _load_inherited()
    required = {
        HERE / "DESIGN.md", HERE / "DESIGN_REVIEW.md",
        HERE / "run_evaluation.py", HERE / "test_run_evaluation.py",
        CANDIDATE_LOCK, BOUNDARY_LOCK, BOUNDARY_RESULT,
    }
    missing = [path for path in required if not path.exists()]
    if missing:
        raise ValueError(f"missing rescue evaluation sources: {missing}")
    additions = {str(path.resolve()): digest(path) for path in required}
    additions.update(_rescue_inventory())
    for name, expected in additions.items():
        if name in files and files[name] != expected:
            raise ValueError(f"rescue dependency differs from inherited pin: {name}")
        files[name] = expected
    return dict(sorted(files.items()))


def freeze() -> None:
    if SOURCE_LOCK.exists():
        raise ValueError("preserve existing native-rescue source lock")
    stages = {
        stage: {
            "case_ids": [case.id for case in cases_for_stage(stage)],
            "membership_sha256": membership(cases_for_stage(stage)),
            "methods": list(METHODS[stage]), "timeout_seconds": TIMEOUT_SECONDS[stage],
        } for stage in STAGES
    }
    payload = {
        "schema": "org.leo.research.native-rescue-source-lock/v1",
        "frozen_before_any_outcomes": True, "files": source_files(),
        "stages": stages, "stage_order": list(STAGES),
        "supplemental_mirrored_negative": {
            "parent_count": 12, "execution_count": 24,
            "descriptors": [supplemental_descriptor(case)
                            for case in supplemental_negative_parents()],
            "membership_sha256": stable_hash([
                supplemental_descriptor(case) for case in supplemental_negative_parents()
            ]),
            "orientations": ["original", "rxswap-v1"],
            "fresh_state_per_execution": True,
        },
        "adapter_membership_sha256": dataset.membership_sha256(),
        "candidate_lock_sha256": digest(CANDIDATE_LOCK),
        "boundary_lock_sha256": digest(BOUNDARY_LOCK),
        "boundary_result_sha256": digest(BOUNDARY_RESULT),
        "holdout_opened": False, "validation_opened": False,
    }
    with SOURCE_LOCK.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def verify_lock(stage: str, cases: tuple[Any, ...]) -> dict[str, Any]:
    lock = json.loads(SOURCE_LOCK.read_text())
    expected = lock["stages"][stage]
    if (
        lock.get("stage_order") != list(STAGES)
        or expected["case_ids"] != [case.id for case in cases]
        or expected["membership_sha256"] != membership(cases)
        or expected["methods"] != list(METHODS[stage])
        or expected["timeout_seconds"] != TIMEOUT_SECONDS[stage]
        or lock.get("adapter_membership_sha256") != dataset.membership_sha256()
        or lock.get("supplemental_mirrored_negative", {}).get("descriptors")
        != [supplemental_descriptor(case) for case in supplemental_negative_parents()]
        or lock.get("supplemental_mirrored_negative", {}).get("membership_sha256")
        != stable_hash([supplemental_descriptor(case)
                        for case in supplemental_negative_parents()])
    ):
        raise ValueError("native-rescue frozen configuration changed")
    for name, expected_hash in lock["files"].items():
        if digest(name) != expected_hash:
            raise ValueError(f"frozen rescue source changed: {name}")
    return lock


def _policy_failures(receipt: dict[str, Any]) -> int:
    original = sum(
        assessment["activity_policy_passed"] is False
        for row in receipt.get("rows", ())
        for method in ("native_tracked", "native_rescue")
        for assessment in row["native_assessments"][method]
    )
    supplemental = sum(
        assessment["activity_policy_passed"] is False
        for row in receipt.get("supplemental_mirrored_negative_rows", ())
        for method in ("native_tracked", "native_rescue")
        for assessment in row["native_assessments"][method]
    )
    return original + supplemental


def predecessor_receipts(stage: str, lock: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for prior_stage in STAGES[:STAGES.index(stage)]:
        path = result_path(prior_stage)
        payload = json.loads(path.read_text())
        if (
            payload.get("status") != "complete" or not payload.get("complete")
            or not payload.get("source_lock_stable") or payload.get("source_lock") != lock
            or payload.get("source_lock_sha256") != digest(SOURCE_LOCK)
            or len(payload.get("rows", ())) != len(lock["stages"][prior_stage]["case_ids"])
            or (prior_stage == "controls"
                and len(payload.get("supplemental_mirrored_negative_rows", ())) != 24)
            or _policy_failures(payload)
        ):
            raise ValueError(f"{prior_stage} receipt does not authorize {stage}")
        output.append({"stage": prior_stage, "path": str(path.resolve()), "sha256": digest(path)})
    return output


def timed(call: Callable[[], Any]) -> tuple[Any, dict[str, float]]:
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    value = call()
    return value, {
        "process_cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def visit_index(case: Any) -> int:
    return int(case.sequence_index if case.sequence_index is not None
               else case.visit_index if case.visit_index is not None else 0)


def rescue_call(detector: Any, raw: np.ndarray, case: Any) -> Any:
    keys = tuple(common.make_key(case, receiver) for receiver in (0, 1))
    return detector.process(
        raw, keys=keys, start_counter=case.source_counter,
        visit_index=visit_index(case), force_discovery=False,
    )


def baseline_call(detector: Any, raw: np.ndarray, case: Any) -> tuple[Any, Any]:
    return common.native_call(detector, raw, case, force_discovery=False)


def rescue_decisions(value: Any) -> tuple[Any, Any]:
    decisions = tuple(value.decisions)
    if len(decisions) != 2:
        raise ValueError("rescue result must expose exactly two receiver decisions")
    return decisions  # type: ignore[return-value]


def validate_rescue_result(value: Any) -> None:
    decisions = rescue_decisions(value)
    primary = tuple(value.primary_decisions)
    if len(primary) != 2:
        raise ValueError("rescue result must expose two primary decisions")
    inactive = [receiver for receiver, decision in enumerate(primary) if not decision.active]
    expected_receiver = inactive[0] if inactive else None
    if value.rescue_receiver != expected_receiver:
        raise ValueError("rescue receiver violates deterministic first-inactive policy")
    counts = {
        "acquisition": int(value.rescue_acquisition_count),
        "candidate": int(value.rescue_candidate_score_count),
        "seed": int(value.rescue_seed_guided_count),
        "confirmation": int(value.rescue_confirmation_guided_count),
    }
    if (not 0 <= counts["acquisition"] <= 1
            or not 0 <= counts["candidate"] <= 10
            or not 0 <= counts["seed"] <= 10
            or not 0 <= counts["confirmation"] <= 10
            or counts["confirmation"] > counts["seed"]
            or counts["seed"] > counts["candidate"]):
        raise ValueError(f"rescue work budget violated: {counts}")
    if expected_receiver is None and any(counts.values()):
        raise ValueError("fully active primary result must not run rescue")
    for receiver, primary_decision in enumerate(primary):
        if primary_decision.active and not decisions[receiver].active:
            raise ValueError("rescue must preserve every primary positive")


def execute_supplemental_controls(detector_type: type) -> list[dict[str, Any]]:
    rows = []
    for parent_index, parent in enumerate(supplemental_negative_parents()):
        parent_raw = dataset.load_iq(parent)
        parent_payload_sha = hashlib.sha256(parent_raw).hexdigest()
        for orientation_index, orientation in enumerate(("original", "rxswap-v1")):
            if orientation == "original":
                raw, case = parent_raw, parent
            else:
                raw = np.ascontiguousarray(parent_raw[:, (1, 0), :])
                raw.setflags(write=False)
                case = swapped_case(parent, hashlib.sha256(raw).hexdigest())
            derived_sha = hashlib.sha256(raw).hexdigest()
            geometry = case.rate, case.edge
            with NativeGuidedBoundary(*geometry) as baseline_engine, NativeGuidedBoundary(*geometry) as rescue_engine:
                baseline = NativeTradeoffDetector(baseline_engine)
                rescue = detector_type(NativeTradeoffDetector(rescue_engine), rescue_engine)
                order = (("native_tracked", "native_rescue")
                         if (parent_index * 2 + orientation_index) % 2 == 0
                         else ("native_rescue", "native_tracked"))
                outputs, timings = {}, {}
                for method in order:
                    if method == "native_tracked":
                        outputs[method], timings[method] = timed(
                            lambda: baseline_call(baseline, raw, case)
                        )
                    else:
                        outputs[method], timings[method] = timed(
                            lambda: rescue_call(rescue, raw, case)
                        )
                        validate_rescue_result(outputs[method])
            decisions = {
                "native_tracked": tuple(outputs["native_tracked"]),
                "native_rescue": rescue_decisions(outputs["native_rescue"]),
            }
            assessments, visits, comparisons = assess_methods(decisions, (), case)
            if hashlib.sha256(raw).hexdigest() != derived_sha:
                raise ValueError(f"supplemental input mutated: {case.id}")
            parent_file_stable = digest(parent.raw_path) == parent.raw_sha256.removeprefix("sha256:")
            if not parent_file_stable:
                raise ValueError(f"supplemental parent source changed: {parent.id}")
            rows.append({
                "paired_parent_index": parent_index, "orientation": orientation,
                "case_id": case.id, "parent_case_id": parent.id,
                "rate_hz": case.rate, "edge": case.edge, "channel": case.channel,
                "receiver_permutation": [0, 1] if orientation == "original" else [1, 0],
                "parent_raw_npy_sha256": parent.raw_sha256,
                "parent_ci16_payload_sha256": parent_payload_sha,
                "derived_ci16_payload_sha256": derived_sha,
                "parent_source_hash_stable": True, "input_immutable": True,
                "derived_truth": jsonable(case.receivers), "method_order": list(order),
                "timings": timings,
                "native_decisions": {name: jsonable(value) for name, value in decisions.items()},
                "rescue_result": jsonable(outputs["native_rescue"]),
                "native_assessments": assessments, "visit_assessments": visits,
                "method_comparison": comparisons,
            })
    if len(rows) != 24:
        raise ValueError("supplemental mirrored audit must contain 24 executions")
    return rows


def assess_methods(decisions: dict[str, tuple[Any, Any]], reference: tuple[Any, ...],
                   case: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    assessments = {
        method: common.assess_native(decisions[method], reference, case)
        for method in ("native_tracked", "native_rescue")
    }
    visits = {}
    for method, rows in assessments.items():
        reference_active = any(item["reference_active"] for item in rows)
        candidate_active = any(item["candidate_active"] for item in rows)
        matched = any(item["matched_reference"] for item in rows)
        visits[method] = {
            "reference_active": reference_active, "candidate_active": candidate_active,
            "matched_reference": matched,
            "lost_reference_visit": reference_active and not matched,
            "additional_or_mismatched_visit": candidate_active and not matched,
        }
    comparisons = []
    for receiver in (0, 1):
        baseline = assessments["native_tracked"][receiver]
        rescue = assessments["native_rescue"][receiver]
        baseline_pair = getattr(decisions["native_tracked"][receiver], "pair", None)
        association = dataset.associate_pair_to_reference(
            decisions["native_rescue"][receiver],
            () if baseline_pair is None else (baseline_pair,), case, receiver,
        )
        matched = bool(getattr(association, "matched", getattr(association, "passed", False)))
        comparisons.append({
            "receiver": receiver,
            "same_activity": baseline["candidate_active"] == rescue["candidate_active"],
            "rescue_associates_to_baseline": (
                not baseline["candidate_active"] and not rescue["candidate_active"]
            ) or matched,
            "association": jsonable(association),
        })
    return assessments, visits, comparisons


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def distribution(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values), "sum_ms": sum(values),
        "minimum_ms": min(values) if values else None,
        "p50_ms": _percentile(values, .50), "p95_ms": _percentile(values, .95),
        "p99_ms": _percentile(values, .99), "maximum_ms": max(values) if values else None,
        "values_ms": values,
    }


def is_rescue_route(route: Any) -> bool:
    return str(route) == "rescue_probe0_probe2"


def _quality(method: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    assessments = [item for row in rows for item in row["native_assessments"][method]]
    visits = [row["visit_assessments"][method] for row in rows]
    decisions = [item for row in rows for item in row["native_decisions"][method]]
    reference = sum(item["reference_active"] for item in assessments)
    lost = sum(item["lost_reference"] for item in assessments)
    return {
        "receiver_rows": len(assessments), "reference_positive_receivers": reference,
        "matched_reference_receivers": sum(item["matched_reference"] for item in assessments),
        "lost_reference_receivers": lost,
        "additional_or_mismatched_active_receivers": sum(
            item["additional_or_mismatched"] for item in assessments
        ),
        "candidate_active_receivers": sum(item["candidate_active"] for item in assessments),
        "reference_positive_visits": sum(item["reference_active"] for item in visits),
        "matched_reference_visits": sum(item["matched_reference"] for item in visits),
        "lost_reference_visits": sum(item["lost_reference_visit"] for item in visits),
        "required_policy_failed_receivers": sum(
            item["activity_policy_passed"] is False for item in assessments
        ),
        "required_policy_passed_receivers": sum(
            item["activity_policy_passed"] is True for item in assessments
        ),
        "miss_fraction": lost / reference if reference else None,
        "miss_bands": {name: (lost / reference <= limit if reference else None)
                       for name, limit in (("1%", .01), ("3%", .03), ("5%", .05))},
        "primary_controller_work_counts": {
            name: sum(int(decision[name]) for decision in decisions)
            for name in ("screened_probe_count", "guided_probe_count",
                         "blind_probe_count", "proposal_count", "scoring_count")
        },
    }


def summarize(stage: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {"by_rate": {}, "route_counts": {}, "rescue": {}}
    for rate in sorted({row["rate_hz"] for row in rows}):
        selected = [row for row in rows if row["rate_hz"] == rate]
        methods = {
            method: {
                "process_cpu": distribution([row["timings"][method]["process_cpu_ms"] for row in selected]),
                "wall": distribution([row["timings"][method]["wall_ms"] for row in selected]),
            } for method in METHODS[stage]
        }
        if "application" in methods:
            app = methods["application"]["process_cpu"]["sum_ms"]
            for method in ("native_tracked", "native_rescue"):
                cost = methods[method]["process_cpu"]["sum_ms"]
                methods[method]["aggregate_cpu_speedup_vs_application"] = app / cost if cost else None
        output["by_rate"][str(rate)] = {
            "case_count": len(selected), "methods": methods,
            "quality": {method: _quality(method, selected)
                        for method in ("native_tracked", "native_rescue")},
        }
    rescue_results = [row["rescue_result"] for row in rows]
    output["rescue"] = {
        "visits": len(rows),
        "visits_with_rescue_receiver": sum(item["rescue_receiver"] is not None for item in rescue_results),
        "accepted_rescues": sum(any(is_rescue_route(decision["route"])
                                    for decision in item["decisions"])
                                for item in rescue_results),
        "acquisition_count": sum(item["rescue_acquisition_count"] for item in rescue_results),
        "candidate_score_count": sum(item["rescue_candidate_score_count"] for item in rescue_results),
        "seed_guided_count": sum(item["rescue_seed_guided_count"] for item in rescue_results),
        "confirmation_guided_count": sum(item["rescue_confirmation_guided_count"] for item in rescue_results),
        "event_count": sum(len(item["rescue_events"]) for item in rescue_results),
        "event_reasons": {},
        "operation_counters_are_additional_to_primary_controller_work": True,
    }
    for item in rescue_results:
        for event in item["rescue_events"]:
            reason = str(event["reason"])
            output["rescue"]["event_reasons"][reason] = output["rescue"]["event_reasons"].get(reason, 0) + 1
    for row in rows:
        for method in ("native_tracked", "native_rescue"):
            for decision in row["native_decisions"][method]:
                key = f"{method}:{decision['route']}"
                output["route_counts"][key] = output["route_counts"].get(key, 0) + 1
    return output


def execute_stage(stage: str) -> None:
    output_path = result_path(stage)
    if output_path.exists():
        raise ValueError(f"preserve existing {stage} rescue result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread counts must equal one")
    cases = cases_for_stage(stage)
    lock = verify_lock(stage, cases)
    lock_hash = digest(SOURCE_LOCK)
    prior = predecessor_receipts(stage, lock)
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("CPU 0 unavailable")
    rows: list[dict[str, Any]] = []
    supplemental_rows: list[dict[str, Any]] = []
    status, error = "complete", None
    started = time.perf_counter()
    previous_handler = signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError(f"{TIMEOUT_SECONDS[stage]} second stage bound")),
    )
    signal.alarm(TIMEOUT_SECONDS[stage])
    try:
        raw_by_id = {case.id: dataset.load_iq(case) for case in cases}
        hashes = {case.id: hashlib.sha256(raw_by_id[case.id]).hexdigest() for case in cases}
        os.sched_setaffinity(0, {0})
        detector_type = rescue_detector_class()
        geometries = sorted({(case.rate, case.edge) for case in cases})
        with ExitStack() as stack:
            baseline_engines = {geometry: stack.enter_context(NativeGuidedBoundary(*geometry))
                                for geometry in geometries}
            rescue_engines = {geometry: stack.enter_context(NativeGuidedBoundary(*geometry))
                              for geometry in geometries}
            baseline_detectors = {geometry: NativeTradeoffDetector(engine)
                                  for geometry, engine in baseline_engines.items()}
            rescue_detectors = {geometry: detector_type(
                NativeTradeoffDetector(rescue_engines[geometry]), rescue_engines[geometry]
            ) for geometry in geometries}
            for index, case in enumerate(cases):
                raw, geometry = raw_by_id[case.id], (case.rate, case.edge)
                method_order = rotated_methods(stage, index)
                outputs: dict[str, Any] = {}
                timings: dict[str, Any] = {}
                for method in method_order:
                    if method == "application":
                        outputs[method], timings[method] = timed(
                            lambda: common.application_call(raw, case)
                        )
                    elif method == "native_tracked":
                        outputs[method], timings[method] = timed(
                            lambda: baseline_call(baseline_detectors[geometry], raw, case)
                        )
                    else:
                        outputs[method], timings[method] = timed(
                            lambda: rescue_call(rescue_detectors[geometry], raw, case)
                        )
                        validate_rescue_result(outputs[method])
                reference = common.application_inventory(outputs["application"], case) if "application" in outputs else ()
                decisions = {
                    "native_tracked": tuple(outputs["native_tracked"]),
                    "native_rescue": rescue_decisions(outputs["native_rescue"]),
                }
                assessments, visits, comparisons = assess_methods(decisions, reference, case)
                if hashlib.sha256(raw).hexdigest() != hashes[case.id]:
                    raise ValueError(f"detector mutated input: {case.id}")
                row = {
                    "case_id": case.id, "origin": case.origin, "cohort": case.cohort,
                    "rate_hz": case.rate, "edge": case.edge, "channel": case.channel,
                    "session_id": case.session, "visit_index": case.visit_index,
                    "source_counter": case.source_counter, "sequence_id": case.sequence_id,
                    "sequence_index": case.sequence_index, "raw_sha256": case.raw_sha256,
                    "input_array_sha256": hashes[case.id], "input_immutable": True,
                    "truth": jsonable(case.receivers), "activity_policy": case.activity_policy,
                    "expected_active": case.expected_active, "method_order": list(method_order),
                    "timings": timings,
                    "application_output": jsonable(outputs.get("application")),
                    "application_pair_inventory": jsonable(reference),
                    "application_truth_assessments": (
                        common.assess_application_truth(reference, case) if "application" in outputs else []
                    ),
                    "native_decisions": {name: jsonable(value) for name, value in decisions.items()},
                    "rescue_result": jsonable(outputs["native_rescue"]),
                    "output_sha256": {name: stable_hash(value) for name, value in outputs.items()},
                    "native_assessments": assessments, "visit_assessments": visits,
                    "method_comparison": comparisons,
                }
                rows.append(row)
                print(json.dumps({"stage": stage, "case": case.id, "completed": len(rows)}), flush=True)
        if stage == "controls":
            supplemental_rows = execute_supplemental_controls(detector_type)
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        os.sched_setaffinity(0, affinity)
    stable = digest(SOURCE_LOCK) == lock_hash and all(
        digest(name) == expected for name, expected in lock["files"].items()
    )
    complete = (
        status == "complete" and len(rows) == len(cases) and stable
        and (stage != "controls" or len(supplemental_rows) == 24)
    )
    supplemental_summary = {
        method: {
            "executions": len(supplemental_rows),
            "active_receiver_decisions": sum(
                decision["active"] for row in supplemental_rows
                for decision in row["native_decisions"][method]
            ),
            "required_policy_failures": sum(
                item["activity_policy_passed"] is False for row in supplemental_rows
                for item in row["native_assessments"][method]
            ),
        } for method in ("native_tracked", "native_rescue")
    }
    payload = {
        "schema": "org.leo.research.native-rescue-result/v1", "stage": stage,
        "status": status, "error": error, "complete": complete,
        "source_lock": lock, "source_lock_sha256": lock_hash,
        "source_lock_stable": stable, "prior_complete_receipts": prior,
        "thread_environment": environment, "affinity_cpu": 0,
        "affinity_restored": sorted(affinity), "timeout_seconds": TIMEOUT_SECONDS[stage],
        "rows": rows, "summary": summarize(stage, rows),
        "supplemental_mirrored_negative_rows": supplemental_rows,
        "supplemental_mirrored_negative_summary": supplemental_summary,
        "quality_failures_are_report_only_except_constructed_truth_stage_gate": True,
        "holdout_opened": False, "validation_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    with output_path.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if not complete:
        raise RuntimeError(error or f"{stage} integrity failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--freeze", action="store_true")
    actions.add_argument("--stage", choices=STAGES)
    args = parser.parse_args()
    freeze() if args.freeze else execute_stage(args.stage)


if __name__ == "__main__":
    main()
