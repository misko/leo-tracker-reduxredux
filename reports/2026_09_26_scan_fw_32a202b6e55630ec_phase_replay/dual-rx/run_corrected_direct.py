"""Correct method 24 replay: phase-blind CFO pair, then sample-level restoration."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
REPORT = HERE.parent
CACHE_INDEX = Path(
    "/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json"
)
CANDIDATES = REPORT / "acquisition/candidate-inventory.csv"
ALIAS_HZ = 1 / 4.4e-6
RATE = 10_000_000
WINDOW = 32_768


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


A = _module("phase_replay_dual_rx_analysis", HERE / "analysis.py")
C = _module("phase_replay_common", REPORT / "common.py")
HB = _module(
    "historical_high_bandwidth_phase",
    REPORT.parent / "2026_09_25_eight_hour_high_bandwidth_phase/analyze.py",
)


def _candidate_pairs() -> dict[int, tuple[dict, dict]]:
    grouped = defaultdict(lambda: defaultdict(list))
    with CANDIDATES.open() as stream:
        for row in csv.DictReader(stream):
            if row["passed_0p025_comparison_gate"] == "True":
                grouped[int(row["visit_index"])][int(row["receiver_id"])].append(row)
    output = {}
    for visit, by_rx in grouped.items():
        if 0 not in by_rx or 1 not in by_rx:
            continue
        output[visit] = tuple(
            max(
                by_rx[receiver],
                key=lambda row: (float(row["fractional_margin"]), -int(row["candidate_rank"])),
            )
            for receiver in (0, 1)
        )
    return output


def _starts() -> np.ndarray:
    stratum = 200_000
    offset = (stratum - 6 * WINDOW) // 2
    return np.asarray(
        [group * stratum + offset + index * WINDOW for group in range(6) for index in range(6)],
        dtype=np.int64,
    )


def _split(starts: np.ndarray, authority: str) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(authority.encode()).digest()[:8]))
    train = []
    held = []
    for group in range(6):
        order = rng.permutation(np.arange(group * 6, group * 6 + 6))
        train.extend(order[:3])
        held.extend(order[3:])
    return np.asarray(train), np.asarray(held)


def _concentration(values: np.ndarray) -> float:
    return float(abs(np.sum(values)) / max(float(np.sum(abs(values))), 1e-30))


def _fit(iq, valid, counter, starts, train, seed):
    aliases = seed + np.arange(-4, 5) * ALIAS_HZ
    alias_scores = []
    for value in aliases:
        observed = A.direct_window_phasors(
            iq,
            valid,
            device_counter_start=counter,
            sample_rate_hz=RATE,
            starts=starts[train],
            window_samples=WINDOW,
            relative_cfo_hz=value,
        )
        alias_scores.append(float(np.median(observed.coherence)))
    alias = float(aliases[int(np.argmax(alias_scores))])
    frequency, rate, concentration = HB.fit_frequency_rate(
        iq, RATE, alias, starts[train], 100.0, 2000.0
    )
    best = (concentration, frequency, rate)
    return aliases, alias_scores, best


def _score(iq, valid, counter, starts, train, held, frequency, rate):
    phasors, coherence, _ = HB.time_phasors(iq, RATE, frequency, rate, starts)
    intercept = float(np.angle(np.sum(phasors[train])))
    zero_intercept_error = A.wrap_rad(np.angle(phasors[held]))
    centered_error = A.wrap_rad(zero_intercept_error - intercept)
    return {
        "r": A.circular_r(zero_intercept_error),
        "zero_intercept_rms_deg": float(
            np.degrees(np.sqrt(np.mean(zero_intercept_error**2)))
        ),
        "train_centered_rms_deg": float(np.degrees(np.sqrt(np.mean(centered_error**2)))),
        "median_coherence": float(np.median(coherence)),
    }


def _fit_forward(iq, valid, counter, starts, seed):
    """Fit every nuisance exclusively on the chronological first half."""

    return _fit(iq, valid, counter, starts, np.arange(18), seed)


def main() -> None:
    began = time.monotonic()
    selection = json.loads((REPORT / "selection.json").read_text())
    source = C.CachedReplayVisitSource(CACHE_INDEX, REPORT / "selection.json")
    pairs = _candidate_pairs()
    starts = _starts()
    rows = []
    for selected in selection["visits"]:
        visit_index = selected["visit_index"]
        base = {
            key: selected[key]
            for key in ("visit_index", "target_index", "channel", "time_bin", "split")
        }
        if visit_index not in pairs:
            rows.append({**base, "status": "no_phase_blind_dual_rx_pair"})
            continue
        visit = source.read_visit(visit_index)
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        first, second = pairs[visit_index]
        seed = float(second["tracking_absolute_baseband_cfo_hz"]) - float(
            first["tracking_absolute_baseband_cfo_hz"]
        )
        train, held = _split(starts, f"20260926:{visit_index}:method24-corrected")
        aliases, alias_scores, random_fit = _fit(
            iq, visit.valid_mask, selected["valid_start_counter"], starts, train, seed
        )
        forward_train = np.arange(18)
        forward_held = np.arange(18, 36)
        _, _, forward_fit = _fit_forward(
            iq, visit.valid_mask, selected["valid_start_counter"], starts, seed
        )
        random_frequency, random_rate = random_fit[1:]
        forward_frequency, forward_rate = forward_fit[1:]
        scores = {}
        for split_name, fit_train, fit_held, frequency, rate in (
            ("random", train, held, random_frequency, random_rate),
            ("forward", forward_train, forward_held, forward_frequency, forward_rate),
        ):
            for model, model_frequency, model_rate in (
                ("raw", 0.0, 0.0),
                ("constant_cfo", frequency, 0.0),
                ("cfo_rate", frequency, rate),
            ):
                for key, value in _score(
                    iq,
                    visit.valid_mask,
                    selected["valid_start_counter"],
                    starts,
                    fit_train,
                    fit_held,
                    model_frequency,
                    model_rate,
                ).items():
                    scores[f"{split_name}_{model}_{key}"] = value
        wrong = A.wrong_time_coherence(
            iq,
            visit.valid_mask,
            left_starts=starts,
            right_starts=A.wrong_time_starts(
                starts, visit_samples=1_200_000, window_samples=WINDOW
            ),
            window_samples=WINDOW,
            sample_rate_hz=RATE,
            relative_cfo_hz=random_frequency,
            relative_rate_hz_s=random_rate,
        )
        rows.append(
            {
                **base,
                "status": "completed",
                "rx0_candidate_rank": first["candidate_rank"],
                "rx1_candidate_rank": second["candidate_rank"],
                "phase_blind_seed_relative_cfo_hz": seed,
                "selected_alias_relative_cfo_hz": float(aliases[int(np.argmax(alias_scores))]),
                "selected_alias_training_median_coherence": max(alias_scores),
                "random_fitted_relative_cfo_hz": random_frequency,
                "random_fitted_relative_rate_hz_s": random_rate,
                "forward_fitted_relative_cfo_hz": forward_frequency,
                "forward_fitted_relative_rate_hz_s": forward_rate,
                "wrong_time_median_coherence": float(np.median(wrong)),
                **scores,
            }
        )
    fields = sorted({key for row in rows for key in row})
    output = HERE / "method24-corrected-direct-iq.csv"
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    complete = [row for row in rows if row["status"] == "completed"]
    evaluation = [row for row in complete if row["split"] == "evaluation"]
    summary = {
        "schema": "scan-phase-replay-dual-rx-corrected-direct/v1",
        "method_id": "24-direct-dual-rx-iq",
        "counts": {
            "eligible": 128,
            "phase_blind_paired": len(complete),
            "evaluation_paired": len(evaluation),
        },
        "window_samples": WINDOW,
        "alias_spacing_hz": ALIAS_HZ,
        "alias_selection": (
            "training-only median sample-level coherence over phase-blind seed "
            "+/- four symbol aliases"
        ),
        "evaluation_medians": {
            key: float(np.median([row[key] for row in evaluation]))
            for key in (
                "random_raw_r",
                "random_constant_cfo_r",
                "random_cfo_rate_r",
                "forward_raw_r",
                "forward_constant_cfo_r",
                "forward_cfo_rate_r",
                "random_cfo_rate_median_coherence",
                "wrong_time_median_coherence",
            )
        },
        "raw_baseline_disposition": (
            "method24-summary.json fitted columns invalid because mixing followed averaging; "
            "raw zero-CFO columns retained only as baseline"
        ),
        "runtime_wall_seconds": time.monotonic() - began,
    }
    (HERE / "method24-corrected-summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
