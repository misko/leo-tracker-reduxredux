"""Run the frozen boundary fallback over the complete DS8/DS9 saved-IQ cohort.

This wrapper deliberately delegates window slicing, input-payload hashing, and
candidate comparison to the immutable full-optimization cohort runner.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
FROZEN_COHORT = HERE.parent / "2026_09_28_arm_full_optimization" / "cohort.py"
DEFAULT_BINARY = (
    HERE.parent
    / "2026_09_28_arm_boundary_fallback"
    / "builds/host-cohort-v1/cohort_boundary"
)
HOST_BUILD_RECEIPT = DEFAULT_BINARY.parent / "build.json"
REQUIRED_DATASETS = {"DS8", "DS9"}
REQUIRED_DWELLS = 680
REQUIRED_DATASET_DWELLS = {"DS8": 260, "DS9": 420}
RATES = {2_500_000, 5_000_000, 7_500_000, 10_000_000}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_cohort():
    spec = importlib.util.spec_from_file_location("frozen_ds89_cohort", FROZEN_COHORT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen cohort runner: {FROZEN_COHORT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_inputs(inputs: Path) -> list[dict]:
    receipt_path = inputs / "inputs.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("schema") != "ds7-large-arm-inputs/v1" or not receipt.get("complete"):
        raise ValueError("inputs must be a complete ds7-large-arm-inputs/v1 receipt")
    rows = receipt.get("rows")
    if not isinstance(rows, list) or len(rows) != REQUIRED_DWELLS:
        raise ValueError(f"expected exactly {REQUIRED_DWELLS} DS8/DS9 dwells")
    keys = set()
    cohort_keys = set()
    datasets = set()
    for row in rows:
        try:
            dataset = row["dataset_id"]
            key = (dataset, row["session_id"], row["visit_index"])
            rate = row["rate_hz"]
            shape = row["shape"]
            payload = inputs / row["file"]
            digest = row["sha256"]
        except (KeyError, TypeError) as error:
            raise ValueError("DS8/DS9 input row is missing required cohort metadata") from error
        cohort_key = (row["session_id"], row["visit_index"])
        if dataset not in REQUIRED_DATASETS or key in keys or cohort_key in cohort_keys:
            raise ValueError("input cohort must contain unique DS8 and DS9 contexts")
        if rate not in RATES or row.get("dtype") != "int16" or shape != [rate * 120 // 1000, 2, 2]:
            raise ValueError("input dwell does not have the required 120 ms dual-CI16 geometry")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("input row has no SHA-256 receipt")
        if payload.parent.resolve() != inputs.resolve() or not payload.is_file():
            raise ValueError(f"saved IQ is unavailable: {row.get('file')!r}")
        keys.add(key)
        cohort_keys.add(cohort_key)
        datasets.add(dataset)
    counts = {dataset: sum(row["dataset_id"] == dataset for row in rows) for dataset in REQUIRED_DATASETS}
    if datasets != REQUIRED_DATASETS or counts != REQUIRED_DATASET_DWELLS:
        raise ValueError("input receipt must contain exactly 260 DS8 and 420 DS9 dwells")
    return rows


def validate_baseline(baseline: Path, rows: list[dict]) -> None:
    expected = {(row["session_id"], row["visit_index"]): row["sha256"] for row in rows}
    actual = {}
    for line in baseline.read_text().splitlines():
        row = json.loads(line)
        if row.get("method") != "original" or row.get("repeat") != 0 or row.get("status") != "ok":
            continue
        context = row.get("context", {})
        key = (context.get("session_id"), context.get("visit_index"))
        if key in expected:
            if key in actual or context.get("sha256") != expected[key]:
                raise ValueError("original baseline has duplicate or hash-mismatched DS8/DS9 context")
            actual[key] = row
    if actual.keys() != expected.keys():
        raise ValueError("original baseline does not cover the complete DS8/DS9 receipt")


def validate_binary(binary: Path) -> None:
    receipt = json.loads(HOST_BUILD_RECEIPT.read_text())
    expected = receipt.get("binary_sha256", {}).get("cohort_boundary")
    if not isinstance(expected, str) or sha256(binary) != expected:
        raise ValueError("candidate binary differs from frozen host-cohort-v1 receipt")


def run(inputs: Path, baseline: Path, output: Path, binary: Path = DEFAULT_BINARY, workers: int = 4) -> None:
    if output.exists():
        raise FileExistsError(output)
    if not binary.is_file():
        raise FileNotFoundError(binary)
    validate_binary(binary)
    rows = validate_inputs(inputs)
    validate_baseline(baseline, rows)
    cohort = load_frozen_cohort()
    cohort.INPUTS = inputs
    cohort.BASELINE = baseline
    cohort.run(binary, output, workers=workers, all_sealed=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run(args.inputs, args.baseline, args.output, args.binary, args.workers)


if __name__ == "__main__":
    main()
