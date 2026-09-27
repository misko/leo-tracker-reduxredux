#!/usr/bin/env python3
"""Run the frozen FP32 FFTW transfer comparison on new development IQ."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent.parent
ACQUISITION = REPORT / "acquisition"
CONTROL_DATASET = REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset"
CANDIDATE = REPORT / "fft32" / "libfft32_fftw.so"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return "sha256:" + result.hexdigest()


def load_runner():
    path = ACQUISITION / "run_acquisition.py"
    spec = importlib.util.spec_from_file_location("newdata_frozen_acquisition_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen acquisition runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_source_lock() -> dict:
    lock_path = HERE / "source_lock.json"
    lock = json.loads(lock_path.read_text())
    if lock.get("schema") != "org.leo.research.ds5-newdata-fft32-transfer-source-lock.v1":
        raise ValueError("source lock schema differs")
    checks = {
        HERE / "design_variants.json": lock["design_sha256"],
        Path(__file__): lock["adapter_sha256"],
        ACQUISITION / "run_acquisition.py": lock["acquisition_runner_sha256"],
        REPORT / "new_data" / "cases.json": lock["dataset_cases_sha256"],
        CONTROL_DATASET / "cases.json": lock["control_cases_sha256"],
        REPORT / "native" / "libblind_strided_v4.so": lock["baseline_library_sha256"],
        CANDIDATE: lock["candidate_library_sha256"],
    }
    for path, expected in checks.items():
        if digest(path) != expected:
            raise ValueError(f"frozen transfer input changed: {path}")
    return lock


def run() -> dict:
    source_lock = verify_source_lock()
    module = load_runner()
    module.HERE = HERE
    module.DATASET = REPORT / "new_data"
    module.CONTROL_DATASET = CONTROL_DATASET
    result = module.run(CANDIDATE, candidate_seeded=False)
    result.update(
        schema="org.leo.research.ds5-newdata-fft32-transfer-results.v1",
        scope=(
            "new-development server FP32 FFTW transfer comparison; no fallback, holdout, ARM, or RF"
        ),
        evaluation_role="newdevelopment",
        source_lock_sha256=digest(HERE / "source_lock.json"),
        frozen_source_lock=source_lock,
        limitations=[
            "packed unseeded FP64 baseline is a detector reference, not physical truth",
            "candidate non-detections are exposed without fallback and are not physical negatives",
            "synthetic controls are fixed smoke evidence and never tune the method",
            "server timing is not ARM timing; IQ file loading and hashing are excluded",
        ],
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        raise ValueError("new output must be beneath fft32_transfer and must not exist")
    result = run()
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"summary": result["summary"], "controls": result["control_summary"]}))


if __name__ == "__main__":
    main()
