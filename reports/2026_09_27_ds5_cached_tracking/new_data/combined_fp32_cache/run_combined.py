#!/usr/bin/env python3
"""Measure unchanged V6 cache with FP32 FFTW blind fallback on new development IQ."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import signal
import sys
import time
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent.parent
NATIVE = REPORT / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
DATASET = HERE.parent / "cases.json"
FP64 = NATIVE / "libblind_strided_v4.so"
FP32 = REPORT / "fft32" / "libfft32_fftw.so"
FFTW = Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3.6.10")
sys.path[:0] = [str(REPORT), str(NATIVE), str(DEPLOY), str(DEPLOY / "src")]

import replay as frozen_replay  # noqa: E402
from blind_strided_v4 import NativeStridedBlindV4  # noqa: E402
from known_state_v3 import NativeKnownStateV3  # noqa: E402
from stress import cache_lookup  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import Key, Policy, Tracker, circular_samples, reference_match  # noqa: E402


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return "sha256:" + result.hexdigest()


def verify_source_lock() -> tuple[dict, dict]:
    design = json.loads((HERE / "design.json").read_text())
    lock = json.loads((HERE / "source_lock.json").read_text())
    checks = {
        HERE / "design.json": lock["design_sha256"],
        Path(__file__): lock["adapter_sha256"],
        DATASET: design["dataset_cases_sha256"],
        REPORT / "config.dev.v6.strided.json": design["v6_config_sha256"],
        REPORT / "replay.py": design["v6_replay_sha256"],
        REPORT / "tracking.py": design["tracking_sha256"],
        REPORT / "stress.py": design["stress_sha256"],
        NATIVE / "known_state_v3.py": design["known_state_v3_python_sha256"],
        NATIVE / "blind_strided_v4.py": design["blind_strided_v4_python_sha256"],
        FP64: design["fp64_library_sha256"],
        FP64.with_name(FP64.name + ".build.json"): design["fp64_build_receipt_sha256"],
        FP32: design["fp32_fftw_library_sha256"],
        FP32.with_name(FP32.name + ".build.json"): design["fp32_fftw_build_receipt_sha256"],
        FFTW: design["server_fftw_library_sha256"],
    }
    if lock.get("stage") != "frozen_before_combined_outcomes":
        raise ValueError("combined source lock is not frozen")
    for path, expected in checks.items():
        if digest(path) != expected:
            raise ValueError(f"frozen combined input changed: {path}")
    receipt = json.loads(FP32.with_name(FP32.name + ".build.json").read_text())
    if receipt.get("semantics") != "FP32 FFTW all FFTs, ESTIMATE plans; not bit-equivalent":
        raise ValueError("fallback build is not the frozen FP32 FFTW backend")
    return design, lock


def load_iq(case: dict) -> np.ndarray:
    path = (DATASET.parent / case["raw_npy"]["path"]).resolve()
    if (
        not path.is_relative_to(DATASET.parent.resolve())
        or digest(path) != case["raw_npy"]["sha256"]
    ):
        raise ValueError(f"IQ path or hash changed: {case['case_id']}")
    values = np.load(path, allow_pickle=False)
    if values.dtype != np.dtype("<i2") or values.shape != (
        case["rate_hz"] * 120 // 1000,
        2,
        2,
    ):
        raise ValueError(f"IQ geometry changed: {case['case_id']}")
    return values


def update_candidate_state(tracker, key, start, index, observation, used_blind):
    """Advance state only from this visit's candidate observation."""
    if observation is None:
        return False
    return tracker.update(key, start, index, observation, discovery=used_blind)


def comparison(reference, candidate, rate_hz: int) -> dict:
    if reference is None or candidate is None:
        return {"timing_error_us": None, "cfo_error_hz": None}
    delta = (reference.window - candidate.window) * (rate_hz // 50)
    delta += reference.epoch_samples - candidate.epoch_samples
    return {
        "timing_error_us": abs(circular_samples(delta, rate_hz)) / rate_hz * 1e6,
        "cfo_error_hz": abs(reference.cfo_hz - candidate.cfo_hz),
    }


def identity_summary(rows: list[dict]) -> dict:
    paired = [row["comparison"] for row in rows if row["comparison"]["timing_error_us"] is not None]
    reference_positives = sum(row["reference_positive"] for row in rows)
    matched = sum(row["matched_reference"] for row in rows)
    extras = sum(row["candidate_positive"] and not row["matched_reference"] for row in rows)
    fallback_rows = [row for row in rows if row["used_blind"]]
    return {
        "receiver_visits": len(rows),
        "reference_positives": reference_positives,
        "matched_reference_positives": matched,
        "lost_reference_positives": reference_positives - matched,
        "additional_candidate_positives": extras,
        "max_paired_timing_error_us": max((row["timing_error_us"] for row in paired), default=0.0),
        "max_paired_cfo_error_hz": max((row["cfo_error_hz"] for row in paired), default=0.0),
        "fallback_calls": len(fallback_rows),
        "fallback_selected_window_changes": sum(
            row["fallback_selected_window_changed"] for row in fallback_rows
        ),
        "fallback_rank_order_changes": sum(
            row["fallback_rank_order_changed"] for row in fallback_rows
        ),
        "gate_pass": matched == reference_positives and extras == 0,
    }


def run() -> dict:
    signal.alarm(240)
    design, lock = verify_source_lock()
    payload = json.loads(DATASET.read_text())
    cases = sorted(
        (case for case in payload["cases"] if case["split"] == "dev"),
        key=lambda case: (case["session_id"], case["visit_index"]),
    )
    if len(cases) != 128 or {case["rate_hz"] for case in cases} != {2_500_000, 5_000_000}:
        raise ValueError("combined replay requires the frozen 128-visit new-development split")
    policy = Policy(**design["policy"])
    tracker = Tracker(policy)
    rows = []
    geometries = {(case["rate_hz"], case["edge"]) for case in cases}
    initialization_started = time.perf_counter()
    with ExitStack() as stack:
        references = {
            geometry: stack.enter_context(NativeDwell(FP64, *geometry, 512))
            for geometry in geometries
        }
        fast = {
            geometry: stack.enter_context(NativeKnownStateV3(*geometry, library=FP64))
            for geometry in geometries
        }
        fallbacks = {
            geometry: stack.enter_context(NativeStridedBlindV4(*geometry, library=FP32, bins=512))
            for geometry in geometries
        }
        initialization_seconds = time.perf_counter() - initialization_started
        for case in cases:
            raw = load_iq(case)
            original_hash = hashlib.sha256(raw).hexdigest()
            rate = case["rate_hz"]
            geometry = (rate, case["edge"])
            for rx in range(2):
                key = Key(case["session_id"], rx, case["channel"], case["edge"], rate)
                start = case["source_start_counter"]
                index = case["visit_index"]

                def acquire_reference(raw=raw, rx=rx, geometry=geometry):
                    packed = np.ascontiguousarray(raw[:, rx, :])
                    return references[geometry].run(packed, maximum=1, seeded=False)

                def acquire_fallback(raw=raw, rx=rx, geometry=geometry):
                    return fallbacks[geometry].run(raw[:, rx, :], maximum=1, seeded=False)

                reference_first = (index + rx) % 2 == 0
                if reference_first:
                    reference, reference_detail, baseline_times = frozen_replay.timed(
                        lambda: (
                            frozen_replay.blind_observation(result := acquire_reference()),
                            result,
                        ),
                        3,
                    )
                overhead_cpu = time.process_time_ns()
                overhead_wall = time.perf_counter_ns()
                with cache_lookup(
                    tracker, key, case["block_offset"], "primary", payload["stress_protocol"]
                ):
                    prediction, reason = tracker.begin(key, start, index)
                state_cpu = (time.process_time_ns() - overhead_cpu) / 1e6
                state_wall = (time.perf_counter_ns() - overhead_wall) / 1e6
                action_times = []
                candidate = None
                candidate_detail = None
                used_blind = False
                attempted_cache = prediction is not None
                if prediction is not None:
                    left = prediction.window * (rate // 50)

                    def measure(
                        raw=raw,
                        left=left,
                        rate=rate,
                        rx=rx,
                        geometry=geometry,
                        prediction=prediction,
                    ):
                        values = raw[left : left + rate // 50, rx, :]
                        result = fast[geometry].measure(
                            values,
                            prediction.epoch_samples,
                            prediction.scoring_cfo_hz,
                            recover_timing=False,
                            frame_limit=design["known_state"]["frame_limit"],
                            expected_physical_cfo_hz=prediction.cfo_hz,
                        )
                        result["scoring_cfo_hz"] = prediction.scoring_cfo_hz
                        return frozen_replay.fast_observation(result, prediction.window), result

                    candidate, candidate_detail, timings = frozen_replay.timed(measure, 3)
                    action_times.append(timings)
                    if not tracker.accepts(key, prediction, candidate):
                        candidate = None
                        reason = "failed_prediction"
                    else:
                        reason = "cache_hit"
                if candidate is None:
                    candidate, candidate_detail, timings = frozen_replay.timed(
                        lambda: (
                            frozen_replay.blind_observation(result := acquire_fallback()),
                            result,
                        ),
                        3,
                    )
                    action_times.append(timings)
                    used_blind = True
                overhead_cpu = time.process_time_ns()
                overhead_wall = time.perf_counter_ns()
                state_updated = update_candidate_state(
                    tracker, key, start, index, candidate, used_blind
                )
                state_cpu += (time.process_time_ns() - overhead_cpu) / 1e6
                state_wall += (time.perf_counter_ns() - overhead_wall) / 1e6
                candidate_times = [
                    {
                        metric: sum(action[i][metric] for action in action_times)
                        + (state_cpu if metric == "cpu_ms" else state_wall)
                        for metric in ("cpu_ms", "wall_ms")
                    }
                    for i in range(3)
                ]
                if not reference_first:
                    reference, reference_detail, baseline_times = frozen_replay.timed(
                        lambda: (
                            frozen_replay.blind_observation(result := acquire_reference()),
                            result,
                        ),
                        3,
                    )
                matched = bool(
                    reference
                    and candidate
                    and reference_match(reference, candidate, case["rate_hz"])
                )
                rows.append(
                    {
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
                        "attempted_cache": attempted_cache,
                        "used_blind": used_blind,
                        "fallback_backend": "fp32_fftw" if used_blind else None,
                        "state_update_source": "candidate_observation" if state_updated else None,
                        "reference_used_for_state": False,
                        "prediction": asdict(prediction) if prediction else None,
                        "reference": asdict(reference) if reference else None,
                        "observation": asdict(candidate) if candidate else None,
                        "reference_positive": bool(reference and reference.positive),
                        "candidate_positive": bool(candidate and candidate.positive),
                        "matched_reference": matched,
                        "comparison": comparison(reference, candidate, rate),
                        "fallback_selected_window_changed": bool(
                            used_blind
                            and reference_detail.rank.order[0] != candidate_detail.rank.order[0]
                        ),
                        "fallback_rank_order_changed": bool(
                            used_blind
                            and tuple(reference_detail.rank.order)
                            != tuple(candidate_detail.rank.order)
                        ),
                        "baseline_times": baseline_times,
                        "candidate_times": candidate_times,
                    }
                )
            if hashlib.sha256(raw).hexdigest() != original_hash:
                raise ValueError("caller IQ changed")
    summary = frozen_replay.summarize(rows)
    identity = {
        "all": identity_summary(rows),
        "by_rate": {
            str(rate): identity_summary([row for row in rows if row["rate_hz"] == rate])
            for rate in (2_500_000, 5_000_000)
        },
    }
    return {
        "schema": "org.leo.research.ds5-newdata-combined-fp32-cache-results.v1",
        "scope": "new-development server combined replay; no holdout, ARM, or RF",
        "dataset_sha256": digest(DATASET),
        "design_sha256": digest(HERE / "design.json"),
        "source_lock_sha256": digest(HERE / "source_lock.json"),
        "frozen_source_lock": lock,
        "fallback_backend": {
            "kind": "fp32_fftw",
            "library": str(FP32),
            "library_sha256": digest(FP32),
            "build_receipt_sha256": digest(FP32.with_name(FP32.name + ".build.json")),
        },
        "fast_backend": {
            "kind": "unchanged_v6_full_aperture_fp64",
            "library": str(FP64),
            "library_sha256": digest(FP64),
        },
        "reference_backend": {
            "kind": "stable_packed_v4_fp64",
            "library": str(FP64),
            "library_sha256": digest(FP64),
        },
        "host": platform.uname()._asdict(),
        "initialization_seconds": initialization_seconds,
        "summary": summary,
        "identity_gate": identity,
        "rows": rows,
        "limitations": [
            "packed FP64 baseline is reference-relative detector evidence, not physical truth",
            "server timing excludes IQ loading and hashing and does not establish ARM performance",
            "the combined gate is evaluated once without retuning",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        raise ValueError("new output must be beneath combined_fp32_cache and must not exist")
    result = run()
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"summary": result["summary"], "identity": result["identity_gate"]}))


if __name__ == "__main__":
    main()
