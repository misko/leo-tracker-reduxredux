#!/usr/bin/env python3
"""Freeze a metadata-only, development/control ARM probe plan."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CACHE_DATASET = ROOT / "reports/2026_09_27_ds5_cached_tracking/dataset"
CONTROL_DATASET = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_cases() -> list[dict]:
    cache_manifest = CACHE_DATASET / "cases.json"
    control_manifest = CONTROL_DATASET / "cases.json"
    cache = json.loads(cache_manifest.read_text())
    controls = json.loads(control_manifest.read_text())
    # First two consecutive visits in each exposed development block. Selection
    # is positional metadata only and does not inspect IQ or detector outcomes.
    real = []
    for rate in (2_500_000, 5_000_000):
        rows = sorted(
            (c for c in cache["cases"] if c["split"] == "dev" and c["rate_hz"] == rate),
            key=lambda c: c["block_offset"],
        )
        real.extend(rows[:2])
    synthetic = [
        c for c in controls["cases"]
        if c["split"] == "control" and c["rate_hz"] in (2_500_000, 5_000_000)
    ]
    out = []
    for dataset_dir, rows in ((CACHE_DATASET, real), (CONTROL_DATASET, synthetic)):
        manifest = dataset_dir / "cases.json"
        for c in rows:
            out.append({
                "case_id": c["case_id"], "origin": c["origin"], "split": c["split"],
                "rate_hz": c["rate_hz"], "edge": c["edge"],
                "dataset_dir": str(dataset_dir.relative_to(ROOT)),
                "dataset_manifest_sha256": sha256(manifest),
                "raw_npy": c["raw_npy"],
            })
    return out


def main() -> None:
    output = HERE / "plan.json"
    payload = {
        "schema": "org.leo.research.arm-stateless-probe-plan/v1",
        "selection": "metadata-only first two dev visits per supported rate plus all matching controls",
        "holdout_excluded": True,
        "methods": ["packed_builtin_fp64", "packed_fftw_fp64", "aligned_v5_fftw_fp32"],
        "warmups": 1, "repetitions": 3, "max_confirmations": 1, "seeded": False,
        "cases": selected_cases(),
    }
    text = json.dumps(payload, indent=2) + "\n"
    if output.exists() and output.read_text() != text:
        raise ValueError("plan.json already exists with different content")
    output.write_text(text)
    print(sha256(output))


if __name__ == "__main__":
    main()
