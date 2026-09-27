#!/usr/bin/env python3
"""Run the frozen lag-4 phase-CFO strategy on development and controls."""

from __future__ import annotations

import hashlib
import json
import platform
import signal
import statistics
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ACQUISITION = REPORT / "acquisition"
NATIVE = REPORT / "native"
DATASET = REPORT / "dataset"
CONTROL_DATASET = REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(ACQUISITION), str(NATIVE), str(REPORT), str(DEPLOY),
                str(DEPLOY / "src")]

import run_acquisition as common  # noqa: E402
from blind_strided_v4 import build_library_v4  # noqa: E402
from build import build, sha256  # noqa: E402
from phase_cfo import NativePhaseCFO  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import reference_match  # noqa: E402

RATES = (2_500_000, 5_000_000)
EXPECTED = {
    "development_manifest": "4874540dfe94bd5ced2d5496d6c53635de22c8f5d59d8edf0a159c62a899d401",
    "control_manifest": "ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48",
    "baseline_library": "8cdc21362e8cb98a21550b0ba2024674881ca106706d9c799b33e5d4f5a7e614",
    "baseline_receipt": "5103c6ebfde2a95e0ecdeec3c2e5c5c3253cf04aaca15da2fda1b5b6c0d1ee3e",
    "design": "c2e1bdb514f148e7f74e01239dec7d5b9e699498b09e3538f161994ba951c4fc",
}


def load_inputs() -> tuple[list[dict], list[dict]]:
    if sha256(DATASET / "cases.json") != EXPECTED["development_manifest"]:
        raise ValueError("development manifest changed")
    if sha256(CONTROL_DATASET / "cases.json") != EXPECTED["control_manifest"]:
        raise ValueError("control manifest changed")
    development_payload = json.loads((DATASET / "cases.json").read_text())
    control_payload = json.loads((CONTROL_DATASET / "cases.json").read_text())
    development = common.select_development(development_payload)
    controls = common.select_controls(control_payload)
    return development, controls


def fallback_reason(result) -> str | None:
    confirmation = result.confirmations[0]
    if not confirmation.candidate_count:
        return "no_candidate"
    if not confirmation.candidates[0].fractional_complete:
        return "fractional_incomplete"
    return None


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def run() -> dict:
    signal.alarm(300)
    design = json.loads((HERE / "design.json").read_text())
    if sha256(HERE / "design.json") != EXPECTED["design"]:
        raise ValueError("frozen design changed")
    development, controls = load_inputs()
    baseline_library = build_library_v4()
    candidate_library = build()
    baseline_receipt = baseline_library.with_name(baseline_library.name + ".build.json")
    if sha256(baseline_library) != EXPECTED["baseline_library"]:
        raise ValueError("baseline binary changed")
    if sha256(baseline_receipt) != EXPECTED["baseline_receipt"]:
        raise ValueError("baseline receipt changed")

    rows: list[dict] = []
    control_rows: list[dict] = []
    all_cases = development + controls
    geometries = {(case["rate_hz"], case["edge"]) for case in all_cases}
    repetitions = design["timing"]["repetitions"]
    with ExitStack() as stack:
        references = {
            geometry: stack.enter_context(NativeDwell(baseline_library, *geometry, 512))
            for geometry in geometries
        }
        fallbacks = {
            geometry: stack.enter_context(NativeDwell(baseline_library, *geometry, 512))
            for geometry in geometries
        }
        candidates = {
            geometry: stack.enter_context(NativePhaseCFO(*geometry))
            for geometry in geometries
        }

        def process(case: dict, root: Path, ordinal: int, control: bool) -> None:
            iq = common.load_iq(root, case)
            input_hash = hashlib.sha256(iq).hexdigest()
            geometry = case["rate_hz"], case["edge"]
            reference_engine = references[geometry]
            fallback_engine = fallbacks[geometry]
            phase_engine = candidates[geometry]
            for rx in range(2):
                view = iq[:, rx, :]

                def reference_call():
                    packed = np.ascontiguousarray(view)
                    result = reference_engine.run(packed, maximum=1, seeded=False)
                    return {"selected": result}

                def strategy_call():
                    attempt = phase_engine.run(view, maximum=1, seeded=False)
                    profile = phase_engine.profile()
                    reason = fallback_reason(attempt)
                    fallback = None
                    if reason is not None:
                        packed = np.ascontiguousarray(view)
                        fallback = fallback_engine.run(packed, maximum=1, seeded=False)
                    return {
                        "selected": attempt if fallback is None else fallback,
                        "attempt": attempt,
                        "fallback": fallback,
                        "fallback_reason": reason,
                        "profile": profile,
                    }

                warm = (reference_call, strategy_call)
                if (ordinal + rx) % 2:
                    warm = tuple(reversed(warm))
                for function in warm:
                    function()

                reference_runs, strategy_runs = [], []
                reference_times, strategy_times = [], []
                for repetition in range(repetitions):
                    order = (("reference", reference_call), ("strategy", strategy_call))
                    if (ordinal + rx + repetition) % 2:
                        order = tuple(reversed(order))
                    for name, function in order:
                        started_cpu = time.thread_time_ns()
                        started_wall = time.perf_counter_ns()
                        value = function()
                        timing = {
                            "cpu_ms": (time.thread_time_ns() - started_cpu) / 1e6,
                            "wall_ms": (time.perf_counter_ns() - started_wall) / 1e6,
                        }
                        if name == "reference":
                            reference_runs.append(value)
                            reference_times.append(timing)
                        else:
                            strategy_runs.append(value)
                            strategy_times.append(timing)

                reference_signatures = [
                    common.scientific_signature(value["selected"])
                    for value in reference_runs
                ]
                strategy_signatures = [
                    (
                        common.scientific_signature(value["attempt"]),
                        common.scientific_signature(value["selected"]),
                        value["fallback_reason"],
                    )
                    for value in strategy_runs
                ]
                if len(set(reference_signatures)) != 1:
                    raise ValueError("reference result changed across repetitions")
                if len(set(strategy_signatures)) != 1:
                    raise ValueError("strategy result changed across repetitions")
                reference_result = reference_runs[0]["selected"]
                strategy = strategy_runs[0]
                selected_result = strategy["selected"]
                reference_observation = common.result_observation(reference_result)
                selected_observation = common.result_observation(selected_result)
                matched = bool(
                    reference_observation and selected_observation
                    and reference_match(reference_observation, selected_observation,
                                        case["rate_hz"])
                )
                reference_compact = common.compact_result(reference_result)
                selected_compact = common.compact_result(selected_result)
                attempt_compact = common.compact_result(strategy["attempt"])
                strategy_fine = []
                for value in strategy_runs:
                    cost = float(value["attempt"].confirmations[0].fine_cpu_ms)
                    if value["fallback"] is not None:
                        cost += float(value["fallback"].confirmations[0].fine_cpu_ms)
                    strategy_fine.append(cost)
                row = {
                    "case_id": case["case_id"],
                    "session_id": case.get("session_id"),
                    "visit_index": case.get("visit_index"),
                    "source_start_counter": case.get("source_start_counter"),
                    "rate_hz": case["rate_hz"],
                    "edge": case["edge"],
                    "channel": case["channel"],
                    "rx": rx,
                    "reference": reference_compact,
                    "candidate": selected_compact,
                    "phase_attempt": attempt_compact,
                    "fallback_used": strategy["fallback"] is not None,
                    "fallback_reason": strategy["fallback_reason"],
                    "matched_reference": matched,
                    "drift": common.comparison_drift(
                        reference_compact, selected_compact, case["rate_hz"]
                    ),
                    "baseline_timing": common.median_timing(reference_times),
                    "candidate_timing": common.median_timing(strategy_times),
                    "reference_fine_cpu_ms": median([
                        float(value["selected"].confirmations[0].fine_cpu_ms)
                        for value in reference_runs
                    ]),
                    "strategy_fine_cpu_ms": median(strategy_fine),
                    "phase_proposal_cpu_ms": median([
                        float(value["profile"]["acquisition_fft_cpu_ms"])
                        for value in strategy_runs
                    ]),
                    "phase_conditioned_cpu_ms": median([
                        float(value["profile"]["conditioned_cpu_ms"])
                        for value in strategy_runs
                    ]),
                    "baseline_timings": reference_times,
                    "candidate_timings": strategy_times,
                }
                if control:
                    row["truth_kind"] = case["truth"]["kind"]
                    row["starlink_model_present"] = case["truth"]["starlink_model_present"]
                    control_rows.append(row)
                else:
                    rows.append(row)
            if hashlib.sha256(iq).hexdigest() != input_hash:
                raise ValueError("caller IQ changed")

        for ordinal, case in enumerate(development):
            process(case, DATASET, ordinal, False)
        for ordinal, case in enumerate(controls, start=len(development)):
            process(case, CONTROL_DATASET, ordinal, True)

    summary = {
        "all": common.summarize(rows),
        "by_rate": {
            str(rate): common.summarize([row for row in rows if row["rate_hz"] == rate])
            for rate in RATES
        },
    }
    stage = {}
    for rate in RATES:
        subset = [row for row in rows if row["rate_hz"] == rate]
        reference_fine = sum(row["reference_fine_cpu_ms"] for row in subset)
        strategy_fine = sum(row["strategy_fine_cpu_ms"] for row in subset)
        stage[str(rate)] = {
            "receiver_visits": len(subset),
            "fallbacks": sum(row["fallback_used"] for row in subset),
            "reference_fine_cpu_ms": reference_fine,
            "strategy_fine_cpu_ms": strategy_fine,
            "fine_stage_speedup": reference_fine / strategy_fine,
            "phase_proposal_cpu_ms": sum(row["phase_proposal_cpu_ms"] for row in subset),
            "phase_conditioned_cpu_ms": sum(
                row["phase_conditioned_cpu_ms"] for row in subset
            ),
        }
    control_changes = sum(
        row["reference"]["positive"] != row["candidate"]["positive"]
        for row in control_rows
    )
    gates = {
        "matched_36_of_36": summary["all"]["matched_reference_positives"] == 36,
        "no_control_decision_changes": control_changes == 0,
        "fractional_complete_for_matched": all(
            row["candidate"]["fractional_complete"]
            for row in rows if row["matched_reference"]
        ),
        "fine_stage_2x_each_rate": all(
            stage[str(rate)]["fine_stage_speedup"] >= 2 for rate in RATES
        ),
        "full_caller_1_05x_each_rate": all(
            summary["by_rate"][str(rate)]["costs"]["cpu_speedup"] >= 1.05
            for rate in RATES
        ),
    }
    gates["passed"] = all(gates.values())
    return {
        "schema": "org.leo.research.phase-cfo-results/v1",
        "scope": "full development and supported controls; explicit failure fallback; no holdout",
        "fresh_holdout_opened": False,
        "design_sha256": sha256(HERE / "design.json"),
        "runner_sha256": sha256(Path(__file__)),
        "dataset_cases_sha256": sha256(DATASET / "cases.json"),
        "control_cases_sha256": sha256(CONTROL_DATASET / "cases.json"),
        "baseline_library_sha256": sha256(baseline_library),
        "candidate_library_sha256": sha256(candidate_library),
        "candidate_build_receipt_sha256": sha256(
            candidate_library.with_name(candidate_library.name + ".build.json")
        ),
        "host": platform.uname()._asdict(),
        "summary": summary,
        "stage_summary": stage,
        "fallback_summary": {
            "development": {
                reason: sum(row["fallback_reason"] == reason for row in rows)
                for reason in ("no_candidate", "fractional_incomplete")
            },
            "controls": {
                reason: sum(row["fallback_reason"] == reason for row in control_rows)
                for reason in ("no_candidate", "fractional_incomplete")
            },
        },
        "control_summary": common.summarize_controls(control_rows),
        "control_decision_changes": control_changes,
        "gates": gates,
        "rows": rows,
        "control_rows": control_rows,
        "limitations": [
            "FP64 V4 is a detector reference, not physical truth",
            "5 Msps development contains no reference positives",
            "complete margin-negative phase results do not trigger oracle-dependent fallback",
            "server timing is not ARM timing",
        ],
    }


def main() -> None:
    output = HERE / "results.json"
    if output.exists():
        raise FileExistsError(output)
    result = run()
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({
        "summary": result["summary"],
        "stage_summary": result["stage_summary"],
        "fallback_summary": result["fallback_summary"],
        "control_summary": result["control_summary"],
        "gates": result["gates"],
    }, indent=2))


if __name__ == "__main__":
    main()
