#!/usr/bin/env python3
"""Full-cohort direct/FFT and matched-bandwidth replay (ledger 25--26)."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = importlib.util.spec_from_file_location(
    "high_bandwidth", ROOT.parent / "2026_09_25_eight_hour_high_bandwidth_phase/analyze.py"
)
assert SPEC and SPEC.loader
HB = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HB
SPEC.loader.exec_module(HB)

COMMON_SPEC = importlib.util.spec_from_file_location("phase_common", ROOT / "common.py")
assert COMMON_SPEC and COMMON_SPEC.loader
COMMON = importlib.util.module_from_spec(COMMON_SPEC)
sys.modules[COMMON_SPEC.name] = COMMON
COMMON_SPEC.loader.exec_module(COMMON)


def seeds(path: Path) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], tuple[float, float]] = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["passed_0p025_comparison_gate"] != "True":
                continue
            key = int(row["visit_index"]), int(row["receiver_id"])
            value = float(row["fractional_margin"]), float(
                row["tracking_absolute_baseband_cfo_hz"]
            )
            if key not in out or value[0] > out[key][0]:
                out[key] = value
    return {key: value[1] for key, value in out.items()}


def run(index: Path, selection: Path, candidates: Path, output: Path) -> None:
    source = COMMON.CachedReplayVisitSource(index, selection)
    selected = json.loads(selection.read_text())
    cfo = seeds(candidates)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if output.exists():
        completed = {json.loads(line)["visit_index"] for line in output.read_text().splitlines()}
    with output.open("a") as stream:
        for item in selected["visits"]:
            visit_index = item["visit_index"]
            if visit_index in completed:
                continue
            started = time.monotonic()
            arrays = source.read_visit(visit_index)
            iq = np.column_stack((arrays.complex64(0), arrays.complex64(1)))
            if (visit_index, 0) not in cfo or (visit_index, 1) not in cfo:
                stream.write(
                    json.dumps(
                        {
                            "schema": "scan-sync-spectral/v1",
                            "visit_index": visit_index,
                            "split": item["split"],
                            "target_index": item["target_index"],
                            "status": "unsupported",
                            "reason": "one or both receivers lack a complete sparse GLRT basin",
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                stream.flush()
                continue
            relative_seed = cfo[visit_index, 1] - cfo[visit_index, 0]
            _, _, _, starts = HB.window_geometry(10_000_000)
            frequency, rate, _ = HB.fit_frequency_rate(
                iq, 10_000_000, relative_seed, starts, 100.0, 3000.0
            )
            direct, coherence, _ = HB.time_phasors(iq, 10_000_000, frequency, rate, starts)
            fft = HB.fft_observables(iq, 10_000_000, frequency, rate, starts)
            parity = np.angle(fft["full"] * np.conj(direct))
            random = HB.random_holdout(
                iq, 10_000_000, relative_seed, f"{visit_index}:native-random-v1"
            )
            cut = len(starts) // 2
            forward_frequency, forward_rate, _ = HB.fit_frequency_rate(
                iq, 10_000_000, relative_seed, starts[:cut], 100.0, 3000.0
            )
            forward_phasors, _, _ = HB.time_phasors(
                iq, 10_000_000, forward_frequency, forward_rate, starts
            )
            native_time = np.arange(len(iq), dtype=float) / 10_000_000
            recentered = iq.copy()
            for receiver in (0, 1):
                recentered[:, receiver] *= np.exp(
                    -2j * np.pi * cfo[visit_index, receiver] * native_time
                )
            reduced = HB.decimate_four(recentered)
            _, _, _, low_starts = HB.window_geometry(2_500_000)
            low_frequency, low_rate, _ = HB.fit_frequency_rate(
                reduced, 2_500_000, 0.0, low_starts, 100.0, 3000.0
            )
            low_direct, low_coherence, _ = HB.time_phasors(
                reduced, 2_500_000, low_frequency, low_rate, low_starts
            )
            low_random = HB.random_holdout(
                reduced, 2_500_000, 0.0, f"{visit_index}:low-random-v1"
            )
            low_cut = len(low_starts) // 2
            low_forward_frequency, low_forward_rate, _ = HB.fit_frequency_rate(
                reduced, 2_500_000, 0.0, low_starts[:low_cut], 100.0, 3000.0
            )
            low_forward_phasors, _, _ = HB.time_phasors(
                reduced, 2_500_000, low_forward_frequency, low_forward_rate, low_starts
            )
            row = {
                "schema": "scan-sync-spectral/v1",
                "status": "complete",
                "validation_scope": "in_sample_historical_reconstruction_no_efficacy_claim",
                "visit_index": visit_index,
                "split": item["split"],
                "target_index": item["target_index"],
                "relative_cfo_seed_hz": relative_seed,
                "fitted_relative_cfo_hz": frequency,
                "fitted_relative_rate_hz_s": rate,
                "direct_phase_r": HB.circular_r(np.angle(direct)),
                "random_train_r": random["train_r"],
                "random_held_r": random["held_r"],
                "forward_train_r": HB.circular_r(np.angle(forward_phasors[:cut])),
                "forward_held_r": HB.circular_r(np.angle(forward_phasors[cut:])),
                "median_direct_coherence": float(np.median(coherence)),
                "fft_full_phase_r": HB.circular_r(np.angle(fft["full"])),
                "fft_common_phase_r": HB.circular_r(np.angle(fft["common"])),
                "fft_phase_only_r": HB.circular_r(np.angle(fft["phat"])),
                "direct_fft_parseval_rms_rad": float(np.sqrt(np.mean(parity**2))),
                "retained_bandwidth_hz": float(np.median(fft["retained_bandwidth_hz"])),
                "bandwidth_phase_r": {
                    key: HB.circular_r(np.angle(value)) for key, value in fft["by_width"].items()
                },
                "derived_2p5_direct_phase_r": HB.circular_r(np.angle(low_direct)),
                "derived_2p5_random_train_r": low_random["train_r"],
                "derived_2p5_random_held_r": low_random["held_r"],
                "derived_2p5_forward_train_r": HB.circular_r(
                    np.angle(low_forward_phasors[:low_cut])
                ),
                "derived_2p5_forward_held_r": HB.circular_r(
                    np.angle(low_forward_phasors[low_cut:])
                ),
                "derived_2p5_median_coherence": float(np.median(low_coherence)),
                "derived_2p5_relative_cfo_hz": low_frequency,
                "derived_2p5_relative_rate_hz_s": low_rate,
                "derived_2p5_policy": (
                    "each RX mixed by its own passed absolute GLRT CFO before common FIR; "
                    "first analysis window begins beyond the 128-native-sample half-filter guard"
                ),
                "runtime_seconds": time.monotonic() - started,
            }
            if not all(arrays.valid_mask.ravel()):
                raise ValueError("spectral replay encountered invalid source support")
            if not math.isfinite(row["direct_fft_parseval_rms_rad"]):
                raise ValueError("non-finite spectral parity")
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.index, args.selection, args.candidates, args.output)


if __name__ == "__main__":
    main()
