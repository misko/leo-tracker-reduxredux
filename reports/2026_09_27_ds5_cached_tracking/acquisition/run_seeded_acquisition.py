#!/usr/bin/env python3
"""Compare packed blind and strided rank-seeded acquisition on development IQ."""

from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import json
import platform
import signal
import statistics
import sys
import time
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DATASET = REPORT / "dataset"
CONTROL_DATASET = REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset"
NATIVE = REPORT / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(REPORT), str(NATIVE), str(DEPLOY), str(DEPLOY / "src")]

from blind_strided_v4 import NativeStridedBlindV4, build_library_v4  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import Observation, reference_match  # noqa: E402

RATES = (2_500_000, 5_000_000)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def load_json(path: Path, expected_sha256: str) -> dict:
    if digest(path) != expected_sha256:
        raise ValueError(f"frozen input hash mismatch: {path}")
    return json.loads(path.read_text())


def select_development(payload: dict) -> list[dict]:
    selected = sorted(
        (case for case in payload["cases"] if case["split"] == "dev"),
        key=lambda case: (case["session_id"], case["visit_index"]),
    )
    if len(selected) != 128 or {case["rate_hz"] for case in selected} != set(RATES):
        raise ValueError("expected exactly 128 development visits at the two native rates")
    return selected


def select_controls(payload: dict) -> list[dict]:
    selected = [
        case
        for case in payload["cases"]
        if case["origin"] == "synthetic_control" and case["rate_hz"] in RATES
    ]
    if len(selected) != 12:
        raise ValueError("unexpected fixed control inventory")
    return selected


def load_iq(root: Path, case: dict) -> np.ndarray:
    path = (root / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("IQ path escapes dataset root")
    if digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError(f"IQ hash mismatch: {case['case_id']}")
    values = np.load(path, allow_pickle=False, mmap_mode="r")
    expected = (case["rate_hz"] * 120 // 1000, 2, 2)
    if values.dtype != np.dtype("<i2") or values.shape != expected:
        raise ValueError(f"IQ geometry mismatch: {case['case_id']}")
    return values


def result_observation(result) -> Observation | None:
    window = int(result.rank.order[0])
    confirmation = result.confirmations[0]
    if not confirmation.candidate_count:
        return None
    candidate = confirmation.candidates[0]
    return Observation(
        window=window,
        epoch_samples=float(candidate.epoch + candidate.fractional_offset_samples),
        cfo_hz=float(candidate.tracking_cfo_hz),
        exact=float(candidate.exact_score),
        control=float(candidate.control_score),
        supported=bool(candidate.fractional_complete),
        timing_kind="fitted",
        scoring_cfo_hz=float(candidate.acquired_cfo_hz),
    )


def compact_result(result) -> dict:
    confirmation = result.confirmations[0]
    observation = result_observation(result)
    return {
        "selected_window": int(result.rank.order[0]),
        "rank_order": [int(value) for value in result.rank.order],
        "projected_epoch_samples": [int(value) for value in result.rank.projected_epoch_samples],
        "rank_scores": [float(value) for value in result.rank.scores],
        "candidate_count": int(confirmation.candidate_count),
        "fractional_complete": bool(
            confirmation.candidate_count and confirmation.candidates[0].fractional_complete
        ),
        "observation": asdict(observation) if observation is not None else None,
        "positive": bool(observation and observation.positive),
        "native_total_cpu_ms": float(result.total_cpu_ms),
        "native_total_wall_ms": float(result.total_wall_ms),
        "rank_cpu_ms": float(result.rank.total_cpu_ms),
        "confirmation_cpu_ms": float(confirmation.total_cpu_ms),
    }


def scientific_signature(result) -> tuple:
    confirmation = result.confirmations[0]
    candidates = []
    for index in range(int(confirmation.candidate_count)):
        candidate = confirmation.candidates[index]
        candidates.append(
            tuple(
                getattr(candidate, name)
                if not isinstance(getattr(candidate, name), ct.Array)
                else tuple(getattr(candidate, name))
                for name, _ in candidate._fields_
            )
        )
    return (
        tuple(result.rank.scores),
        tuple(result.rank.order),
        tuple(result.rank.projected_epoch_samples),
        int(result.confirmation_count),
        int(result.confirmation_window_mask),
        int(confirmation.candidate_count),
        tuple(candidates),
    )


def run_timed(function) -> tuple[object, dict]:
    cpu_started = time.thread_time_ns()
    wall_started = time.perf_counter_ns()
    result = function()
    return result, {
        "cpu_ms": (time.thread_time_ns() - cpu_started) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
    }


def median_timing(values: list[dict]) -> dict:
    return {
        name: statistics.median(value[name] for value in values) for name in ("cpu_ms", "wall_ms")
    }


def summarize(rows: list[dict]) -> dict:
    reference_positive = [row for row in rows if row["reference"]["positive"]]
    candidate_positive = [row for row in rows if row["candidate"]["positive"]]
    matched = [row for row in rows if row["matched_reference"]]
    extras = [row for row in rows if row["candidate"]["positive"] and not row["matched_reference"]]
    lost = [row for row in rows if row["reference"]["positive"] and not row["matched_reference"]]
    baseline_cpu = sum(row["baseline_timing"]["cpu_ms"] for row in rows)
    candidate_cpu = sum(row["candidate_timing"]["cpu_ms"] for row in rows)
    baseline_wall = sum(row["baseline_timing"]["wall_ms"] for row in rows)
    candidate_wall = sum(row["candidate_timing"]["wall_ms"] for row in rows)
    return {
        "receiver_visits": len(rows),
        "reference_positives": len(reference_positive),
        "candidate_positives": len(candidate_positive),
        "matched_reference_positives": len(matched),
        "lost_reference_positives": len(lost),
        "additional_candidate_positives": len(extras),
        "candidate_no_candidate": sum(row["candidate"]["candidate_count"] == 0 for row in rows),
        "candidate_incomplete": sum(
            row["candidate"]["candidate_count"] > 0 and not row["candidate"]["fractional_complete"]
            for row in rows
        ),
        "costs": {
            "packed_unseeded_cpu_ms": baseline_cpu,
            "packed_unseeded_wall_ms": baseline_wall,
            "strided_candidate_cpu_ms": candidate_cpu,
            "strided_candidate_wall_ms": candidate_wall,
            "cpu_speedup": baseline_cpu / candidate_cpu,
            "wall_speedup": baseline_wall / candidate_wall,
            "distance_from_10x_cpu_factor": 10 / (baseline_cpu / candidate_cpu),
        },
    }


def summarize_controls(rows: list[dict]) -> dict:
    groups = {}
    for rate in RATES:
        for kind in ("pilot", "noise", "tone"):
            subset = [row for row in rows if row["rate_hz"] == rate and row["truth_kind"] == kind]
            groups[f"{rate}:{kind}"] = {
                "receiver_cases": len(subset),
                "baseline_positive": sum(row["reference"]["positive"] for row in subset),
                "candidate_positive": sum(row["candidate"]["positive"] for row in subset),
                "matched_baseline": sum(row["matched_reference"] for row in subset),
            }
    return {
        "groups": groups,
        "scope": "fixed constructed controls run after development; never used to tune",
    }


def verify_default_inputs(design: dict, library: Path) -> None:
    checks = {
        NATIVE / "blind_strided_v4.py": design["default_v4"]["python_sha256"],
        NATIVE / "blind_strided_v4.c": design["default_v4"]["c_sha256"],
        NATIVE / "blind_strided_v4.h": design["default_v4"]["header_sha256"],
        library: design["default_v4"]["binary_sha256"],
        library.with_name(library.name + ".build.json"): design["default_v4"][
            "build_receipt_sha256"
        ],
        REPORT / "tracking.py": design["tracking_sha256"],
        NATIVE / "profile.json": design["native_profile_sha256"],
    }
    for path, expected in checks.items():
        if digest(path) != expected:
            raise ValueError(f"default frozen input changed: {path}")


def run(candidate_library: Path | None = None, *, candidate_seeded: bool = True) -> dict:
    signal.alarm(300)
    design = json.loads((HERE / "design.json").read_text())
    dataset_payload = load_json(DATASET / "cases.json", design["dataset_cases_sha256"])
    control_payload = load_json(CONTROL_DATASET / "cases.json", design["control_cases_sha256"])
    development = select_development(dataset_payload)
    controls = select_controls(control_payload)
    default_library = candidate_library is None
    library = build_library_v4() if default_library else candidate_library.resolve()
    if not library.is_file():
        raise FileNotFoundError(library)
    if default_library:
        verify_default_inputs(design, library)

    rows: list[dict] = []
    control_rows: list[dict] = []
    all_cases = development + controls
    geometries = {(case["rate_hz"], case["edge"]) for case in all_cases}
    with ExitStack() as stack:
        baselines = {
            geometry: stack.enter_context(NativeDwell(library, *geometry, 512))
            for geometry in geometries
        }
        candidates = {
            geometry: stack.enter_context(
                NativeStridedBlindV4(*geometry, library=library, bins=512)
            )
            for geometry in geometries
        }

        def process(case: dict, root: Path, ordinal: int, *, control: bool) -> None:
            iq = load_iq(root, case)
            input_hash = hashlib.sha256(iq).hexdigest()
            geometry = (case["rate_hz"], case["edge"])
            baseline_engine = baselines[geometry]
            candidate_engine = candidates[geometry]
            for rx in range(2):

                def baseline_call(rx=rx):
                    packed = np.ascontiguousarray(iq[:, rx, :])
                    return baseline_engine.run(packed, maximum=1, seeded=False)

                def candidate_call(rx=rx):
                    view = iq[:, rx, :]
                    return candidate_engine.run(view, maximum=1, seeded=candidate_seeded)

                warm_order = (baseline_call, candidate_call)
                if (ordinal + rx) % 2:
                    warm_order = tuple(reversed(warm_order))
                for function in warm_order:
                    function()

                baseline_results = []
                candidate_results = []
                baseline_times = []
                candidate_times = []
                for repetition in range(design["timing"]["repetitions"]):
                    order = (("baseline", baseline_call), ("candidate", candidate_call))
                    if (ordinal + rx + repetition) % 2:
                        order = tuple(reversed(order))
                    for name, function in order:
                        result, timing = run_timed(function)
                        if name == "baseline":
                            baseline_results.append(result)
                            baseline_times.append(timing)
                        else:
                            candidate_results.append(result)
                            candidate_times.append(timing)

                baseline_signatures = [scientific_signature(result) for result in baseline_results]
                candidate_signatures = [
                    scientific_signature(result) for result in candidate_results
                ]
                if any(value != baseline_signatures[0] for value in baseline_signatures[1:]):
                    raise ValueError("packed baseline changed across repetitions")
                if any(value != candidate_signatures[0] for value in candidate_signatures[1:]):
                    raise ValueError("strided candidate changed across repetitions")
                baseline_result = baseline_results[0]
                candidate_result = candidate_results[0]
                if (
                    tuple(baseline_result.rank.scores) != tuple(candidate_result.rank.scores)
                    or tuple(baseline_result.rank.order) != tuple(candidate_result.rank.order)
                    or tuple(baseline_result.rank.projected_epoch_samples)
                    != tuple(candidate_result.rank.projected_epoch_samples)
                ):
                    raise ValueError("packed and strided rank proposals differ")

                baseline_observation = result_observation(baseline_result)
                candidate_observation = result_observation(candidate_result)
                matched = bool(
                    baseline_observation
                    and candidate_observation
                    and reference_match(
                        baseline_observation, candidate_observation, case["rate_hz"]
                    )
                )
                row = {
                    "case_id": case["case_id"],
                    "session_id": case.get("session_id"),
                    "visit_index": case.get("visit_index"),
                    "source_start_counter": case.get("source_start_counter"),
                    "rate_hz": case["rate_hz"],
                    "edge": case["edge"],
                    "channel": case["channel"],
                    "rx": rx,
                    "reference": compact_result(baseline_result),
                    "candidate": compact_result(candidate_result),
                    "matched_reference": matched,
                    "baseline_timing": median_timing(baseline_times),
                    "candidate_timing": median_timing(candidate_times),
                    "baseline_timings": baseline_times,
                    "candidate_timings": candidate_times,
                }
                if control:
                    row.update(
                        truth_kind=case["truth"]["kind"],
                        starlink_model_present=case["truth"]["starlink_model_present"],
                    )
                    control_rows.append(row)
                else:
                    rows.append(row)
            if hashlib.sha256(iq).hexdigest() != input_hash:
                raise ValueError("caller IQ changed")

        for ordinal, case in enumerate(development):
            process(case, DATASET, ordinal, control=False)
        if len(rows) != 256:
            raise ValueError("development result inventory mismatch")
        for ordinal, case in enumerate(controls, start=len(development)):
            process(case, CONTROL_DATASET, ordinal, control=True)

    build_receipt = library.with_name(library.name + ".build.json")
    result = {
        "schema": "org.leo.research.ds5-seeded-acquisition-results.v1",
        "scope": "development-only independent detector comparison; no automatic fallback",
        "fresh_holdout_opened": False,
        "candidate_seeded": candidate_seeded,
        "design_sha256": digest(HERE / "design.json"),
        "runner_sha256": digest(Path(__file__)),
        "dataset_cases_sha256": digest(DATASET / "cases.json"),
        "control_cases_sha256": digest(CONTROL_DATASET / "cases.json"),
        "candidate_library_path": str(library),
        "candidate_library_sha256": digest(library),
        "candidate_build_receipt_sha256": (
            digest(build_receipt) if build_receipt.is_file() else None
        ),
        "host": platform.uname()._asdict(),
        "summary": {
            "all": summarize(rows),
            "by_rate": {
                str(rate): summarize([row for row in rows if row["rate_hz"] == rate])
                for rate in RATES
            },
        },
        "control_summary": summarize_controls(control_rows),
        "rows": rows,
        "control_rows": control_rows,
        "limitations": [
            "packed unseeded baseline is a detector reference, not physical truth",
            "candidate non-detections are exposed without fallback but are not physical negatives",
            "5 MS/s development contains no established real-IQ reference positives",
            "synthetic controls are fixed smoke evidence and never tune the method",
            "server timing is not ARM timing; IQ file loading and hashing are excluded",
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    parser.add_argument("--candidate-library", type=Path)
    parser.add_argument("--candidate-seeded", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        raise ValueError("new output must be beneath acquisition and must not exist")
    result = run(args.candidate_library, candidate_seeded=args.candidate_seeded)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"summary": result["summary"], "controls": result["control_summary"]}))


if __name__ == "__main__":
    main()
