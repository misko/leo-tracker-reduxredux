"""Replay exact Qin dual-RX receiver products on sparse acquired support."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from leo.analysis.qam.pilot import (
    _complete_frame_starts,
    _fit_phase_slope_frame,
    _KnownPilotDemodulator,
)
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_symbols,
)

HERE = Path(__file__).parent
REPORT = HERE.parent
CACHE = Path("/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json")


def _common():
    spec = importlib.util.spec_from_file_location("phase_replay_common", REPORT / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _common()


def _pairs() -> dict[int, tuple[dict, dict]]:
    grouped = defaultdict(lambda: defaultdict(list))
    with (REPORT / "acquisition/candidate-inventory.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["passed_0p025_comparison_gate"] == "True":
                grouped[int(row["visit_index"])][int(row["receiver_id"])].append(row)
    result = {}
    for visit, by_rx in grouped.items():
        if 0 in by_rx and 1 in by_rx:
            result[visit] = tuple(
                max(
                    by_rx[receiver],
                    key=lambda row: (
                        float(row["fractional_margin"]),
                        -int(row["candidate_rank"]),
                    ),
                )
                for receiver in (0, 1)
            )
    return result


def _frames(samples, candidate, edge):
    epoch = int(candidate["integer_epoch_sample"])
    fractional = float(candidate["fractional_epoch_offset_samples"])
    cfo = float(candidate["tracking_absolute_baseband_cfo_hz"])
    starts = _complete_frame_starts(
        len(samples), 10_000_000, epoch, fractional_epoch_offset_samples=fractional
    )
    exact = qin_edge_pilot_symbols(edge)
    control = qin_edge_pilot_symbols(edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    symbol_time = (np.arange(300) + 2.5) * OFDM_SYMBOL_DURATION_S
    centered = symbol_time - np.mean(symbol_time)
    demodulator = _KnownPilotDemodulator(samples, 10_000_000, edge, cfo)
    output = []
    for start in starts:
        pilots = demodulator.frame(start, fractional_epoch_offset_samples=fractional)
        fit = _fit_phase_slope_frame(
            pilots * np.conj(exact),
            pilots * np.conj(control),
            centered,
            maximum_residual_cfo_hz=2_000.0,
        )
        channel = np.asarray(fit.channel_vector, dtype=np.complex128)
        output.append(
            {
                "reference_sample": float(start + fractional + np.mean(symbol_time) * 10_000_000),
                "channel": channel,
                "residual_cfo_hz": float(fit.residual_cfo_hz),
                "absolute_cfo_hz": cfo + float(fit.residual_cfo_hz),
                "exact_coherence": float(fit.exact_coherence),
                "control_coherence": float(fit.control_coherence),
            }
        )
    return output


def main() -> None:
    selection = json.loads((REPORT / "selection.json").read_text())
    selected_ids = {row["visit_index"] for row in selection["visits"]}
    source = C.CachedReplayVisitSource(CACHE, REPORT / "selection.json")
    pairs = _pairs()
    observations = []
    accounting = []
    for selected in selection["visits"]:
        visit_index = selected["visit_index"]
        if visit_index not in pairs:
            accounting.append({"visit_index": visit_index, "status": "no_dual_rx_acquisition"})
            continue
        visit = source.read_visit(visit_index)
        candidates = pairs[visit_index]
        receiver_frames = [
            _frames(visit.complex64(receiver), candidates[receiver], selected["edge"])
            for receiver in (0, 1)
        ]
        matched = 0
        for left in receiver_frames[0]:
            if not receiver_frames[1]:
                continue
            right = min(
                receiver_frames[1],
                key=lambda row: abs(row["reference_sample"] - left["reference_sample"]),
            )
            separation = abs(right["reference_sample"] - left["reference_sample"])
            if separation > 3.0:
                continue
            common_reference = 0.5 * (left["reference_sample"] + right["reference_sample"])
            restoration = np.exp(
                2j
                * np.pi
                * (right["absolute_cfo_hz"] - left["absolute_cfo_hz"])
                * common_reference
                / 10_000_000
            )
            product = np.conj(left["channel"]) * right["channel"] * restoration
            observations.append(
                {
                    "visit_index": visit_index,
                    "target_index": selected["target_index"],
                    "channel": selected["channel"],
                    "split": selected["split"],
                    "device_counter_reference": selected["valid_start_counter"]
                    + round(0.5 * (left["reference_sample"] + right["reference_sample"])),
                    "reference_separation_samples": separation,
                    "rx0_residual_cfo_hz": left["residual_cfo_hz"],
                    "rx1_residual_cfo_hz": right["residual_cfo_hz"],
                    "exact_coherence_min": min(left["exact_coherence"], right["exact_coherence"]),
                    "control_margin_min": min(
                        left["exact_coherence"] - left["control_coherence"],
                        right["exact_coherence"] - right["control_coherence"],
                    ),
                    "tone_products_real": product.real.tolist(),
                    "tone_products_imag": product.imag.tolist(),
                    "raw_product_phase_rad": float(np.angle(np.sum(product))),
                    "raw_product_coherence": float(
                        abs(np.sum(product)) / max(float(np.sum(abs(product))), 1e-30)
                    ),
                    "phase_reference": (
                        "raw sample gauge restored at local common_reference_sample; "
                        "device counter retained for cross-visit transport"
                    ),
                }
            )
            matched += 1
        accounting.append(
            {
                "visit_index": visit_index,
                "status": "completed" if matched else "no_common_frame",
                "common_frame_count": matched,
            }
        )
    # Development-only response by target and tone; evaluation cannot alter it.
    response = {}
    for target in (4, 5, 6, 7):
        rows = [
            r for r in observations if r["target_index"] == target and r["split"] == "development"
        ]
        vectors = [
            np.asarray(r["tone_products_real"]) + 1j * np.asarray(r["tone_products_imag"])
            for r in rows
        ]
        if vectors:
            response[target] = np.mean(np.asarray(vectors), axis=0)
    for row in observations:
        vector = np.asarray(row["tone_products_real"]) + 1j * np.asarray(row["tone_products_imag"])
        trained = response.get(row["target_index"])
        if trained is None or np.any(abs(trained) <= np.finfo(float).tiny):
            row["response_normalized_a_phase_rad"] = None
            row["response_normalized_b_phase_rad"] = None
            continue
        normalized = vector / trained
        row["response_normalized_a_phase_rad"] = float(np.angle(np.sum(normalized[::2])))
        row["response_normalized_b_phase_rad"] = float(np.angle(np.sum(normalized[1::2])))
    window_rows = []
    by_visit = defaultdict(list)
    for row in observations:
        by_visit[row["visit_index"]].append(row)
    selection_by_visit = {row["visit_index"]: row for row in selection["visits"]}
    for visit_index, visit_rows in by_visit.items():
        origin = selection_by_visit[visit_index]["valid_start_counter"]
        for duration_ms in (23, 47, 95):
            duration = duration_ms * 10_000
            for start in range(0, 1_200_000 - duration + 1, duration):
                contained = [
                    row
                    for row in visit_rows
                    if origin + start <= row["device_counter_reference"] < origin + start + duration
                ]
                if len(contained) < 3:
                    continue
                phasors = np.exp(
                    1j * np.asarray([row["raw_product_phase_rad"] for row in contained])
                )
                window_rows.append(
                    {
                        "visit_index": visit_index,
                        "split": selection_by_visit[visit_index]["split"],
                        "duration_ms": duration_ms,
                        "device_counter_start": origin + start,
                        "device_counter_stop_exclusive": origin + start + duration,
                        "common_frame_count": len(contained),
                        "raw_phase_rad": float(np.angle(np.sum(phasors))),
                        "frame_phase_r": float(abs(np.mean(phasors))),
                    }
                )
    path = HERE / "method21-23-pilot-observations.json"
    path.write_text(json.dumps({"observations": observations, "accounting": accounting}) + "\n")
    (HERE / "method22-common-windows.json").write_text(json.dumps(window_rows) + "\n")
    evaluation = [r for r in observations if r["split"] == "evaluation"]
    band_error = [
        float(
            np.angle(
                np.exp(
                    1j
                    * (r["response_normalized_a_phase_rad"] - r["response_normalized_b_phase_rad"])
                )
            )
        )
        for r in evaluation
        if r["response_normalized_a_phase_rad"] is not None
    ]
    summary = {
        "schema": "scan-phase-replay-dual-rx-pilot/v1",
        "methods": ["21-dual-rx-pilot-double-difference", "23-response-normalized-disjoint-band"],
        "counts": {
            "eligible_visits": 128,
            "dual_rx_acquired_visits": len(selected_ids & pairs.keys()),
            "visits_with_common_frames": len({r["visit_index"] for r in observations}),
            "common_frames": len(observations),
            "evaluation_common_frames": len(evaluation),
        },
        "response_training": "development visits only, separate complex response per target/tone",
        "evaluation_disjoint_band": {
            "count": len(band_error),
            "a_b_phase_r": float(abs(np.mean(np.exp(1j * np.asarray(band_error)))))
            if band_error
            else None,
            "a_b_phase_rms_deg": float(np.degrees(np.sqrt(np.mean(np.asarray(band_error) ** 2))))
            if band_error
            else None,
        },
        "double_difference_status": (
            "not_evaluated_here: requires two phase-blind same-signal pairs in one receiver/probe"
        ),
        "method22_common_windows": {
            str(duration): {
                "count": sum(row["duration_ms"] == duration for row in window_rows),
                "evaluation_count": sum(
                    row["duration_ms"] == duration and row["split"] == "evaluation"
                    for row in window_rows
                ),
                "evaluation_median_frame_phase_r": float(
                    np.median(
                        [
                            row["frame_phase_r"]
                            for row in window_rows
                            if row["duration_ms"] == duration and row["split"] == "evaluation"
                        ]
                    )
                ),
            }
            for duration in (23, 47, 95)
        },
    }
    (HERE / "method21-23-summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
