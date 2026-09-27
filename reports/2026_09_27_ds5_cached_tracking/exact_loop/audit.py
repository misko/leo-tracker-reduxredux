#!/usr/bin/env python3
"""Pin and quantify the ARM-relevant exact-loop optimization audit."""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DEPLOY_NATIVE = Path("/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence")

PINNED = {
    REPORT / "native/blind_aligned_v5.c": "181b7dc702c59fc52afe23ac571be6dc7ff4fcf12e1e89b7b3eca2c34d58ac7b",
    REPORT / "native/blind_aligned_v5_cortex_a9.build.json": "f355c06ff1d392043237c0c5a58fd4153843eeccf1b9b42b7763311cf1903268",
    REPORT / "native/libblind_aligned_v5.so.build.json": "0ddc880b77a17f6a25c0da32400d48beba96feede69abdec20a5c0b9e136ce4c",
    REPORT / "fft32/fft32_fftw.c": "47215be17a6c32d8f377871e44b03c7f8942b0f54b48947db9968a475bec7b14",
    REPORT / "fft32/libfft32_fftw.so.build.json": "efce18893445d1cc1c7ac0ab22231a6c15200f4fd7c3e025a4c410f8e2fa3ce4",
    REPORT / "scout/blind_cost_receipt.json": "935d89bcdf39f3b8414ffa81f280feeb7e0a826e7c555133ccc16ff37785fd78",
    DEPLOY_NATIVE / "ci16_fold.h": "afdd9a1476b04bf06a529438a504f28640daff486196f1b1a6b185c59478a288",
    DEPLOY_NATIVE / "ci16_lag.h": "9dc6642506fd9e68c2e7643b2aa2733638c542b0b17d7280fde131c8bae6a39c",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> dict:
    for path, expected in PINNED.items():
        actual = digest(path)
        if actual != expected:
            raise ValueError(f"pinned source drift: {path}: {actual}")

    v5 = (REPORT / "native/blind_aligned_v5.c").read_text()
    fold = (DEPLOY_NATIVE / "ci16_fold.h").read_text()
    lag = (DEPLOY_NATIVE / "ci16_lag.h").read_text()
    required = {
        "aligned_rank_load": (v5, "vld4_s16"),
        "rank_i16_multiply": (v5, "vmull_s16"),
        "rank_product_widen": (v5, "vmovl_s32"),
        "rank_i64_accumulate": (v5, "vaddq_s64"),
        "coarse_i16_multiply": (fold, "vmull_s16"),
        "coarse_product_widen": (fold, "vmovl_s32"),
        "coarse_i64_accumulate": (fold, "vaddq_s64"),
        "nuisance_i16_multiply": (lag, "vmull_s16"),
        "nuisance_i64_pair_accumulate": (lag, "vpadalq_s32"),
    }
    missing = [name for name, (source, token) in required.items() if token not in source]
    if missing:
        raise ValueError(f"expected exact ARM kernels missing: {missing}")

    arm_receipt = json.loads((REPORT / "native/blind_aligned_v5_cortex_a9.build.json").read_text())
    if arm_receipt["status"] != "cross_compiled_and_disassembled_not_executed_or_timed":
        raise ValueError("unexpected ARM qualification status")
    expected_instructions = {"vld4.16", "vmull.s16", "vmovl.s32", "vadd.i64", "vsub.i64"}
    if not expected_instructions.issubset(set(arm_receipt["verified_instruction_fragments"].values())):
        raise ValueError("ARM rank disassembly receipt lacks exact widening instructions")

    cost = json.loads((REPORT / "scout/blind_cost_receipt.json").read_text())
    rate_rows = {}
    for rate in (2_500_000, 5_000_000):
        rows = [row["median"] for row in cost["rows"] if row["rate_hz"] == rate]
        residuals = [
            row["dwell_total_cpu_ms"] - row["rank_total_cpu_ms"] - row["confirm_total_cpu_ms"]
            for row in rows
        ]
        dwell = statistics.median(row["dwell_total_cpu_ms"] for row in rows)
        ten_percent = 0.1 * dwell
        # The residual includes selected-window packing plus dwell orchestration
        # and timer non-additivity. Its largest observed positive value is thus
        # a conservative empirical bound on a packing-only optimization.
        observed_upper = max(0.0, max(residuals))
        rate_rows[str(rate)] = {
            "receiver_visits": len(rows),
            "dwell_cpu_median_ms": dwell,
            "packing_plus_orchestration_residual_median_ms": statistics.median(residuals),
            "packing_plus_orchestration_residual_max_ms": observed_upper,
            "ten_percent_projection_gate_ms": ten_percent,
            "perfect_removal_fraction_of_gate": observed_upper / ten_percent,
            "projection_gate_passed": observed_upper >= ten_percent,
        }

    return {
        "schema": "org.leo.research.exact-loop-arm-audit/v1",
        "decision": "stop-before-implementation",
        "reason": "material exact CI16 loops already have NEON; remaining scalar pack misses the x86 server projection gate even at perfect removal",
        "scope": "read-only source/build/timing audit; no DSP replay, holdout, RF, or ARM timing",
        "projection_context": "historical x86_64 server receipt only; not an ARM cost bound",
        "pinned_sha256": {str(path.resolve()): expected for path, expected in PINNED.items()},
        "existing_arm_exact_paths": {
            "rank_fold": "sample-aligned vld4, signed-16 products, each product widened to int64 before complex add/sub",
            "coarse_fold": "contiguous vld2, signed-16 power/lag products, each product widened before int64 cell accumulation",
            "nuisance_lag": "contiguous vld2, signed-16 products accumulated into int64 lanes",
            "rank_disassembly_crosscheck_only": arm_receipt["verified_instruction_fragments"],
        },
        "no_material_candidates": {
            "runtime_integer_division_or_modulo": "confined to sparse bookkeeping; absent from dense rank/CI16 loops",
            "fftw_conversion": "compiler already emits packed SSE double/float conversions on the measured x86 server",
            "complex_helpers": "fcx-limited-range already active; libc cabs remains required by exact final GLRT ceilings",
            "selected_window_pack": "only uncovered ARM scalar loop; misses the x86 server projection gate, while physical ARM cost remains unknown",
        },
        "projection_by_rate": rate_rows,
        "limitations": [
            "The Cortex-A9 receipt proves generated instructions, not ARM runtime performance.",
            "Server timings cannot be presented as ARM savings.",
            "The physical ARM packing cost remains unknown and requires hardware measurement.",
            "The packing bound comes from the fixed 16-receiver prefix and includes orchestration/timer residual.",
            "No server candidate was built because the x86 projection gate failed before implementation.",
        ],
    }


if __name__ == "__main__":
    output = run()
    path = HERE / "evidence.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": output["decision"], "projection_by_rate": output["projection_by_rate"]}, indent=2))
