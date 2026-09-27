#!/usr/bin/env python3
"""Oracle-timing development diagnostic for a fixed bank of short GLRT CFO centers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import signal
import statistics
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DATASET = REPORT / "dataset"
CONTROL_DATASET = REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset"
NATIVE = REPORT / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(NATIVE), str(DEPLOY), str(DEPLOY / "src")]

from known_state_v3 import NativeKnownStateV3, build_library_v3  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def load_json(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"frozen input hash mismatch: {path}")
    return json.loads(path.read_text())


def load_iq(root: Path, case: dict) -> np.ndarray:
    path = (root / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(root.resolve()) or digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError(f"IQ path/hash mismatch: {case['case_id']}")
    values = np.load(path, allow_pickle=False, mmap_mode="r")
    expected = (case["rate_hz"] * 120 // 1000, 2, 2)
    if values.dtype != np.dtype("<i2") or values.shape != expected:
        raise ValueError(f"IQ geometry mismatch: {case['case_id']}")
    return values


def point_signature(result: dict) -> tuple:
    return tuple(
        result[name]
        for name in (
            "exact_score",
            "control_score",
            "tracking_cfo_hz",
            "fractional_offset_samples",
            "support_frames",
            "scored_fractional",
            "valid_bounds",
        )
    )


def run_bank(
    workspace: NativeKnownStateV3,
    raw: np.ndarray,
    rx: int,
    left: int,
    epoch: int,
    centers: list[int],
    repetitions: int,
) -> dict:
    def evaluate(center: int) -> dict:
        values = raw[left : left + workspace.rate // 50, rx, :]
        return workspace.measure(
            values,
            float(epoch),
            float(center),
            expected_physical_cfo_hz=float(center),
            recover_timing=False,
            frame_limit=2,
        )

    for center in centers:
        evaluate(center)
    repetition_results = []
    timings = []
    for repetition in range(repetitions):
        order = centers if repetition % 2 == 0 else list(reversed(centers))
        started_cpu = time.thread_time_ns()
        started_wall = time.perf_counter_ns()
        by_center = {center: evaluate(center) for center in order}
        timings.append(
            {
                "cpu_ms": (time.thread_time_ns() - started_cpu) / 1e6,
                "wall_ms": (time.perf_counter_ns() - started_wall) / 1e6,
                "native_cpu_ms": sum(by_center[center]["total_cpu_ms"] for center in centers),
            }
        )
        repetition_results.append(by_center)
    expected = {center: point_signature(repetition_results[0][center]) for center in centers}
    for by_center in repetition_results[1:]:
        if {center: point_signature(by_center[center]) for center in centers} != expected:
            raise ValueError("GLRT center result changed across repetitions")
    results = repetition_results[0]
    selected_center = max(
        centers,
        key=lambda center: results[center]["exact_score"] - results[center]["control_score"],
    )
    selected = results[selected_center]
    return {
        "selected_center_hz": selected_center,
        "proposed_physical_cfo_hz": selected["tracking_cfo_hz"],
        "exact": selected["exact_score"],
        "control": selected["control_score"],
        "margin": selected["exact_score"] - selected["control_score"],
        "positive": selected["exact_score"] - selected["control_score"] > 0.025,
        "support_frames": selected["support_frames"],
        "valid_bounds": bool(selected["valid_bounds"]),
        "scores": [
            {
                "center_hz": center,
                "exact": results[center]["exact_score"],
                "control": results[center]["control_score"],
                "margin": results[center]["exact_score"] - results[center]["control_score"],
                "tracking_cfo_hz": results[center]["tracking_cfo_hz"],
            }
            for center in centers
        ],
        "timing": {
            name: statistics.median(value[name] for value in timings)
            for name in ("cpu_ms", "wall_ms", "native_cpu_ms")
        },
    }


def baseline_fine(
    workspace: NativeDwell, raw: np.ndarray, rx: int, expected: dict, repetitions: int
) -> dict:
    results = []
    for _ in range(1 + repetitions):
        packed = np.ascontiguousarray(raw[:, rx, :])
        results.append(workspace.run(packed, maximum=1, seeded=False))
    measured = results[1:]
    first = measured[0]
    window = int(first.rank.order[0])
    confirmation = first.confirmations[0]
    if not confirmation.candidate_count:
        raise ValueError("reference baseline lost its candidate")
    candidate = confirmation.candidates[0]
    observation = expected["observation"]
    if (
        window != expected["selected_window"]
        or float(candidate.exact_score) != observation["exact"]
        or float(candidate.control_score) != observation["control"]
    ):
        raise ValueError("reference baseline differs from frozen acquisition receipt")
    return {
        "fine_cpu_ms": statistics.median(
            float(result.confirmations[0].fine_cpu_ms) for result in measured
        ),
        "confirmation_cpu_ms": statistics.median(
            float(result.confirmations[0].total_cpu_ms) for result in measured
        ),
        "dwell_cpu_ms": statistics.median(float(result.total_cpu_ms) for result in measured),
    }


def summarize(rows: list[dict], variant: str) -> dict:
    selected = [row["variants"][variant] for row in rows]
    fine = sum(row["baseline_cost"]["fine_cpu_ms"] for row in rows)
    outer = sum(value["timing"]["cpu_ms"] for value in selected)
    native = sum(value["timing"]["native_cpu_ms"] for value in selected)
    return {
        "receiver_cases": len(rows),
        "margin_positive": sum(value["positive"] for value in selected),
        "cfo_within_8khz": sum(value["cfo_within_8khz"] for value in selected),
        "joint_success": sum(value["positive"] and value["cfo_within_8khz"] for value in selected),
        "max_abs_cfo_error_hz": max(abs(value["cfo_error_hz"]) for value in selected),
        "cost": {
            "baseline_fine_cpu_ms": fine,
            "center_bank_outer_cpu_ms": outer,
            "center_bank_native_cpu_ms": native,
            "outer_over_baseline_fine": outer / fine,
            "native_over_baseline_fine": native / fine,
        },
    }


def summarize_controls(rows: list[dict], variant: str) -> dict:
    groups = {}
    for rate in (2_500_000, 5_000_000):
        for kind in ("pilot", "noise", "tone"):
            subset = [row for row in rows if row["rate_hz"] == rate and row["truth_kind"] == kind]
            groups[f"{rate}:{kind}"] = {
                "receiver_cases": len(subset),
                "reference_positive": sum(row["reference_positive"] for row in subset),
                "candidate_positive": sum(row["variants"][variant]["positive"] for row in subset),
                "pilot_cfo_within_8khz": sum(
                    row["variants"][variant].get("cfo_within_8khz", False)
                    for row in subset
                    if kind == "pilot"
                ),
            }
    return groups


def run() -> dict:
    signal.alarm(300)
    design = json.loads((HERE / "glrt_cfo_design.json").read_text())
    reference = load_json(HERE / "results.json", design["reference_results_sha256"])
    dataset = load_json(DATASET / "cases.json", design["dataset_cases_sha256"])
    controls = load_json(CONTROL_DATASET / "cases.json", design["control_cases_sha256"])
    cases = {case["case_id"]: case for case in dataset["cases"] if case["split"] == "dev"}
    control_cases = {
        case["case_id"]: case
        for case in controls["cases"]
        if case["origin"] == "synthetic_control" and case["rate_hz"] in (2_500_000, 5_000_000)
    }
    reference_rows = [row for row in reference["rows"] if row["reference"]["positive"]]
    if len(reference_rows) != 36:
        raise ValueError("expected 36 frozen development reference positives")
    control_rows = reference["control_rows"]
    if len(control_rows) != 24:
        raise ValueError("expected 24 fixed receiver-controls")

    known_library = build_library_v3()
    blind_library = NATIVE / "libblind_strided_v4.so"
    checks = {
        NATIVE / "known_state_v3.py": design["known_state_v3"]["python_sha256"],
        NATIVE / "known_state_v3.c": design["known_state_v3"]["c_sha256"],
        NATIVE / "known_state_v3.h": design["known_state_v3"]["header_sha256"],
        known_library: design["known_state_v3"]["binary_sha256"],
        known_library.with_name(known_library.name + ".build.json"): design["known_state_v3"][
            "build_receipt_sha256"
        ],
        blind_library: design["blind_library_sha256"],
    }
    for path, expected in checks.items():
        if digest(path) != expected:
            raise ValueError(f"native input changed: {path}")

    variant_centers = {variant["name"]: variant["centers_hz"] for variant in design["variants"]}
    all_rows = reference_rows + control_rows
    geometries = {(row["rate_hz"], row["edge"]) for row in all_rows}
    positive_results = []
    control_results = []
    with ExitStack() as stack:
        point = {
            geometry: stack.enter_context(NativeKnownStateV3(*geometry, library=known_library))
            for geometry in geometries
        }
        blind = {
            geometry: stack.enter_context(NativeDwell(blind_library, *geometry, 512))
            for geometry in geometries
        }

        def process(row: dict, case: dict, root: Path, *, control: bool) -> None:
            raw = load_iq(root, case)
            rate = row["rate_hz"]
            rx = row["rx"]
            reference_result = row["reference"]
            observation = reference_result["observation"]
            if observation is None:
                raise ValueError("oracle timing requires a reference observation")
            window = reference_result["selected_window"]
            epoch = math.floor(observation["epoch_samples"])
            result = {
                "case_id": row["case_id"],
                "rate_hz": rate,
                "edge": row["edge"],
                "rx": rx,
                "source_start_counter": row.get("source_start_counter"),
                "reference_positive": reference_result["positive"],
                "reference_window": window,
                "reference_epoch_samples": observation["epoch_samples"],
                "oracle_integer_epoch": epoch,
                "reference_cfo_hz": observation["cfo_hz"],
                "reference_margin": observation["exact"] - observation["control"],
                "baseline_cost": baseline_fine(
                    blind[(rate, row["edge"])], raw, rx, reference_result, 3
                ),
                "variants": {},
            }
            left = window * (rate // 50)
            for name, centers in variant_centers.items():
                value = run_bank(point[(rate, row["edge"])], raw, rx, left, epoch, centers, 3)
                error = value["proposed_physical_cfo_hz"] - observation["cfo_hz"]
                value.update(
                    cfo_error_hz=error,
                    cfo_within_8khz=abs(error) <= 8000,
                )
                result["variants"][name] = value
            if control:
                result.update(
                    truth_kind=row["truth_kind"],
                    starlink_model_present=row["starlink_model_present"],
                )
                control_results.append(result)
            else:
                positive_results.append(result)

        for row in reference_rows:
            process(row, cases[row["case_id"]], DATASET, control=False)
        for row in control_rows:
            process(
                row,
                control_cases[row["case_id"]],
                CONTROL_DATASET,
                control=True,
            )

    summaries = {name: summarize(positive_results, name) for name in variant_centers}
    control_summaries = {
        name: summarize_controls(control_results, name) for name in variant_centers
    }
    return {
        "schema": "org.leo.research.ds5-glrt-cfo-oracle-results.v1",
        "scope": "development reference-positive oracle-timing diagnostic; not acquisition",
        "fresh_holdout_opened": False,
        "design_sha256": digest(HERE / "glrt_cfo_design.json"),
        "runner_sha256": digest(Path(__file__)),
        "reference_results_sha256": digest(HERE / "results.json"),
        "known_state_v3_binary_sha256": digest(known_library),
        "blind_library_sha256": digest(blind_library),
        "summary": summaries,
        "control_summary": control_summaries,
        "rows": positive_results,
        "control_rows": control_results,
        "limitations": [
            "reference-selected window and fitted timing are supplied before scoring",
            "two-frame scores are unqualified and do not replace full confirmation",
            "packed baseline positives are detector references rather than physical truth",
            "controls are fixed smoke evidence and never tune centers or thresholds",
            "server timing is not ARM timing; file loading and hashing are excluded",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "glrt_cfo_results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        raise ValueError("new output must be beneath acquisition and must not exist")
    result = run()
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"summary": result["summary"], "controls": result["control_summary"]}))


if __name__ == "__main__":
    main()
