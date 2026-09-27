"""Frozen staged evaluation for the two-port tone-conditioned rescue."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
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
from typing import Any


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
RAW = REPORT / "native_rescue"
BOUNDARY = REPORT / "native_guided_boundary"
TRADEOFF = REPORT / "native_tradeoff"
RAW_LOCK = RAW / "source_lock.json"
RAW_CONTROLS = RAW / "results.controls.json"
ENGINE_LOCK = HERE / "ENGINE_LOCK.json"
SOURCE_LOCK = HERE / "source_lock.json"
EXPECTED_RAW_LOCK = "0c12603cba55e137501032577f36bb8c7b0a0c3bbe7e06da34a949c687cabb54"
EXPECTED_RAW_CONTROLS = "cddba5d93b7093b9e95fe522233a292635a000f25c034e35b61fae92d4cb0727"
STAGES = ("controls", "diagnostic", "real")
METHODS = {
    "controls": ("native_tracked", "raw_rescue", "tone_rescue"),
    "diagnostic": ("application", "native_tracked", "tone_rescue"),
    "real": ("application", "native_tracked", "tone_rescue"),
}
TIMEOUT_SECONDS = {"controls": 120, "diagnostic": 120, "real": 300}
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)

sys.path[:0] = [
    str(ROOT / "src"), str(HERE), str(RAW), str(BOUNDARY), str(TRADEOFF),
]

import numpy as np  # noqa: E402
import leo  # noqa: E402
from native_guided_boundary import NativeGuidedBoundary  # noqa: E402
from native_rescue_detector import SameRxRescueDetector  # noqa: E402
from native_tradeoff_detector import NativeTradeoffDetector  # noqa: E402
from tone_conditioned_rescue_detector import (  # noqa: E402
    ToneConditionedSameRxRescueDetector,
)

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("tone-rescue evaluation must use this checkout")


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


raw_runner = _load_module("tone_rescue_frozen_raw_runner", RAW / "run_evaluation.py")
common = raw_runner.common
dataset = raw_runner.dataset
digest = raw_runner.digest
jsonable = raw_runner.jsonable
stable_hash = raw_runner.stable_hash
distribution = raw_runner.distribution


def tone_engine_class() -> type:
    return importlib.import_module("native_tone_guided").NativeToneGuided


def cases_for_stage(stage: str) -> tuple[Any, ...]:
    cases = tuple(raw_runner.cases_for_stage(stage))
    expected = {"controls": 42, "diagnostic": 26, "real": 64}[stage]
    if len(cases) != expected or any(case.split != "development" for case in cases):
        raise ValueError(f"invalid {stage} development membership")
    return cases


def result_path(stage: str) -> Path:
    return HERE / f"results.{stage}.json"


def rotated_methods(stage: str, index: int) -> tuple[str, ...]:
    methods = METHODS[stage]
    offset = index % len(methods)
    return methods[offset:] + methods[:offset]


def _engine_inventory() -> dict[str, str]:
    payload = json.loads(ENGINE_LOCK.read_text())
    artifacts = payload.get("artifacts_sha256", payload.get("files", {}))
    if not artifacts:
        raise ValueError("tone engine lock has no artifact inventory")
    files = {str(ENGINE_LOCK.resolve()): digest(ENGINE_LOCK)}
    for name, expected in artifacts.items():
        path = Path(name)
        if not path.is_absolute():
            path = HERE / path
        if digest(path) != expected:
            raise ValueError(f"tone engine artifact changed: {path}")
        files[str(path.resolve())] = expected
        if path.name.endswith('.so.build.json'):
            receipt = json.loads(path.read_text())
            for dependency, expected_dependency in receipt['sources_sha256'].items():
                if digest(dependency) != expected_dependency:
                    raise ValueError(f'tone build dependency changed: {dependency}')
                files[str(Path(dependency).resolve())] = expected_dependency
    return files


def source_files() -> dict[str, str]:
    if digest(RAW_LOCK) != EXPECTED_RAW_LOCK or digest(RAW_CONTROLS) != EXPECTED_RAW_CONTROLS:
        raise ValueError("frozen raw-rescue parent changed")
    parent_lock = json.loads(RAW_LOCK.read_text())
    parent_result = json.loads(RAW_CONTROLS.read_text())
    if (
        not parent_result.get("complete")
        or not parent_result.get("source_lock_stable")
        or parent_result.get("source_lock") != parent_lock
        or len(parent_result.get("rows", ())) != 42
        or len(parent_result.get("supplemental_mirrored_negative_rows", ())) != 24
    ):
        raise ValueError("raw-rescue parent receipt is incomplete")
    files: dict[str, str] = {}
    for name, expected in parent_lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen parent dependency changed: {name}")
        files[name] = expected
    required = {
        HERE / "DESIGN.md",
        HERE / "DESIGN_REVIEW.md",
        HERE / "tone_conditioned_rescue_detector.py",
        HERE / "test_tone_conditioned_rescue_detector.py",
        HERE / "run_tone_rescue_evaluation.py",
        HERE / "test_tone_rescue_evaluation.py",
        RAW_LOCK,
        RAW_CONTROLS,
    }
    missing = [path for path in required if not path.exists()]
    if missing:
        raise ValueError(f"missing tone-rescue evaluation sources: {missing}")
    additions = {str(path.resolve()): digest(path) for path in required}
    additions.update(_engine_inventory())
    for name, expected in additions.items():
        if name in files and files[name] != expected:
            raise ValueError(f"tone-rescue dependency pin conflicts: {name}")
        files[name] = expected
    return dict(sorted(files.items()))


def freeze() -> None:
    if SOURCE_LOCK.exists():
        raise ValueError("preserve existing tone-rescue source lock")
    stages = {
        stage: {
            "case_ids": [case.id for case in cases_for_stage(stage)],
            "membership_sha256": raw_runner.membership(cases_for_stage(stage)),
            "methods": list(METHODS[stage]),
            "timeout_seconds": TIMEOUT_SECONDS[stage],
        }
        for stage in STAGES
    }
    parents = raw_runner.supplemental_negative_parents()
    payload = {
        "schema": "org.leo.research.native-tone-rescue-source-lock/v1",
        "frozen_before_any_outcomes": True,
        "files": source_files(),
        "stages": stages,
        "stage_order": list(STAGES),
        "supplemental_mirrored_negative": {
            "parent_count": 12,
            "execution_count": 24,
            "descriptors": [raw_runner.supplemental_descriptor(case) for case in parents],
            "membership_sha256": stable_hash([
                raw_runner.supplemental_descriptor(case) for case in parents
            ]),
            "orientations": ["original", "rxswap-v1"],
            "fresh_state_per_execution": True,
        },
        "adapter_membership_sha256": dataset.membership_sha256(),
        "raw_rescue_source_lock_sha256": digest(RAW_LOCK),
        "raw_rescue_controls_result_sha256": digest(RAW_CONTROLS),
        "tone_engine_lock_sha256": digest(ENGINE_LOCK),
        "holdout_opened": False,
        "validation_opened": False,
    }
    with SOURCE_LOCK.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def verify_lock(stage: str, cases: tuple[Any, ...]) -> dict[str, Any]:
    lock = json.loads(SOURCE_LOCK.read_text())
    selected = lock["stages"][stage]
    parents = raw_runner.supplemental_negative_parents()
    if (
        lock.get("stage_order") != list(STAGES)
        or selected["case_ids"] != [case.id for case in cases]
        or selected["membership_sha256"] != raw_runner.membership(cases)
        or selected["methods"] != list(METHODS[stage])
        or selected["timeout_seconds"] != TIMEOUT_SECONDS[stage]
        or lock.get("adapter_membership_sha256") != dataset.membership_sha256()
        or lock.get("raw_rescue_source_lock_sha256") != EXPECTED_RAW_LOCK
        or lock.get("raw_rescue_controls_result_sha256") != EXPECTED_RAW_CONTROLS
        or lock.get("supplemental_mirrored_negative", {}).get("descriptors")
        != [raw_runner.supplemental_descriptor(case) for case in parents]
    ):
        raise ValueError("tone-rescue frozen configuration changed")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen tone-rescue source changed: {name}")
    return lock


def _required_policy_failures(receipt: dict[str, Any]) -> int:
    checked = ("native_tracked", "tone_rescue")
    return sum(
        assessment["activity_policy_passed"] is False
        for section in ("rows", "supplemental_mirrored_negative_rows")
        for row in receipt.get(section, ())
        for method in checked
        for assessment in row["native_assessments"][method]
    )


def predecessor_receipts(stage: str, lock: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for prior_stage in STAGES[:STAGES.index(stage)]:
        path = result_path(prior_stage)
        payload = json.loads(path.read_text())
        if (
            payload.get("status") != "complete"
            or not payload.get("complete")
            or not payload.get("source_lock_stable")
            or payload.get("source_lock") != lock
            or payload.get("source_lock_sha256") != digest(SOURCE_LOCK)
            or len(payload.get("rows", ())) != len(lock["stages"][prior_stage]["case_ids"])
            or (prior_stage == "controls"
                and len(payload.get("supplemental_mirrored_negative_rows", ())) != 24)
            or _required_policy_failures(payload)
        ):
            raise ValueError(f"{prior_stage} receipt does not authorize {stage}")
        output.append({"stage": prior_stage, "path": str(path.resolve()), "sha256": digest(path)})
    return output


def validate_tone_result(value: Any) -> None:
    raw_runner.validate_rescue_result(value)
    calls = tuple(value.tone_guided_calls)
    expected = int(value.rescue_seed_guided_count) + int(value.rescue_confirmation_guided_count)
    if len(calls) != expected:
        raise ValueError("tone rescue did not retain every guided call")
    for call in calls:
        if call.probe_index not in (0, 2) or call.receiver != value.rescue_receiver:
            raise ValueError("tone rescue recorded an invalid guided call identity")
        observation = call.observation
        if observation is not None:
            for field in (
                "nuisance_enabled", "nuisance_applied", "nuisance_frequency_hz",
                "nuisance_spectral_fraction", "nuisance_fitted_power_fraction",
                "nuisance_cpu_ms", "pack_cpu_ms", "conversion_cpu_ms",
                "glrt_cpu_ms", "glrt_evaluations",
            ):
                if not hasattr(observation, field):
                    raise ValueError(f"tone rescue observation omitted {field}")


def _make_detectors(stack: ExitStack, geometry: tuple[int, str], *, include_raw: bool) -> dict[str, Any]:
    boundary = stack.enter_context(NativeGuidedBoundary(*geometry))
    tone_primary_boundary = stack.enter_context(NativeGuidedBoundary(*geometry))
    tone_engine = stack.enter_context(tone_engine_class()(*geometry))
    detectors: dict[str, Any] = {
        "native_tracked": NativeTradeoffDetector(boundary),
        "tone_rescue": ToneConditionedSameRxRescueDetector(
            NativeTradeoffDetector(tone_primary_boundary), tone_engine
        ),
    }
    if include_raw:
        raw_boundary = stack.enter_context(NativeGuidedBoundary(*geometry))
        detectors["raw_rescue"] = SameRxRescueDetector(
            NativeTradeoffDetector(raw_boundary), raw_boundary
        )
    return detectors


def _call(method: str, detector: Any, raw: np.ndarray, case: Any) -> Any:
    if method == "application":
        return common.application_call(raw, case)
    if method == "native_tracked":
        return raw_runner.baseline_call(detector, raw, case)
    result = raw_runner.rescue_call(detector, raw, case)
    raw_runner.validate_rescue_result(result)
    if method == "tone_rescue":
        validate_tone_result(result)
    return result


def _decisions(method: str, value: Any) -> tuple[Any, Any]:
    return tuple(value) if method == "native_tracked" else raw_runner.rescue_decisions(value)


def primary_parity(outputs: dict[str, Any]) -> dict[str, bool]:
    """Compare each wrapper's untouched primary decision to the baseline."""

    baseline = stable_hash(tuple(outputs["native_tracked"]))
    parity = {
        method: stable_hash(tuple(outputs[method].primary_decisions)) == baseline
        for method in ("raw_rescue", "tone_rescue") if method in outputs
    }
    if not all(parity.values()):
        raise ValueError(f"rescue wrapper changed primary detector science/state: {parity}")
    return parity


def _assess(decisions: dict[str, tuple[Any, Any]], reference: tuple[Any, ...], case: Any):
    assessments = {
        method: common.assess_native(value, reference, case)
        for method, value in decisions.items()
    }
    visits = {}
    for method, items in assessments.items():
        ref_active = any(item["reference_active"] for item in items)
        candidate_active = any(item["candidate_active"] for item in items)
        matched = any(item["matched_reference"] for item in items)
        visits[method] = {
            "reference_active": ref_active,
            "candidate_active": candidate_active,
            "matched_reference": matched,
            "lost_reference_visit": ref_active and not matched,
            "additional_or_mismatched_visit": candidate_active and not matched,
        }
    return assessments, visits


def _execute_supplemental() -> list[dict[str, Any]]:
    rows = []
    for parent_index, parent in enumerate(raw_runner.supplemental_negative_parents()):
        parent_raw = dataset.load_iq(parent)
        parent_payload_sha = hashlib.sha256(parent_raw).hexdigest()
        for orientation_index, orientation in enumerate(("original", "rxswap-v1")):
            if orientation == "original":
                raw, case = parent_raw, parent
            else:
                raw = np.ascontiguousarray(parent_raw[:, (1, 0), :])
                raw.setflags(write=False)
                case = raw_runner.swapped_case(parent, hashlib.sha256(raw).hexdigest())
            payload_sha = hashlib.sha256(raw).hexdigest()
            with ExitStack() as stack:
                detectors = _make_detectors(stack, (case.rate, case.edge), include_raw=True)
                order = rotated_methods("controls", parent_index * 2 + orientation_index)
                outputs, timings = {}, {}
                for method in order:
                    outputs[method], timings[method] = raw_runner.timed(
                        lambda method=method: _call(method, detectors[method], raw, case)
                    )
            decisions = {method: _decisions(method, outputs[method]) for method in order}
            parity = primary_parity(outputs)
            assessments, visits = _assess(decisions, (), case)
            if hashlib.sha256(raw).hexdigest() != payload_sha:
                raise ValueError(f"supplemental input mutated: {case.id}")
            if digest(parent.raw_path) != parent.raw_sha256.removeprefix("sha256:"):
                raise ValueError(f"supplemental parent source changed: {parent.id}")
            rows.append({
                "paired_parent_index": parent_index,
                "orientation": orientation,
                "case_id": case.id,
                "parent_case_id": parent.id,
                "rate_hz": case.rate,
                "edge": case.edge,
                "channel": case.channel,
                "receiver_permutation": [0, 1] if orientation == "original" else [1, 0],
                "parent_raw_npy_sha256": parent.raw_sha256,
                "parent_ci16_payload_sha256": parent_payload_sha,
                "derived_ci16_payload_sha256": payload_sha,
                "parent_source_hash_stable": True,
                "input_immutable": True,
                "derived_truth": jsonable(case.receivers),
                "method_order": list(order),
                "timings": timings,
                "native_decisions": {name: jsonable(value) for name, value in decisions.items()},
                "raw_rescue_result": jsonable(outputs["raw_rescue"]),
                "tone_rescue_result": jsonable(outputs["tone_rescue"]),
                "primary_decision_parity": parity,
                "native_assessments": assessments,
                "visit_assessments": visits,
            })
    if len(rows) != 24:
        raise ValueError("supplemental mirrored audit must contain 24 executions")
    return rows


def _quality(method: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = [item for row in rows for item in row["native_assessments"][method]]
    visits = [row["visit_assessments"][method] for row in rows]
    reference = sum(item["reference_active"] for item in items)
    lost = sum(item["lost_reference"] for item in items)
    return {
        "receiver_rows": len(items),
        "reference_positive_receivers": reference,
        "matched_reference_receivers": sum(item["matched_reference"] for item in items),
        "lost_reference_receivers": lost,
        "additional_or_mismatched_active_receivers": sum(
            item["additional_or_mismatched"] for item in items
        ),
        "candidate_active_receivers": sum(item["candidate_active"] for item in items),
        "reference_positive_visits": sum(item["reference_active"] for item in visits),
        "matched_reference_visits": sum(item["matched_reference"] for item in visits),
        "lost_reference_visits": sum(item["lost_reference_visit"] for item in visits),
        "required_policy_failed_receivers": sum(
            item["activity_policy_passed"] is False for item in items
        ),
        "miss_fraction": lost / reference if reference else None,
        "miss_bands": {name: (lost / reference <= limit if reference else None)
                       for name, limit in (("1%", .01), ("3%", .03), ("5%", .05))},
    }


def summarize(stage: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {"by_rate": {}, "route_counts": {}, "rescue": {}}
    native_methods = tuple(method for method in METHODS[stage] if method != "application")
    for rate in sorted({row["rate_hz"] for row in rows}):
        selected = [row for row in rows if row["rate_hz"] == rate]
        methods = {
            method: {
                "process_cpu": distribution([
                    row["timings"][method]["process_cpu_ms"] for row in selected
                ]),
                "wall": distribution([row["timings"][method]["wall_ms"] for row in selected]),
            }
            for method in METHODS[stage]
        }
        if "application" in methods:
            app = methods["application"]["process_cpu"]["sum_ms"]
            for method in native_methods:
                cost = methods[method]["process_cpu"]["sum_ms"]
                methods[method]["aggregate_cpu_speedup_vs_application"] = app / cost if cost else None
        output["by_rate"][str(rate)] = {
            "case_count": len(selected),
            "methods": methods,
            "quality": {method: _quality(method, selected) for method in native_methods},
        }
    for row in rows:
        for method in native_methods:
            for decision in row["native_decisions"][method]:
                key = f"{method}:{decision['route']}"
                output["route_counts"][key] = output["route_counts"].get(key, 0) + 1
    for method, field in (("raw_rescue", "raw_rescue_result"),
                          ("tone_rescue", "tone_rescue_result")):
        results = [row[field] for row in rows if field in row]
        output["rescue"][method] = {
            "visits": len(results),
            "accepted_rescues": sum(any(
                decision["route"] == "rescue_probe0_probe2" for decision in item["decisions"]
            ) for item in results),
            "candidate_score_count": sum(item["rescue_candidate_score_count"] for item in results),
            "seed_guided_count": sum(item["rescue_seed_guided_count"] for item in results),
            "confirmation_guided_count": sum(item["rescue_confirmation_guided_count"] for item in results),
            "tone_guided_call_receipts": sum(len(item.get("tone_guided_calls", ())) for item in results),
            "operation_counters_are_additional_to_primary_controller_work": True,
        }
    return output


def execute_stage(stage: str) -> None:
    output_path = result_path(stage)
    if output_path.exists():
        raise ValueError(f"preserve existing {stage} tone-rescue result")
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
    supplemental: list[dict[str, Any]] = []
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
        with ExitStack() as stack:
            detector_sets = {
                geometry: _make_detectors(stack, geometry, include_raw=stage == "controls")
                for geometry in sorted({(case.rate, case.edge) for case in cases})
            }
            for index, case in enumerate(cases):
                raw = raw_by_id[case.id]
                methods = rotated_methods(stage, index)
                detectors = detector_sets[(case.rate, case.edge)]
                outputs, timings = {}, {}
                for method in methods:
                    detector = None if method == "application" else detectors[method]
                    outputs[method], timings[method] = raw_runner.timed(
                        lambda method=method, detector=detector: _call(method, detector, raw, case)
                    )
                reference = common.application_inventory(outputs["application"], case) \
                    if "application" in outputs else ()
                decisions = {
                    method: _decisions(method, outputs[method])
                    for method in methods if method != "application"
                }
                parity = primary_parity(outputs)
                assessments, visits = _assess(decisions, reference, case)
                if hashlib.sha256(raw).hexdigest() != hashes[case.id]:
                    raise ValueError(f"detector mutated input: {case.id}")
                rows.append({
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
                    "input_array_sha256": hashes[case.id],
                    "input_immutable": True,
                    "truth": jsonable(case.receivers),
                    "activity_policy": case.activity_policy,
                    "expected_active": case.expected_active,
                    "method_order": list(methods),
                    "timings": timings,
                    "application_output": jsonable(outputs.get("application")),
                    "application_pair_inventory": jsonable(reference),
                    "application_truth_assessments": (
                        common.assess_application_truth(reference, case)
                        if "application" in outputs else []
                    ),
                    "native_decisions": {name: jsonable(value) for name, value in decisions.items()},
                    "raw_rescue_result": jsonable(outputs.get("raw_rescue")),
                    "tone_rescue_result": jsonable(outputs["tone_rescue"]),
                    "primary_decision_parity": parity,
                    "output_sha256": {name: stable_hash(value) for name, value in outputs.items()},
                    "native_assessments": assessments,
                    "visit_assessments": visits,
                })
                print(json.dumps({"stage": stage, "case": case.id, "completed": len(rows)}), flush=True)
        if stage == "controls":
            supplemental = _execute_supplemental()
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
        and (stage != "controls" or len(supplemental) == 24)
    )
    supplemental_summary = {
        method: {
            "executions": len(supplemental),
            "active_receiver_decisions": sum(
                decision["active"] for row in supplemental
                for decision in row["native_decisions"][method]
            ),
            "required_policy_failures": sum(
                item["activity_policy_passed"] is False for row in supplemental
                for item in row["native_assessments"][method]
            ),
        }
        for method in METHODS["controls"]
    }
    payload = {
        "schema": "org.leo.research.native-tone-rescue-result/v1",
        "stage": stage,
        "status": status,
        "error": error,
        "complete": complete,
        "source_lock": lock,
        "source_lock_sha256": lock_hash,
        "source_lock_stable": stable,
        "prior_complete_receipts": prior,
        "thread_environment": environment,
        "affinity_cpu": 0,
        "affinity_restored": sorted(affinity),
        "timeout_seconds": TIMEOUT_SECONDS[stage],
        "rows": rows,
        "summary": summarize(stage, rows),
        "supplemental_mirrored_negative_rows": supplemental,
        "supplemental_mirrored_negative_summary": supplemental_summary,
        "raw_rescue_failures_are_frozen_report_only": True,
        "progression_requires_native_and_tone_rescue_constructed_truth": True,
        "holdout_opened": False,
        "validation_opened": False,
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
