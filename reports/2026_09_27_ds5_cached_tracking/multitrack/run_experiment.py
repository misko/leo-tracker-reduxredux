#!/usr/bin/env python3
"""Causal full-aperture replay with a bounded bank of independent tracks."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import platform
import signal
import sys
import time
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NATIVE = ROOT / "native"
NEW_DATA = ROOT / "new_data"
CONTROL_DATASET = ROOT.parent / "2026_09_26_ds5_server_eval" / "dataset"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(ROOT), str(NATIVE), str(DEPLOY), str(DEPLOY / "src")]

from bank import MultiTrackBank  # noqa: E402
from blind_strided_v4 import NativeStridedBlindV4, build_library_v4  # noqa: E402
from known_state_v3 import NativeKnownStateV3  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import Key, Observation, Policy, reference_match  # noqa: E402

RATES = (2_500_000, 5_000_000)
NEW_DATA_SHA256 = "b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845"
CONTROL_SHA256 = "ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48"
BASELINE_SHA256 = "8cdc21362e8cb98a21550b0ba2024674881ca106706d9c799b33e5d4f5a7e614"
BASELINE_RECEIPT_SHA256 = "5103c6ebfde2a95e0ecdeec3c2e5c5c3253cf04aaca15da2fda1b5b6c0d1ee3e"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scientific(value):
    if isinstance(value, ct.Structure):
        return {
            name: scientific(getattr(value, name))
            for name, _ in value._fields_
            if "cpu_ms" not in name and "wall_ms" not in name
        }
    if isinstance(value, ct.Array):
        return [scientific(item) for item in value]
    return value


def confirmation_observation(result, confirmation_index: int) -> Observation | None:
    if confirmation_index >= result.confirmation_count:
        return None
    confirmation = result.confirmations[confirmation_index]
    if not confirmation.candidate_count:
        return None
    candidate = confirmation.candidates[0]
    return Observation(
        int(result.rank.order[confirmation_index]),
        candidate.epoch + candidate.fractional_offset_samples,
        candidate.tracking_cfo_hz,
        candidate.exact_score,
        candidate.control_score,
        bool(candidate.fractional_complete),
        "fitted",
        candidate.acquired_cfo_hz,
    )


def blind_observations(result) -> list[Observation]:
    return [
        observation
        for index in range(int(result.confirmation_count))
        if (observation := confirmation_observation(result, index)) is not None
    ]


def fast_observation(result: dict, window: int) -> Observation:
    return Observation(
        window,
        result["epoch_samples"],
        result["tracking_cfo_hz"],
        result["exact_score"],
        result["control_score"],
        bool(
            result["valid_bounds"]
            and result["support_frames"] >= 2
            and result["scored_fractional"]
            and not result["needs_reacquire"]
        ),
        result["timing_semantics"],
        result["scoring_cfo_hz"],
    )


def timed(function, repetitions: int):
    expected, _ = function()
    measurements = []
    detail = None
    for _ in range(repetitions):
        cpu = time.process_time_ns()
        wall = time.perf_counter_ns()
        actual, detail = function()
        measurements.append({
            "cpu_ms": (time.process_time_ns() - cpu) / 1e6,
            "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
        })
        if actual != expected:
            raise ValueError("DSP observation changed across identical repetitions")
    return expected, detail, measurements


def load_case(dataset_root: Path, case: dict) -> np.ndarray:
    path = (dataset_root / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(dataset_root.resolve()):
        raise ValueError("IQ path escapes dataset")
    if sha256(path) != case["raw_npy"]["sha256"].removeprefix("sha256:"):
        raise ValueError("IQ hash mismatch")
    raw = np.load(path, allow_pickle=False)
    expected = (case["rate_hz"] * 120 // 1000, 2, 2)
    if raw.dtype != np.dtype("<i2") or raw.shape != expected:
        raise ValueError("unexpected IQ geometry")
    return raw


def summarize(rows: list[dict]) -> dict:
    def group(subset: list[dict]) -> dict:
        costs = {
            side: {
                metric: sum(median(row[side][i][metric] for i in range(len(row[side])))
                            for row in subset)
                for metric in ("cpu_ms", "wall_ms")
            }
            for side in ("baseline_times", "candidate_times")
        }
        candidate_cpu = costs["candidate_times"]["cpu_ms"]
        candidate_wall = costs["candidate_times"]["wall_ms"]
        return {
            "receiver_visits": len(subset),
            "actions": dict(Counter(row["reason"] for row in subset)),
            "reference_positives": sum(row["reference_positive"] for row in subset),
            "candidate_positives": sum(row["candidate_positive"] for row in subset),
            "matched_reference_positives": sum(row["matched_reference"] for row in subset),
            "lost_reference_positives": sum(
                row["reference_positive"] and not row["matched_reference"] for row in subset
            ),
            "additional_positive_cases": sum(
                row["candidate_positive"] and not row["matched_reference"] for row in subset
            ),
            "cache_attempt_visits": sum(row["cache_check_count"] > 0 for row in subset),
            "cache_checks": sum(row["cache_check_count"] for row in subset),
            "cache_hits": sum(not row["used_blind"] for row in subset),
            "ambiguous_cache_hits": sum(len(row["accepted_track_ids"]) > 1 for row in subset),
            "blind_calls": sum(row["used_blind"] for row in subset),
            "blind_confirmations": sum(row["blind_confirmation_count"] for row in subset),
            "maximum_bank_size": max((row["bank_size_after"] for row in subset), default=0),
            "costs": costs,
            "cpu_speedup": costs["baseline_times"]["cpu_ms"] / candidate_cpu
            if candidate_cpu else None,
            "wall_speedup": costs["baseline_times"]["wall_ms"] / candidate_wall
            if candidate_wall else None,
        }

    return {
        "all_visits": group(rows),
        "by_rate": {
            str(rate): group([row for row in rows if row["rate_hz"] == rate])
            for rate in RATES
        },
    }


def run() -> dict:
    signal.alarm(300)
    design = json.loads((HERE / "design.json").read_text())
    dataset_path = NEW_DATA / "cases.json"
    control_path = CONTROL_DATASET / "cases.json"
    if sha256(dataset_path) != NEW_DATA_SHA256:
        raise ValueError("new-data manifest changed")
    if sha256(control_path) != CONTROL_SHA256:
        raise ValueError("control manifest changed")
    payload = json.loads(dataset_path.read_text())
    cases = sorted(payload["cases"], key=lambda case: (case["session_id"], case["visit_index"]))
    if len(cases) != 128 or any(case["split"] != "dev" for case in cases):
        raise ValueError("unexpected new-data inventory")
    control_payload = json.loads(control_path.read_text())
    controls = [
        case for case in control_payload["cases"]
        if case["split"] == "control" and case["rate_hz"] in RATES
    ]
    if len(controls) != 12:
        raise ValueError("unexpected supported control inventory")

    library = build_library_v4()
    receipt_path = library.with_name(library.name + ".build.json")
    receipt = json.loads(receipt_path.read_text())
    if sha256(library) != BASELINE_SHA256 or sha256(receipt_path) != BASELINE_RECEIPT_SHA256:
        raise ValueError("frozen V4 binary or receipt changed")
    if sha256(library) != receipt["binary_sha256"]:
        raise ValueError("V4 binary does not match receipt")
    for source, expected in receipt["sources_sha256"].items():
        if sha256(Path(source)) != expected:
            raise ValueError(f"V4 source changed: {source}")

    policy = Policy(
        max_age_seconds=2.0,
        discovery_interval=32,
        maximum_cfo_innovation_hz=8000.0,
        maximum_cfo_rate_hz_per_s=5000.0,
        maximum_timing_innovation_seconds=4e-6,
        maximum_clock_error_ppm=50.0,
        learning_cfo_slack_hz=2000.0,
        use_cfo_rate=True,
    )
    bank = MultiTrackBank(policy, maximum_tracks=3)
    repetitions = design["timing"]["repetitions"]
    rows, control_rows = [], []
    source_paths = [
        HERE / "design.json",
        HERE / "bank.py",
        Path(__file__),
        ROOT / "tracking.py",
        NATIVE / "known_state_v3.py",
        NATIVE / "blind_strided_v4.py",
    ]
    source_hashes = {str(path.resolve()): sha256(path) for path in source_paths}

    geometries = {(case["rate_hz"], case["edge"]) for case in cases + controls}
    with ExitStack() as stack:
        references = {
            geometry: stack.enter_context(NativeDwell(library, *geometry, 512))
            for geometry in geometries
        }
        fast = {
            geometry: stack.enter_context(NativeKnownStateV3(*geometry, library=library))
            for geometry in geometries
        }
        fallback = {
            geometry: stack.enter_context(
                NativeStridedBlindV4(*geometry, library=library, bins=512)
            )
            for geometry in geometries
        }

        for ordinal, case in enumerate(cases):
            raw = load_case(NEW_DATA, case)
            original_hash = hashlib.sha256(raw).hexdigest()
            rate = case["rate_hz"]
            geometry = rate, case["edge"]
            for rx in range(2):
                key = Key(case["session_id"], rx, case["channel"], case["edge"], rate)
                start, index = case["source_start_counter"], case["visit_index"]

                def reference_call():
                    packed = np.ascontiguousarray(raw[:, rx, :])
                    result = references[geometry].run(packed, maximum=1, seeded=False)
                    return confirmation_observation(result, 0), result

                reference_first = (ordinal + rx) % 2 == 0
                if reference_first:
                    reference, reference_detail, baseline_times = timed(
                        reference_call, repetitions
                    )

                state_cpu, state_wall = time.process_time_ns(), time.perf_counter_ns()
                plan = bank.begin(key, start, index)
                state_cpu = (time.process_time_ns() - state_cpu) / 1e6
                state_wall = (time.perf_counter_ns() - state_wall) / 1e6
                action_times: list[list[dict]] = []
                checks = []
                observations: dict[int, Observation] = {}
                for planned in plan.tracks:
                    left = planned.prediction.window * (rate // 50)

                    def check_call(planned=planned, left=left):
                        selected = raw[left:left + rate // 50, rx, :]
                        scoring_cfo = planned.prediction.scoring_cfo_hz
                        result = fast[geometry].measure(
                            selected,
                            planned.prediction.epoch_samples,
                            scoring_cfo,
                            expected_physical_cfo_hz=planned.prediction.cfo_hz,
                            recover_timing=False,
                            frame_limit=16,
                        )
                        result["scoring_cfo_hz"] = scoring_cfo
                        return fast_observation(result, planned.prediction.window), result

                    observation, detail, timings = timed(check_call, repetitions)
                    observations[planned.track_id] = observation
                    action_times.append(timings)
                    checks.append({
                        "track_id": planned.track_id,
                        "prediction": asdict(planned.prediction),
                        "observation": asdict(observation),
                        "detail": detail,
                    })

                state_started_cpu, state_started_wall = (
                    time.process_time_ns(), time.perf_counter_ns()
                )
                selection = bank.accept_cached(plan, observations) if plan.tracks else None
                state_cpu += (time.process_time_ns() - state_started_cpu) / 1e6
                state_wall += (time.perf_counter_ns() - state_started_wall) / 1e6
                used_blind = selection is None or selection.observation is None
                blind_result = None
                blind_confirmation_count = 0
                discovery_track_ids: tuple[int, ...] = ()
                if used_blind:
                    def fallback_call():
                        result = fallback[geometry].run(
                            raw[:, rx, :], maximum=3, seeded=False
                        )
                        return confirmation_observation(result, 0), result

                    observation, blind_result, timings = timed(fallback_call, repetitions)
                    action_times.append(timings)
                    discovered = blind_observations(blind_result)
                    blind_confirmation_count = int(blind_result.confirmation_count)
                    state_started_cpu, state_started_wall = (
                        time.process_time_ns(), time.perf_counter_ns()
                    )
                    discovery_track_ids = bank.discover(plan, discovered)
                    state_cpu += (time.process_time_ns() - state_started_cpu) / 1e6
                    state_wall += (time.perf_counter_ns() - state_started_wall) / 1e6
                    reason = plan.reason if not plan.tracks else "failed_bank"
                    selected_track_id = None
                    accepted_track_ids: tuple[int, ...] = ()
                    rejected_track_ids = tuple(item.track_id for item in plan.tracks)
                else:
                    observation = selection.observation
                    reason = "cache_hit"
                    selected_track_id = selection.selected_track_id
                    accepted_track_ids = selection.accepted_track_ids
                    rejected_track_ids = selection.rejected_track_ids

                candidate_times = [
                    {
                        metric: sum(action[rep][metric] for action in action_times)
                        + (state_cpu if metric == "cpu_ms" else state_wall)
                        for metric in ("cpu_ms", "wall_ms")
                    }
                    for rep in range(repetitions)
                ]
                if not reference_first:
                    reference, reference_detail, baseline_times = timed(
                        reference_call, repetitions
                    )
                blind_top_equal = None
                if used_blind:
                    blind_top_equal = observation == reference
                    if not blind_top_equal:
                        raise ValueError("strided fallback top differs from packed reference")
                matched = bool(
                    reference and observation and reference_match(reference, observation, rate)
                )
                rows.append({
                    "case_id": case["case_id"],
                    "session_id": case["session_id"],
                    "visit_index": index,
                    "block_offset": case["block_offset"],
                    "rate_hz": rate,
                    "edge": case["edge"],
                    "channel": case["channel"],
                    "rx": rx,
                    "start_counter": start,
                    "end_counter": case["source_end_counter_exclusive"],
                    "reason": reason,
                    "plan_reason": plan.reason,
                    "cache_check_count": len(plan.tracks),
                    "cache_checks": checks,
                    "selected_track_id": selected_track_id,
                    "accepted_track_ids": list(accepted_track_ids),
                    "rejected_track_ids": list(rejected_track_ids),
                    "ambiguity_count": len(accepted_track_ids),
                    "used_blind": used_blind,
                    "blind_confirmation_count": blind_confirmation_count,
                    "blind_top_equal_reference": blind_top_equal,
                    "discovery_track_ids": list(discovery_track_ids),
                    "bank_size_after": len(bank.tracks(key)),
                    "global_accepted_since_discovery": bank.accepted_since_discovery(key),
                    "reference": asdict(reference) if reference else None,
                    "observation": asdict(observation) if observation else None,
                    "matched_reference": matched,
                    "reference_positive": bool(reference and reference.positive),
                    "candidate_positive": bool(observation and observation.positive),
                    "reference_timed_first": reference_first,
                    "baseline_times": baseline_times,
                    "candidate_times": candidate_times,
                })
            if hashlib.sha256(raw).hexdigest() != original_hash:
                raise ValueError("caller IQ mutated")

        # Controls are isolated cold acquisitions. They test acquisition only.
        for ordinal, case in enumerate(controls):
            raw = load_case(CONTROL_DATASET, case)
            rate = case["rate_hz"]
            geometry = rate, case["edge"]
            for rx in range(2):
                def reference_call():
                    packed = np.ascontiguousarray(raw[:, rx, :])
                    result = references[geometry].run(packed, maximum=1, seeded=False)
                    return confirmation_observation(result, 0), result

                def candidate_call():
                    result = fallback[geometry].run(raw[:, rx, :], maximum=3, seeded=False)
                    return confirmation_observation(result, 0), result

                if (ordinal + rx) % 2:
                    candidate, candidate_detail, candidate_times = timed(
                        candidate_call, repetitions
                    )
                    reference, reference_detail, baseline_times = timed(
                        reference_call, repetitions
                    )
                else:
                    reference, reference_detail, baseline_times = timed(
                        reference_call, repetitions
                    )
                    candidate, candidate_detail, candidate_times = timed(
                        candidate_call, repetitions
                    )
                if candidate != reference:
                    raise ValueError("control candidate top differs from packed reference")
                control_rows.append({
                    "case_id": case["case_id"],
                    "rate_hz": rate,
                    "edge": case["edge"],
                    "rx": rx,
                    "truth_kind": case["truth"]["kind"],
                    "starlink_model_present": case["truth"]["starlink_model_present"],
                    "reference_positive": bool(reference and reference.positive),
                    "candidate_positive": bool(candidate and candidate.positive),
                    "candidate_confirmation_count": int(candidate_detail.confirmation_count),
                    "baseline_times": baseline_times,
                    "candidate_times": candidate_times,
                })

    summary = summarize(rows)
    control_changes = sum(
        row["reference_positive"] != row["candidate_positive"] for row in control_rows
    )
    gates = {
        "identity_129_of_129": (
            summary["all_visits"]["reference_positives"] == 129
            and summary["all_visits"]["matched_reference_positives"] == 129
        ),
        "zero_additional_positives": summary["all_visits"]["additional_positive_cases"] == 0,
        "zero_control_decision_changes": control_changes == 0,
        "overall_cpu_speedup_at_least_1_797": summary["all_visits"]["cpu_speedup"] >= 1.797,
        "each_rate_cpu_speedup_at_least_1": all(
            summary["by_rate"][str(rate)]["cpu_speedup"] >= 1 for rate in RATES
        ),
        "full_coverage": len(rows) == 256 and all(row["observation"] is not None for row in rows),
    }
    gates["passed"] = all(gates.values())
    if source_hashes != {str(path.resolve()): sha256(path) for path in source_paths}:
        raise ValueError("source changed during replay")
    for source, expected in receipt["sources_sha256"].items():
        if sha256(Path(source)) != expected:
            raise ValueError("V4 source changed during replay")
    return {
        "schema": "org.leo.research.multitrack-results/v1",
        "scope": "causal new-development server replay plus isolated controls; no holdout",
        "fresh_holdout_opened": False,
        "dataset_sha256": sha256(dataset_path),
        "control_dataset_sha256": sha256(control_path),
        "design_sha256": sha256(HERE / "design.json"),
        "source_sha256": source_hashes,
        "native_sha256": sha256(library),
        "native_build_receipt_sha256": sha256(receipt_path),
        "host": platform.uname()._asdict(),
        "summary": summary,
        "control_summary": {
            "receiver_controls": len(control_rows),
            "decision_changes": control_changes,
            "by_kind": {
                kind: {
                    "receiver_controls": sum(row["truth_kind"] == kind for row in control_rows),
                    "reference_positive": sum(
                        row["truth_kind"] == kind and row["reference_positive"]
                        for row in control_rows
                    ),
                    "candidate_positive": sum(
                        row["truth_kind"] == kind and row["candidate_positive"]
                        for row in control_rows
                    ),
                }
                for kind in ("pilot", "noise", "tone")
            },
            "interpretation": "isolated cold acquisitions; controls do not test bank state",
        },
        "gates": gates,
        "rows": rows,
        "control_rows": control_rows,
        "limitations": [
            "independent blind top is a detector reference, not physical truth",
            "all lower-window blind observations are strategy-owned but only top is its output",
            "2us/8kHz discovery association is conservative and can split a moving trajectory",
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
        "control_summary": result["control_summary"],
        "gates": result["gates"],
    }, indent=2))


if __name__ == "__main__":
    main()
