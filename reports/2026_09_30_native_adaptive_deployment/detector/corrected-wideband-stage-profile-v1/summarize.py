#!/usr/bin/env python3
"""Summarize the existing stage-boundary profile for corrected visit 301.

This is an evidence extractor.  It does not run or modify the detector.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ARM = ROOT / "reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-arm-v1/visit-0301.arm.jsonl"
HOST = ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/wideband-research/retention-audit-v1/visit-0301.jsonl"
COMPARISON = ROOT / "reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-arm-v1/comparison.json"
SOURCE = ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/wideband-research/source/native/adaptive/detector/kernel/private/full_search_reference.c"

EXPECTED = {
    ARM: "43f091fd8e26a87267e8dc792b094ce611a47e20ce194efc9508ad35f479bbdb",
    HOST: "e1159c922de818bd001f9b838d20a318b3db5070361c42ff3172da311b026174",
    COMPARISON: "afc027a212beda620bde6db1867317978ea89bbf05226d7c8425e323aea1361b",
    SOURCE: "b1b74aecd47b730f214f8d44061a42a5d3200579220b017ab99301641633cb25",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    calls = [row["result"] for row in rows if row.get("result", {}).get("kind") == "call"]
    if len(calls) != 1:
        raise RuntimeError(f"expected exactly one call in {path}, got {len(calls)}")
    return calls[0]


def profile(path: Path) -> dict:
    value = call(path)
    if not value["profile_enabled"] or len(value["rows"]) != 2:
        raise RuntimeError(f"expected a profiled two-receiver call in {path}")
    totals = {
        key: sum(row["timings_ms"][key] for row in value["rows"])
        for key in (
            "total_cpu",
            "coarse",
            "acquisition",
            "fine_fft",
            "conditioned",
            "verification",
            "glrt",
            "fractional_epoch",
        )
    }
    # acquisition contains fine_fft, conditioned, verification and loop overhead.
    totals["acquisition_other"] = totals["acquisition"] - sum(
        totals[key] for key in ("fine_fft", "conditioned", "verification")
    )
    # The top-level row total contains disjoint coarse, acquisition, final GLRT,
    # fractional work and small control/sort overhead. glrt is measured inside
    # that residual rather than inside acquisition.
    totals["final_other_including_glrt"] = totals["total_cpu"] - sum(
        totals[key] for key in ("coarse", "acquisition", "fractional_epoch")
    )
    totals["final_control_sort_other"] = totals["final_other_including_glrt"] - totals["glrt"]
    totals["disjoint_share_percent"] = {
        key: 100.0 * totals[key] / totals["total_cpu"]
        for key in ("coarse", "acquisition", "fractional_epoch", "final_other_including_glrt")
    }
    totals["acquisition_share_percent"] = {
        key: 100.0 * totals[key] / totals["acquisition"]
        for key in ("fine_fft", "conditioned", "verification", "acquisition_other")
    }
    return {
        "call_cpu_ms": value["call_cpu_ms"],
        "call_wall_ms": value["call_wall_ms"],
        "detector_cpu_ms": value["detector_cpu_ms"],
        "outer_profile_ms": value["profile"],
        "row_cpu_ms": totals,
        "per_receiver": [
            {"receiver_id": row["receiver_id"], **row["timings_ms"]}
            for row in value["rows"]
        ],
    }


def main() -> None:
    for path, expected in EXPECTED.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"evidence hash mismatch for {path}: {actual}")
    comparison = json.loads(COMPARISON.read_text())
    if comparison.get("status") != "pass":
        raise RuntimeError("frozen host/ARM comparison is not passing")
    checks = comparison["comparison"]
    for key in ("structure_equal", "numeric_values_finite", "within_frozen_tolerance", "all_gate_decisions_equal"):
        if checks.get(key) is not True:
            raise RuntimeError(f"frozen comparison did not establish {key}")

    host = profile(HOST)
    arm = profile(ARM)
    ratio_keys = (
        "total_cpu",
        "coarse",
        "acquisition",
        "fine_fft",
        "conditioned",
        "verification",
        "glrt",
        "fractional_epoch",
    )
    output = {
        "schema": "leo-corrected-wideband-stage-profile/v1",
        "status": "pass",
        "scope": "one 120 ms DS9 visit (301), both receivers, corrected frozen wideband reference path",
        "scientific_comparison": {
            "status": comparison["status"],
            "candidate_structure_equal": checks["structure_equal"],
            "gate_decisions_compared": checks["gate_decisions_compared"],
            "gate_decisions_equal": checks["all_gate_decisions_equal"],
            "passing_candidates": checks["native_passing_candidates"],
        },
        "host": host,
        "physical_arm": arm,
        "arm_over_host_cpu_ratio": {
            key: arm["row_cpu_ms"][key] / host["row_cpu_ms"][key]
            for key in ratio_keys
        },
        "evidence_sha256": {
            str(path.relative_to(ROOT)): digest for path, digest in EXPECTED.items()
        },
        "interpretation_limits": [
            "Single visit and single physical ARM execution; timings are diagnostic, not a population bound.",
            "Acquisition contains fine FFT, conditioned search, verification, and loop overhead; nested values must not be added to acquisition.",
            "The final_other_including_glrt residual contains final integer GLRT plus control/sort overhead.",
            "No production source, algorithm, thresholds, or golden evidence changed.",
        ],
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
