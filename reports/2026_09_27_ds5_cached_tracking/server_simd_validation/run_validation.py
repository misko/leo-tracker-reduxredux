#!/usr/bin/env python3
"""Validate the unchanged exact server SIMD candidate on fixed development inventories."""

from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import json
import os
import pickle
import signal
import statistics
import struct
import sys
import time
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
NEW_DATA = REPORT / "new_data"
OLD_CONTROLS = REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset"
ADVERSARIAL = REPORT / "lag3_controls"
NATIVE = REPORT / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
FP64 = NATIVE / "libblind_strided_v4.so"
FP32 = REPORT / "fft32" / "libfft32_fftw.so"
SIMD = REPORT / "server_simd" / "libserver_simd.so"
sys.path[:0] = [
    str(REPORT / "server_simd"), str(REPORT), str(NATIVE), str(DEPLOY), str(DEPLOY / "src")
]

from blind_strided_v4 import NativeStridedBlindV4  # noqa: E402
from server_simd import NativeServerSIMD  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import Observation, circular_samples, reference_match  # noqa: E402

VARIANTS = ("original_fp64_packed", "stable_fp32_fftw", "unchanged_server_simd")
RATES = (2_500_000, 5_000_000)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_source_lock() -> dict:
    lock = load_json(HERE / "source_lock.json")
    paths = {
        "design": HERE / "design.json",
        "runner": Path(__file__),
        "new_cases": NEW_DATA / "cases.json",
        "old_control_cases": OLD_CONTROLS / "cases.json",
        "adversarial_cases": ADVERSARIAL / "cases.json",
        "fp64_library": FP64,
        "fp64_receipt": FP64.with_name(FP64.name + ".build.json"),
        "fp32_library": FP32,
        "fp32_receipt": FP32.with_name(FP32.name + ".build.json"),
        "simd_library": SIMD,
        "simd_receipt": SIMD.with_name(SIMD.name + ".build.json"),
        "simd_component_result": REPORT / "server_simd" / "component_results.json",
        "simd_wrapper": REPORT / "server_simd" / "server_simd.py",
        "strided_wrapper": NATIVE / "blind_strided_v4.py",
        "tracking": REPORT / "tracking.py",
        "runtime_fftw": Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3.6.10"),
    }
    actual = {name: digest(path) for name, path in paths.items()}
    if lock.get("files") != actual:
        raise ValueError("server SIMD validation source lock changed")
    return lock


def selected_cases() -> list[tuple[str, Path, dict, str | None]]:
    new = sorted(
        (case for case in load_json(NEW_DATA / "cases.json")["cases"] if case["split"] == "dev"),
        key=lambda case: case["case_id"],
    )
    old = sorted(
        (
            case for case in load_json(OLD_CONTROLS / "cases.json")["cases"]
            if case["origin"] == "synthetic_control" and case["rate_hz"] in RATES
        ),
        key=lambda case: case["case_id"],
    )
    adversarial = sorted(load_json(ADVERSARIAL / "cases.json")["cases"],
                         key=lambda case: case["case_id"])
    if len(new) != 128 or len(old) != 12 or len(adversarial) != 20:
        raise ValueError("fixed validation inventory changed")
    if any(case["split"] != "control" for case in old + adversarial):
        raise ValueError("control inventory split changed")
    return (
        [("new_development", NEW_DATA, case, None) for case in new]
        + [("old_constructed_controls", OLD_CONTROLS, case, case["truth"]["kind"])
           for case in old]
        + [("new_adversarial_controls", ADVERSARIAL, case, case["injected"]["kind"])
           for case in adversarial]
    )


def load_iq(root: Path, case: dict) -> np.ndarray:
    path = (root / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(root.resolve()) or digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError(f"IQ source mismatch: {case['case_id']}")
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    expected = (case["rate_hz"] * case["dwell_ms"] // 1000, 2, 2)
    if values.dtype != np.dtype("<i2") or values.shape != expected:
        raise ValueError(f"IQ geometry mismatch: {case['case_id']}")
    return values


def science_value(value, field: str = ""):
    if isinstance(value, ct.Structure):
        return tuple(
            (name, science_value(getattr(value, name), name))
            for name, _ in value._fields_
            if "cpu_ms" not in name and "wall_ms" not in name
        )
    if isinstance(value, ct.Array):
        return tuple(science_value(item, field) for item in value)
    if isinstance(value, float):
        return struct.pack(">d", value)
    return value


def science_signature(result) -> tuple:
    return science_value(result)


def signature_hash(signature: tuple) -> str:
    return "sha256:" + hashlib.sha256(pickle.dumps(signature, protocol=5)).hexdigest()


def observation(result) -> Observation | None:
    if not result.confirmation_count or not result.confirmations[0].candidate_count:
        return None
    candidate = result.confirmations[0].candidates[0]
    return Observation(
        window=int(result.rank.order[0]),
        epoch_samples=float(candidate.epoch + candidate.fractional_offset_samples),
        cfo_hz=float(candidate.tracking_cfo_hz),
        exact=float(candidate.exact_score),
        control=float(candidate.control_score),
        supported=bool(candidate.fractional_complete),
        timing_kind="fitted",
        scoring_cfo_hz=float(candidate.acquired_cfo_hz),
    )


def compact(result) -> dict:
    observed = observation(result)
    nuisance = result.nuisances[0]
    return {
        "selected_window": int(result.rank.order[0]),
        "rank_order": [int(value) for value in result.rank.order],
        "projected_epoch_samples": [int(value) for value in result.rank.projected_epoch_samples],
        "rank_scores": [float(value) for value in result.rank.scores],
        "confirmation_count": int(result.confirmation_count),
        "candidate_count": int(result.confirmations[0].candidate_count),
        "observation": asdict(observed) if observed is not None else None,
        "positive": bool(observed and observed.positive),
        "nuisance": {
            "enabled": int(nuisance.enabled), "applied": int(nuisance.applied),
            "frequency_hz": float(nuisance.frequency_hz),
            "spectral_fraction": float(nuisance.spectral_fraction),
            "fitted_power_fraction": float(nuisance.fitted_power_fraction),
        },
    }


def identity(reference: Observation | None, candidate: Observation | None, rate: int) -> dict:
    matched = bool(reference and candidate and reference_match(reference, candidate, rate))
    delta = None
    if reference is not None and candidate is not None:
        sample_delta = ((reference.window - candidate.window) * (rate // 50)
                        + reference.epoch_samples - candidate.epoch_samples)
        delta = {
            "circular_timing_us": abs(circular_samples(sample_delta, rate)) / rate * 1e6,
            "cfo_hz": abs(reference.cfo_hz - candidate.cfo_hz),
        }
    return {
        "matched_positive_reference": matched,
        "lost_positive_reference": bool(reference and reference.positive and not matched),
        "additional_candidate_positive": bool(candidate and candidate.positive and not matched),
        "coordinate_delta": delta,
    }


def timed(function):
    started_cpu = time.thread_time_ns()
    started_wall = time.perf_counter_ns()
    result = function()
    return result, {
        "cpu_ms": (time.thread_time_ns() - started_cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - started_wall) / 1e6,
    }


def median_timing(samples: list[dict]) -> dict:
    return {name: statistics.median(sample[name] for sample in samples)
            for name in ("cpu_ms", "wall_ms")}


def summarize(rows: list[dict]) -> dict:
    totals = {
        variant: {
            clock: sum(row["timing"][variant]["median"][clock] for row in rows)
            for clock in ("cpu_ms", "wall_ms")
        }
        for variant in VARIANTS
    }
    original, stable, simd = (totals[name] for name in VARIANTS)
    return {
        "receiver_cases": len(rows),
        "candidate_exact_fp32_mismatches": sum(not row["candidate_exact_fp32"] for row in rows),
        "repeatability_failures": sum(not row["repeatable"] for row in rows),
        "positive_counts": {
            variant: sum(row["science"][variant]["positive"] for row in rows)
            for variant in VARIANTS
        },
        "stable_vs_original": {
            "lost": sum(row["identity"]["stable_vs_original"]["lost_positive_reference"] for row in rows),
            "additional": sum(row["identity"]["stable_vs_original"]["additional_candidate_positive"] for row in rows),
            "matched": sum(row["identity"]["stable_vs_original"]["matched_positive_reference"] for row in rows),
        },
        "simd_vs_original": {
            "lost": sum(row["identity"]["simd_vs_original"]["lost_positive_reference"] for row in rows),
            "additional": sum(row["identity"]["simd_vs_original"]["additional_candidate_positive"] for row in rows),
            "matched": sum(row["identity"]["simd_vs_original"]["matched_positive_reference"] for row in rows),
        },
        "timing_totals_ms": totals,
        "speedups": {
            "original_fp64_to_simd_cpu": original["cpu_ms"] / simd["cpu_ms"],
            "original_fp64_to_simd_wall": original["wall_ms"] / simd["wall_ms"],
            "stable_fp32_to_simd_cpu": stable["cpu_ms"] / simd["cpu_ms"],
            "stable_fp32_to_simd_wall": stable["wall_ms"] / simd["wall_ms"],
            "original_fp64_to_stable_fp32_cpu": original["cpu_ms"] / stable["cpu_ms"],
            "original_fp64_to_stable_fp32_wall": original["wall_ms"] / stable["wall_ms"],
        },
    }


def run() -> dict:
    signal.alarm(300)
    lock = verify_source_lock()
    cases = selected_cases()
    original_affinity = os.sched_getaffinity(0)
    if 0 not in original_affinity:
        raise ValueError("P-core 0 unavailable")
    geometries = {(case["rate_hz"], case["edge"]) for _, _, case, _ in cases}
    rows = []
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            original_engines = {
                geometry: stack.enter_context(NativeDwell(FP64, *geometry, 512))
                for geometry in geometries
            }
            stable_engines = {
                geometry: stack.enter_context(
                    NativeStridedBlindV4(*geometry, library=FP32, bins=512)
                ) for geometry in geometries
            }
            simd_engines = {
                geometry: stack.enter_context(NativeServerSIMD(*geometry, library=SIMD))
                for geometry in geometries
            }
            for engine in simd_engines.values():
                engine.force("simd")
                if engine.kernel_identity != "ssse3-sse4.1-forced":
                    raise ValueError("SIMD backend attestation failed")
            ordinal = 0
            for inventory, root, case, kind in cases:
                iq = load_iq(root, case)
                memory_hash = "sha256:" + hashlib.sha256(iq).hexdigest()
                geometry = (case["rate_hz"], case["edge"])
                for receiver in (0, 1):
                    functions = {
                        "original_fp64_packed": lambda receiver=receiver: original_engines[geometry].run(
                            np.ascontiguousarray(iq[:, receiver, :]), maximum=1, seeded=False
                        ),
                        "stable_fp32_fftw": lambda receiver=receiver: stable_engines[geometry].run(
                            iq[:, receiver, :], maximum=1, seeded=False
                        ),
                        "unchanged_server_simd": lambda receiver=receiver: simd_engines[geometry].run(
                            iq, receiver, maximum=1, seeded=False
                        ),
                    }
                    warm_order = VARIANTS[ordinal % 3:] + VARIANTS[:ordinal % 3]
                    for variant in warm_order:
                        functions[variant]()
                    results = {variant: [] for variant in VARIANTS}
                    timings = {variant: [] for variant in VARIANTS}
                    for repetition in range(3):
                        shift = (ordinal + repetition) % 3
                        order = VARIANTS[shift:] + VARIANTS[:shift]
                        for variant in order:
                            result, elapsed = timed(functions[variant])
                            results[variant].append(result)
                            timings[variant].append(elapsed)
                    signatures = {
                        variant: [science_signature(result) for result in results[variant]]
                        for variant in VARIANTS
                    }
                    repeatable = all(
                        all(value == values[0] for value in values[1:])
                        for values in signatures.values()
                    )
                    exact = signatures["unchanged_server_simd"] == signatures["stable_fp32_fftw"]
                    first = {variant: results[variant][0] for variant in VARIANTS}
                    observations = {variant: observation(first[variant]) for variant in VARIANTS}
                    rows.append({
                        "case_id": case["case_id"], "inventory": inventory, "kind": kind,
                        "rate_hz": case["rate_hz"], "edge": case["edge"], "receiver": receiver,
                        "raw_sha256": case["raw_npy"]["sha256"],
                        "candidate_exact_fp32": exact, "repeatable": repeatable,
                        "science_signature_sha256": {
                            variant: signature_hash(signatures[variant][0]) for variant in VARIANTS
                        },
                        "science": {variant: compact(first[variant]) for variant in VARIANTS},
                        "identity": {
                            "stable_vs_original": identity(
                                observations["original_fp64_packed"],
                                observations["stable_fp32_fftw"], case["rate_hz"]
                            ),
                            "simd_vs_original": identity(
                                observations["original_fp64_packed"],
                                observations["unchanged_server_simd"], case["rate_hz"]
                            ),
                        },
                        "timing": {
                            variant: {"samples": timings[variant], "median": median_timing(timings[variant])}
                            for variant in VARIANTS
                        },
                    })
                    ordinal += 1
                if "sha256:" + hashlib.sha256(iq).hexdigest() != memory_hash:
                    raise ValueError("caller IQ mutated")
    finally:
        os.sched_setaffinity(0, original_affinity)
    if len(rows) != 320:
        raise ValueError("validation receiver inventory incomplete")
    overall = summarize(rows)
    by_inventory = {
        inventory: summarize([row for row in rows if row["inventory"] == inventory])
        for inventory in ("new_development", "old_constructed_controls", "new_adversarial_controls")
    }
    by_rate = {str(rate): summarize([row for row in rows if row["rate_hz"] == rate])
               for rate in RATES}
    validation_gate = (
        overall["candidate_exact_fp32_mismatches"] == 0
        and overall["repeatability_failures"] == 0
        and all(
            overall[name][field] == 0
            for name in ("stable_vs_original", "simd_vs_original")
            for field in ("lost", "additional")
        )
    )
    return {
        "schema": "org.leo.research.server-simd-validation-result/v1",
        "fresh_holdout_opened": False,
        "original_component_gate_passed": False,
        "candidate_unchanged_after_component_gate": True,
        "affinity_cpu": 0,
        "affinity_restored": sorted(original_affinity),
        "warmups_per_variant_receiver_case": 1,
        "repetitions": 3,
        "association": {"circular_timing_us": 2.0, "cfo_hz": 8000.0},
        "source_lock": lock,
        "validation_gate_passed": validation_gate,
        "summary": {"all": overall, "by_inventory": by_inventory, "by_rate_hz": by_rate},
        "rows": rows,
        "limitations": [
            "The original FP64 detector is a numerical reference, not physical truth.",
            "Constructed controls do not calibrate detector false-positive or sensitivity rates.",
            "This validation was authorized after the component gate outcome and does not retroactively pass that gate.",
            "These server measurements do not establish a 10x, ARM, production, or RF result.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("output must be a new file directly under server_simd_validation")
    payload = run()
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"validation_gate_passed": payload["validation_gate_passed"],
                      **payload["summary"]["all"]["speedups"]}, sort_keys=True))


if __name__ == "__main__":
    main()
