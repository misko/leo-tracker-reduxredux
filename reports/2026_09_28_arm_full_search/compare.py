"""Run a native full-search probe binary against the frozen Python oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

GRID_ATOL = 2e-11
SCORE_ATOL = 2e-9
CFO_ATOL_HZ = 2e-6
HIT_MARGIN_GATE = 0.025
HIT_EPOCH_TOLERANCE_SAMPLES = 2
HIT_CFO_TOLERANCE_HZ = 8_000.0

INTEGER_FIELDS = (
    ("coarse_epoch", "coarse_epoch_sample"),
    ("refined_epoch", "refined_epoch_sample"),
    ("epoch", "refined_epoch_sample"),
    ("frame_support", "frame_support"),
)
FLOAT_FIELDS = (
    ("coarse_cfo_hz", "coarse_residual_cfo_hz", CFO_ATOL_HZ),
    ("conditioned_cfo_hz", "residual_cfo_hz", CFO_ATOL_HZ),
    ("acquired_cfo_hz", "absolute_cfo_hz", CFO_ATOL_HZ),
    ("acquire_score", "acquire_score", SCORE_ATOL),
    ("verify_score", "verify_score", SCORE_ATOL),
    ("verify_control_score", "conditioned_control_score", SCORE_ATOL),
    ("conditioned_score", "conditioned_exact_score", SCORE_ATOL),
    ("coarse_score", "coarse_score", SCORE_ATOL),
)
FINAL_FLOAT_FIELDS = (
    ("tracking_cfo_hz", "tracking_cfo_hz", CFO_ATOL_HZ),
    ("exact_score", "exact_score", SCORE_ATOL),
    ("control_score", "control_score", SCORE_ATOL),
    ("margin", "margin", SCORE_ATOL),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(actual: object, expected: object, tolerance: float) -> dict[str, Any]:
    actual_float, expected_float = float(actual), float(expected)
    delta = actual_float - expected_float
    return {
        "actual": actual_float,
        "expected": expected_float,
        "delta": delta,
        "exact": actual_float == expected_float,
        "tolerance": tolerance,
        "within_tolerance": math.isclose(
            actual_float, expected_float, rel_tol=0.0, abs_tol=tolerance
        ),
    }


def exact(actual: object, expected: object) -> dict[str, Any]:
    return {"actual": actual, "expected": expected, "exact": actual == expected}


def compare_grid(reference_path: Path, native_path: Path, shape: list[int]) -> dict[str, Any]:
    reference_bytes = reference_path.read_bytes()
    native_bytes = native_path.read_bytes()
    expected_size = int(np.prod(shape)) * np.dtype("<f8").itemsize
    if len(reference_bytes) != expected_size or len(native_bytes) != expected_size:
        return {
            "byte_exact": reference_bytes == native_bytes,
            "shape": shape,
            "valid_size": False,
            "reference_bytes": len(reference_bytes),
            "native_bytes": len(native_bytes),
            "within_tolerance": False,
        }
    reference = np.frombuffer(reference_bytes, dtype="<f8")
    native = np.frombuffer(native_bytes, dtype="<f8")
    difference = np.abs(native - reference)
    finite = bool(np.all(np.isfinite(native)))
    maximum = float(np.max(difference)) if difference.size else 0.0
    return {
        "byte_exact": reference_bytes == native_bytes,
        "shape": shape,
        "valid_size": True,
        "finite": finite,
        "max_abs_difference": maximum,
        "tolerance": GRID_ATOL,
        "within_tolerance": finite and maximum <= GRID_ATOL,
    }


def compare_candidate(
    native: dict[str, Any], reference: dict[str, Any], final: dict[str, Any]
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for native_name, reference_name in INTEGER_FIELDS:
        fields[native_name] = exact(native.get(native_name), reference[reference_name])
    coarse_bin = round((float(reference["coarse_residual_cfo_hz"]) + 400000.0) / 80000.0)
    fields["coarse_bin"] = exact(native.get("coarse_bin"), coarse_bin)
    fields["glrt_complete"] = exact(native.get("glrt_complete"), True)
    for native_name, reference_name, tolerance in FLOAT_FIELDS:
        fields[native_name] = numeric(native.get(native_name), reference[reference_name], tolerance)
    for native_name, reference_name, tolerance in FINAL_FLOAT_FIELDS:
        fields[native_name] = numeric(native.get(native_name), final[reference_name], tolerance)
    # The frozen acquisition result intentionally does not expose its transient
    # pre-conditioned fine-grid maximum; retain it as native-only diagnostics.
    fields["fine_cfo_hz"] = {"actual": native.get("fine_cfo_hz"), "oracle_field": None}
    return {
        "fields": fields,
        "exact": all(value.get("exact", True) for value in fields.values()),
        "within_tolerance": all(
            value.get("within_tolerance", value.get("exact", True)) for value in fields.values()
        ),
    }


def _positive(entries: list[dict[str, Any]], margin_key: str) -> list[dict[str, Any]]:
    return [entry for entry in entries if float(entry[margin_key]) >= HIT_MARGIN_GATE]


def hit_metrics(reference: list[dict[str, Any]], native: list[dict[str, Any]]) -> dict[str, Any]:
    """One-to-one timing/CFO matching, independent of ordered parity."""

    expected = _positive(reference, "margin")
    actual = _positive(native, "margin")
    available = set(range(len(actual)))
    pairs: list[dict[str, Any]] = []
    for expected_index, item in enumerate(expected):
        choices = [
            (
                abs(int(item["refined_epoch_sample"]) - int(actual[index]["epoch"])),
                abs(float(item["tracking_cfo_hz"]) - float(actual[index]["tracking_cfo_hz"])),
                index,
            )
            for index in available
            if abs(int(item["refined_epoch_sample"]) - int(actual[index]["epoch"]))
            <= HIT_EPOCH_TOLERANCE_SAMPLES
            and abs(float(item["tracking_cfo_hz"]) - float(actual[index]["tracking_cfo_hz"]))
            <= HIT_CFO_TOLERANCE_HZ
        ]
        if choices:
            epoch_delta, cfo_delta, actual_index = min(choices)
            available.remove(actual_index)
            pairs.append(
                {
                    "reference_positive_index": expected_index,
                    "native_positive_index": actual_index,
                    "epoch_delta_samples": epoch_delta,
                    "tracking_cfo_delta_hz": cfo_delta,
                }
            )
    matched = len(pairs)
    return {
        "reference_positive_count": len(expected),
        "native_positive_count": len(actual),
        "matched_count": matched,
        "missed_count": len(expected) - matched,
        "added_count": len(actual) - matched,
        "recall": None if not expected else matched / len(expected),
        "precision": None if not actual else matched / len(actual),
        "matches": pairs,
    }


def compare_response(
    native: dict[str, Any],
    receiver: dict[str, Any],
    native_grid: Path,
    oracle_directory: Path,
) -> dict[str, Any]:
    candidates = native.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("native response candidates must be a list")
    reference = receiver["retained_candidates"]
    finals = receiver["final_glrt512"]
    ordered = [
        compare_candidate(actual, expected, final)
        for actual, expected, final in zip(candidates, reference, finals, strict=False)
    ]
    count = {
        "candidate_count": exact(native.get("candidate_count"), len(reference)),
        "retained_peak_count": exact(native.get("retained_peak_count"), len(reference)),
        "ordered_pair_count": exact(len(candidates), len(reference)),
    }
    reference_hits = [
        {
            **candidate,
            "tracking_cfo_hz": final["tracking_cfo_hz"],
            "margin": final["margin"],
        }
        for candidate, final in zip(reference, finals, strict=True)
    ]
    return {
        "grid": compare_grid(
            _resolve(oracle_directory, receiver["coarse_grid"]),
            native_grid,
            receiver["coarse_grid"]["shape"],
        ),
        "counts": count,
        "ordered_candidates": ordered,
        "ordered_exact": len(candidates) == len(reference)
        and all(item["exact"] for item in ordered),
        "ordered_within_tolerance": len(candidates) == len(reference)
        and all(item["within_tolerance"] for item in ordered),
        "one_to_one_hits": hit_metrics(reference_hits, candidates),
    }


def _resolve(oracle_directory: Path, item: dict[str, Any]) -> Path:
    path = oracle_directory / item["file"]
    if sha256(path) != item["sha256"]:
        raise ValueError(f"oracle sidecar hash differs: {path.name}")
    return path


def run(binary: Path, oracle_directory: Path, output: Path) -> dict[str, Any]:
    oracle_path = oracle_directory / "oracle.json"
    oracle = json.loads(oracle_path.read_text())
    if oracle.get("schema") != "arm-full-search-oracle/v1":
        raise ValueError("unsupported oracle schema")
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    receipt: dict[str, Any] = {
        "schema": "arm-full-search-compare/v1",
        "complete": False,
        "binary": str(binary),
        "binary_sha256": sha256(binary),
        "oracle": str(oracle_path),
        "oracle_sha256": sha256(oracle_path),
        "grid_atol": GRID_ATOL,
        "score_atol": SCORE_ATOL,
        "cfo_atol_hz": CFO_ATOL_HZ,
        "hit_epoch_tolerance_samples": HIT_EPOCH_TOLERANCE_SAMPLES,
        "hit_cfo_tolerance_hz": HIT_CFO_TOLERANCE_HZ,
        "records": 0,
    }
    (output / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    failed = False
    with (output / "results.jsonl").open("x") as results:
        for case in oracle["cases"]:
            rate = str(case["context"]["rate_hz"])
            exact_template = _resolve(oracle_directory, case["templates"]["exact"])
            control_template = _resolve(oracle_directory, case["templates"]["control"])
            for receiver in case["receivers"]:
                probe = _resolve(oracle_directory, receiver["raw_probe"])
                grid_path = output / (
                    f"{case['context']['target']['edge']}-rx{receiver['receiver_id']}-coarse.f64"
                )
                command = [
                    str(binary),
                    rate,
                    str(exact_template),
                    str(control_template),
                    str(probe),
                    str(grid_path),
                    "1",
                ]
                completed = subprocess.run(command, capture_output=True, text=True, check=False)
                record: dict[str, Any] = {
                    "context": case["context"],
                    "receiver_id": receiver["receiver_id"],
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
                try:
                    native = json.loads(completed.stdout)
                    record["native"] = native
                    if completed.returncode:
                        raise ValueError("native binary returned nonzero")
                    record["comparison"] = compare_response(
                        native, receiver, grid_path, oracle_directory
                    )
                    parity = record["comparison"]
                    record["passed"] = bool(
                        parity["grid"]["within_tolerance"] and parity["ordered_within_tolerance"]
                    )
                except Exception as error:
                    record["error"] = repr(error)
                    record["passed"] = False
                results.write(json.dumps(record, allow_nan=False) + "\n")
                results.flush()
                receipt["records"] += 1
                failed = failed or not record["passed"]
                (output / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    receipt["complete"] = True
    receipt["passed"] = not failed
    (output / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.binary, args.oracle, args.output)
    print(json.dumps(receipt, allow_nan=False))
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
