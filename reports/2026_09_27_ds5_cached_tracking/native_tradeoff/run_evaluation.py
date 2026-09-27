"""Frozen staged evaluation of native blind and causal tracked detection.

The runner intentionally keeps timing, state advancement, scientific
assessment, and persistence in one small program so a receipt pins the exact
call boundary.  It never loads validation or holdout IQ.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import statistics
import sys
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
TG11 = REPORT / "tg11"
sys.path[:0] = [str(ROOT / "src"), str(TG11), str(HERE)]

import numpy as np  # noqa: E402

import leo  # noqa: E402
import leo.analysis.starlink.acquisition as acquisition  # noqa: E402
import leo.analysis.starlink.pilot_methods as pilot_methods  # noqa: E402
import leo.analysis.starlink.templates as templates  # noqa: E402
import leo.scanner.detector as scanner_detector  # noqa: E402
from leo.scanner.models import (  # noqa: E402
    ScannerConfiguration,
    current_low_band_targets,
)

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("tradeoff evaluation must import leo from this checkout")
if Path(templates.__file__).resolve() != ROOT / "src/leo/analysis/starlink/templates.py":
    raise RuntimeError("tradeoff evaluation must use this checkout's templates")

import tradeoff_dataset as dataset  # noqa: E402
from native_engine import NativeTG11  # noqa: E402
from native_tradeoff_detector import (  # noqa: E402
    CacheKey,
    NativeTradeoffDetector,
)

THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)
STAGES = ("controls", "diagnostic", "real")
METHODS = {
    "controls": ("native_blind", "native_tracked"),
    "diagnostic": ("application", "native_blind", "native_tracked"),
    "real": ("application", "native_blind", "native_tracked"),
}
TIMEOUT_SECONDS = {"controls": 120, "diagnostic": 300, "real": 300}


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
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite value cannot enter a scientific receipt")
    return value


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def make_key(case: Any, receiver: int) -> CacheKey:
    return CacheKey(
        case.session, receiver, case.channel, case.edge, case.rate,
        case.tuning_identity, case.calibration_identity,
    )


def configuration(case: Any) -> ScannerConfiguration:
    target = next(
        item for item in current_low_band_targets()
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


def application_call(raw: np.ndarray, case: Any) -> Any:
    samples = np.empty(raw.shape[:2], dtype=np.complex64)
    samples.real = raw[:, :, 0]
    samples.imag = raw[:, :, 1]
    samples.setflags(write=False)
    return scanner_detector.analyze_glrt64_dwell(
        samples, configuration(case), edge=case.edge
    )


def native_call(
    detector: NativeTradeoffDetector,
    raw: np.ndarray,
    case: Any,
    *,
    force_discovery: bool,
) -> tuple[Any, Any]:
    visit_index = (
        case.sequence_index
        if case.sequence_index is not None
        else case.visit_index if case.visit_index is not None else 0
    )
    return tuple(
        detector.process(
            raw,
            make_key(case, receiver),
            start_counter=case.source_counter,
            visit_index=int(visit_index),
            force_discovery=force_discovery,
        )
        for receiver in (0, 1)
    )  # type: ignore[return-value]


def timed(function: Callable[[], Any]) -> tuple[Any, dict[str, float]]:
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    result = function()
    return result, {
        "process_cpu_ms": (time.process_time_ns() - cpu_start) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall_start) / 1e6,
    }


def application_inventory(analysis: Any, case: Any) -> tuple[Any, ...]:
    inventory = tuple(dataset.reference_positive_pair_inventory(analysis, case))
    if bool(inventory) != (analysis.first is not None):
        raise ValueError(
            f"application first/inventory invariant failed for {case.id}"
        )
    return inventory


def _matched(association: Any) -> bool:
    return bool(_get(association, "matched", _get(association, "passed", False)))


def assess_native(
    decisions: tuple[Any, Any],
    reference: tuple[Any, ...],
    case: Any,
) -> list[dict[str, Any]]:
    rows = []
    for receiver, decision in enumerate(decisions):
        receiver_reference = tuple(
            item for item in reference if int(_get(item, "receiver")) == receiver
        )
        assessment = dataset.assess_receiver(
            decision, receiver_reference, case, receiver, profile="native_diverse"
        )
        active = bool(assessment["candidate_active"])
        reference_active = bool(assessment["reference_active"])
        associated = assessment["reference_outcome"] == "retained_associated"
        rows.append({**jsonable(assessment),
                     "matched_reference": associated,
                     "lost_reference": reference_active and not associated,
                     "additional_or_mismatched": active and not associated})
    return rows


def assess_application_truth(
    inventory: tuple[Any, ...], case: Any
) -> list[dict[str, Any]]:
    rows = []
    for receiver in (0, 1):
        selected = tuple(item for item in inventory if int(_get(item, "receiver")) == receiver)
        rows.append({
            "receiver": receiver,
            "pair_count": len(selected),
            "inactive_assessment": (
                dataset.assess_receiver(None, (), case, receiver, profile="baseline_early")
                if not selected else None
            ),
            "pairs": [{
                "pair": jsonable(pair),
                "truth_association": jsonable(dataset.associate_pair_to_truth(
                    pair, case, receiver, profile="baseline_early"
                )),
            } for pair in selected],
        })
    return jsonable(rows)


def cases_for_stage(stage: str) -> tuple[Any, ...]:
    if stage == "controls":
        return tuple(dataset.legacy_controls()) + tuple(
            dataset.legacy_sequence_occurrences()
        )
    if stage == "diagnostic":
        return tuple(dataset.diagnostic_development_cases())
    if stage == "real":
        cases = tuple(dataset.real_prefix_cases())
        ordered = tuple(sorted(cases, key=lambda item: (item.session, item.source_counter)))
        if {item.id for item in ordered} != {item.id for item in cases}:
            raise ValueError("real case inventory changed while sorting")
        return ordered
    raise ValueError(f"unknown stage: {stage}")


def _source_manifest_paths() -> set[Path]:
    paths: set[Path] = set()
    if hasattr(dataset, "source_hashes"):
        paths.update(Path(item) for item in dataset.source_hashes())
    for name in ("SOURCE_HASHES", "SOURCE_FILES"):
        values = getattr(dataset, name, {})
        paths.update(Path(item) for item in values)
    return paths


def source_files() -> dict[str, str]:
    native_backend = getattr(acquisition, "_native_acquisition", None)
    if native_backend is None or not getattr(native_backend, "__file__", None):
        raise ValueError("current scanner native acquisition backend is unavailable")
    paths = {
        HERE / "EVAL_DESIGN.md",
        HERE / "run_evaluation.py",
        HERE / "test_run_evaluation.py",
        HERE / "native_tradeoff_detector.py",
        HERE / "tradeoff_dataset.py",
        HERE / "test_run_evaluation.py",
        HERE / "test_native_tradeoff_dataset.py",
        HERE / "test_native_tradeoff_detector.py",
        TG11 / "native_engine.py",
        TG11 / "decision.py",
        TG11 / "libtg11.so",
        TG11 / "libtg11.so.build.json",
        Path(scanner_detector.__file__),
        Path(acquisition.__file__),
        Path(pilot_methods.__file__),
        Path(templates.__file__),
        Path(native_backend.__file__),
        ROOT / "src/leo/scanner/models.py",
    } | _source_manifest_paths()
    receipt = json.loads((TG11 / "libtg11.so.build.json").read_text())
    expected_binary = receipt.get("binary_sha256")
    if expected_binary and digest(TG11 / "libtg11.so") != expected_binary:
        raise ValueError("TG11 binary differs from its build receipt")
    for name, expected in receipt.get("sources_sha256", {}).items():
        path = Path(name)
        if digest(path) != expected:
            raise ValueError(f"TG11 native dependency changed: {path}")
        paths.add(path)
    return {str(path.resolve()): digest(path) for path in sorted(paths)}


def lock_path(stage: str) -> Path:
    return HERE / f"source_lock.{stage}.json"


def result_path(stage: str) -> Path:
    return HERE / f"results.{stage}.json"


def _membership(cases: tuple[Any, ...]) -> str:
    return stable_hash([
        {
            "id": case.id,
            "rate": case.rate,
            "edge": case.edge,
            "session": case.session,
            "source_counter": case.source_counter,
            "raw_sha256": case.raw_sha256,
        }
        for case in cases
    ])


def freeze(stage: str) -> None:
    target = lock_path(stage)
    if target.exists():
        raise ValueError(f"preserve existing {stage} source lock")
    cases = cases_for_stage(stage)
    if stage != "controls":
        common_lock = json.loads(lock_path("controls").read_text())
        for name, expected in common_lock["files"].items():
            if digest(name) != expected:
                raise ValueError(f"common frozen variant changed after controls: {name}")
    predecessor = {"diagnostic": "controls", "real": "diagnostic"}.get(stage)
    prior = None
    if predecessor is not None:
        prior_path = result_path(predecessor)
        if not prior_path.exists():
            raise ValueError(f"{predecessor} receipt required before freezing {stage}")
        prior_payload = json.loads(prior_path.read_text())
        if not prior_payload.get("complete"):
            raise ValueError(f"incomplete {predecessor} evidence blocks {stage}")
        prior_lock_path = lock_path(predecessor)
        prior_lock = json.loads(prior_lock_path.read_text())
        if prior_payload.get("source_lock") != prior_lock:
            raise ValueError(f"{predecessor} source lock differs from its receipt")
        prior = {"stage": predecessor, "path": str(prior_path.resolve()),
                 "sha256": digest(prior_path),
                 "source_lock_path": str(prior_lock_path.resolve()),
                 "source_lock_sha256": digest(prior_lock_path)}
    payload = {
        "schema": "org.leo.research.native-tradeoff-source-lock/v1",
        "stage": stage,
        "frozen_before_stage_outcomes": True,
        "files": source_files(),
        "case_ids": [case.id for case in cases],
        "membership_sha256": _membership(cases),
        "adapter_membership_sha256": dataset.membership_sha256(),
        "prior_complete_receipt": prior,
        "methods": list(METHODS[stage]),
        "timeout_seconds": TIMEOUT_SECONDS[stage],
        "application_native_backend": acquisition._folded_anchor_score_grid_backend(),
        "holdout_opened": False,
        "validation_opened": False,
    }
    with target.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def verify_lock(stage: str, cases: tuple[Any, ...]) -> dict[str, Any]:
    lock = json.loads(lock_path(stage).read_text())
    if lock["stage"] != stage or lock["case_ids"] != [case.id for case in cases]:
        raise ValueError("stage membership differs from its source lock")
    if lock["membership_sha256"] != _membership(cases):
        raise ValueError("stage membership digest changed")
    if lock["adapter_membership_sha256"] != dataset.membership_sha256():
        raise ValueError("adapter-wide membership digest changed")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen source changed: {name}")
    prior = lock.get("prior_complete_receipt")
    if prior is not None:
        if digest(prior["path"]) != prior["sha256"]:
            raise ValueError("prior stage receipt changed")
        if digest(prior["source_lock_path"]) != prior["source_lock_sha256"]:
            raise ValueError("prior stage source lock changed")
    if stage != "controls":
        common_lock = json.loads(lock_path("controls").read_text())
        for name, expected in common_lock["files"].items():
            if digest(name) != expected:
                raise ValueError(f"common frozen variant changed after controls: {name}")
    return lock


def execute_stage(stage: str) -> None:
    output = result_path(stage)
    if output.exists():
        raise ValueError(f"preserve existing {stage} result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread counts must equal one before launch")
    cases = cases_for_stage(stage)
    lock = verify_lock(stage, cases)
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    rows: list[dict[str, Any]] = []
    status, error = "complete", None
    started = time.perf_counter()
    previous_handler = signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError(
            f"{TIMEOUT_SECONDS[stage]} second {stage} bound"
        )),
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
            engines = {
                geometry: stack.enter_context(
                    NativeTG11(*geometry, library=TG11 / "libtg11.so")
                )
                for geometry in geometries
            }
            blind = {
                geometry: NativeTradeoffDetector(engine)
                for geometry, engine in engines.items()
            }
            tracked = {
                geometry: NativeTradeoffDetector(engine)
                for geometry, engine in engines.items()
            }
            for case_index, case in enumerate(cases):
                raw = raw_by_id[case.id]
                rotation = case_index % len(METHODS[stage])
                method_order = METHODS[stage][rotation:] + METHODS[stage][:rotation]
                results: dict[str, Any] = {}
                timings: dict[str, Any] = {}
                for method in method_order:
                    geometry = (case.rate, case.edge)
                    if method == "application":
                        value, timing = timed(
                            lambda raw=raw, case=case: application_call(raw, case)
                        )
                    elif method == "native_blind":
                        value, timing = timed(
                            lambda detector=blind[geometry], raw=raw, case=case: native_call(
                                detector, raw, case, force_discovery=True
                            )
                        )
                    else:
                        value, timing = timed(
                            lambda detector=tracked[geometry], raw=raw, case=case: native_call(
                                detector, raw, case, force_discovery=False
                            )
                        )
                    results[method] = value
                    timings[method] = timing
                if hashlib.sha256(raw).hexdigest() != input_hashes[case.id]:
                    raise ValueError(f"detector mutated input: {case.id}")
                reference = (
                    application_inventory(results["application"], case)
                    if "application" in results else ()
                )
                native_assessments = {
                    method: assess_native(results[method], reference, case)
                    for method in ("native_blind", "native_tracked")
                }
                visit_assessments = {}
                for method, assessments in native_assessments.items():
                    reference_active = any(item["reference_active"] for item in assessments)
                    candidate_active = any(item["candidate_active"] for item in assessments)
                    matched = any(item["matched_reference"] for item in assessments)
                    visit_assessments[method] = {
                        "reference_active": reference_active,
                        "candidate_active": candidate_active,
                        "matched_reference": matched,
                        "lost_reference_visit": reference_active and not matched,
                        "additional_or_mismatched_visit": candidate_active and not matched,
                    }
                method_comparison = []
                for receiver in (0, 1):
                    blind_assessment = native_assessments["native_blind"][receiver]
                    tracked_assessment = native_assessments["native_tracked"][receiver]
                    blind_pair = _get(results["native_blind"][receiver], "pair")
                    identity = dataset.associate_pair_to_reference(
                        results["native_tracked"][receiver],
                        (() if blind_pair is None else (blind_pair,)), case, receiver,
                    )
                    method_comparison.append({
                        "receiver": receiver,
                        "same_activity": (
                            blind_assessment["candidate_active"]
                            == tracked_assessment["candidate_active"]
                        ),
                        "tracked_associates_to_blind": (
                            not tracked_assessment["candidate_active"]
                            and not blind_assessment["candidate_active"]
                        ) or _matched(identity),
                        "association": jsonable(identity),
                    })
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
                    "outputs": {name: jsonable(value) for name, value in results.items()},
                    "output_sha256": {name: stable_hash(value) for name, value in results.items()},
                    "application_pair_inventory": jsonable(reference),
                    "application_truth_assessments": assess_application_truth(reference, case),
                    "native_assessments": native_assessments,
                    "visit_assessments": visit_assessments,
                    "native_method_comparison": method_comparison,
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
    source_stable = all(digest(name) == expected for name, expected in lock["files"].items())
    complete = status == "complete" and len(rows) == len(cases) and source_stable
    payload = {
        "schema": "org.leo.research.native-tradeoff-evaluation/v1",
        "stage": stage,
        "status": status,
        "error": error,
        "complete": complete,
        "source_lock": lock,
        "source_lock_stable": source_stable,
        "thread_environment": environment,
        "affinity_cpu": 0,
        "affinity_restored": sorted(affinity),
        "timeout_seconds": TIMEOUT_SECONDS[stage],
        "rows": rows,
        "summary": summarize(stage, rows),
        "holdout_opened": False,
        "validation_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"stage": stage, "status": status, "complete": complete,
                      "cases": len(rows)}), flush=True)


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


def _loss_band(lost: int, reference: int) -> str:
    if reference == 0:
        return "no_reference_positives"
    fraction = lost / reference
    if fraction == 0:
        return "0%"
    if fraction <= 0.01:
        return "<=1%"
    if fraction <= 0.03:
        return "<=3%"
    if fraction <= 0.05:
        return "<=5%"
    return ">5%"


def summarize(stage: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"by_rate": {}, "route_counts": {}}
    rates = sorted({row["rate_hz"] for row in rows})
    for rate in rates:
        selected = [row for row in rows if row["rate_hz"] == rate]
        methods: dict[str, Any] = {}
        for method in METHODS[stage]:
            cpu = [row["timings"][method]["process_cpu_ms"] for row in selected]
            wall = [row["timings"][method]["wall_ms"] for row in selected]
            methods[method] = {
                "process_cpu": _distribution(cpu),
                "wall": _distribution(wall),
            }
        if "application" in methods:
            application_cpu = methods["application"]["process_cpu"]["sum_ms"]
            for method in ("native_blind", "native_tracked"):
                native_cpu = methods[method]["process_cpu"]["sum_ms"]
                methods[method]["aggregate_cpu_speedup_vs_application"] = (
                    application_cpu / native_cpu if native_cpu else None
                )
        quality: dict[str, Any] = {}
        for method in ("native_blind", "native_tracked"):
            assessments = [item for row in selected for item in row["native_assessments"][method]]
            visit_assessments = [row["visit_assessments"][method] for row in selected]
            decisions = [decision for row in selected for decision in row["outputs"][method]]
            reference_count = sum(item["reference_active"] for item in assessments)
            matched = sum(item["matched_reference"] for item in assessments)
            lost = sum(item["lost_reference"] for item in assessments)
            additions = sum(item["additional_or_mismatched"] for item in assessments)
            active = sum(item["candidate_active"] for item in assessments)
            physical_outcomes: dict[str, int] = {}
            policy_passed = policy_failed = policy_report_only = 0
            for item in assessments:
                outcome = str(item["physical_outcome"])
                physical_outcomes[outcome] = physical_outcomes.get(outcome, 0) + 1
                if item["activity_policy_passed"] is True:
                    policy_passed += 1
                elif item["activity_policy_passed"] is False:
                    policy_failed += 1
                else:
                    policy_report_only += 1
            quality[method] = {
                "receiver_rows": len(assessments),
                "reference_positive_receivers": reference_count,
                "matched_reference_receivers": matched,
                "lost_reference_receivers": lost,
                "additional_or_mismatched_active_receivers": additions,
                "candidate_active_receivers": active,
                "reference_positive_visits": sum(
                    item["reference_active"] for item in visit_assessments
                ),
                "matched_reference_visits": sum(
                    item["matched_reference"] for item in visit_assessments
                ),
                "lost_reference_visits": sum(
                    item["lost_reference_visit"] for item in visit_assessments
                ),
                "additional_or_mismatched_active_visits": sum(
                    item["additional_or_mismatched_visit"] for item in visit_assessments
                ),
                "physical_outcomes": physical_outcomes,
                "required_policy_passed_receivers": policy_passed,
                "required_policy_failed_receivers": policy_failed,
                "report_only_receivers": policy_report_only,
                "miss_band": _loss_band(lost, reference_count),
                "work_counts": {
                    name: sum(int(decision[name]) for decision in decisions)
                    for name in (
                        "screened_probe_count", "guided_probe_count",
                        "blind_probe_count", "proposal_count", "scoring_count",
                    )
                },
            }
        result["by_rate"][str(rate)] = {"case_count": len(selected),
                                         "methods": methods, "quality": quality,
                                         "native_method_comparison": {
                                             "receiver_rows": 2 * len(selected),
                                             "same_activity": sum(
                                                 item["same_activity"]
                                                 for row in selected
                                                 for item in row["native_method_comparison"]
                                             ),
                                             "tracked_associates_to_blind": sum(
                                                 item["tracked_associates_to_blind"]
                                                 for row in selected
                                                 for item in row["native_method_comparison"]
                                             ),
                                         }}
    result["by_cohort"] = {}
    for cohort in sorted({row["cohort"] for row in rows}):
        selected = [row for row in rows if row["cohort"] == cohort]
        result["by_cohort"][cohort] = {
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
        for method in ("native_blind", "native_tracked"):
            outcomes: dict[str, int] = {}
            active = 0
            for row in selected:
                for assessment in row["native_assessments"][method]:
                    active += int(assessment["candidate_active"])
                    outcome = assessment["physical_outcome"]
                    outcomes[outcome] = outcomes.get(outcome, 0) + 1
            result["by_cohort"][cohort][method]["candidate_active_receivers"] = active
            result["by_cohort"][cohort][method]["physical_outcomes"] = outcomes
    result["timing_by_route_signature"] = {}
    for method in ("native_blind", "native_tracked"):
        signatures: dict[str, list[dict[str, float]]] = {}
        for row in rows:
            signature = "+".join(decision["route"] for decision in row["outputs"][method])
            signatures.setdefault(signature, []).append(row["timings"][method])
        result["timing_by_route_signature"][method] = {
            signature: {
                "process_cpu": _distribution([
                    item["process_cpu_ms"] for item in timings
                ]),
                "wall": _distribution([item["wall_ms"] for item in timings]),
            }
            for signature, timings in sorted(signatures.items())
        }
    for row in rows:
        for method in ("native_blind", "native_tracked"):
            for decision in row["outputs"][method]:
                route = str(decision.get("route", "missing"))
                key = f"{method}:{route}"
                result["route_counts"][key] = result["route_counts"].get(key, 0) + 1
    return result


def main() -> None:
    args = sys.argv[1:]
    if len(args) not in (2, 3) or args[0] != "--stage" or args[1] not in STAGES:
        raise ValueError(
            "usage: run_evaluation.py --stage controls|diagnostic|real [--freeze]"
        )
    stage = args[1]
    if len(args) == 3:
        if args[2] != "--freeze":
            raise ValueError("only --freeze is accepted after the stage")
        freeze(stage)
    else:
        execute_stage(stage)


if __name__ == "__main__":
    main()
