"""Report-only saved-IQ template and per-tone coherence diagnosis.

Run with the historical scientific source first on PYTHONPATH. No acquisition,
persisted-contract mutation, or production-code change occurs here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

import numpy as np

from leo.analysis.starlink import pilot_methods
from leo.analysis.starlink.fractional_epoch import fractional_take
from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S as TG,
)
from leo.analysis.starlink.templates import (
    OFDM_SYMBOL_DURATION_S as TS,
)
from leo.analysis.starlink.templates import (
    edge_frequencies_hz,
    qin_edge_pilot_frame,
    qin_edge_pilot_indices,
    qin_edge_pilot_symbols,
)
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.adaptive_hop import AdaptiveHopIqStore

# Frozen before loading any evaluation IQ. Same cells for both templates and
# the one-symbol-shift specificity control; no data-driven grid expansion.
TIMING_OFFSETS = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)
SETTINGS = {
    "timing_offsets_from_saved_fraction_samples": TIMING_OFFSETS,
    "timing_selection": "maximize exact-minus-independent-rolled-control margin",
    "additional_acquired_cfo_offsets_hz": [0.0],
    "symbol_inventory": [2, 65],
    "control_symbol_shift": 1,
    "glrt_frequency_cells_per_trial": 512,
    "coherence_tone_fit": "eight-tone least squares, useful interior samples, 64 symbols",
    "coherence_common_frame_phase": "removed separately; no across-frame phase continuity claim",
}


def center(edge):
    indexes = np.asarray(qin_edge_pilot_indices(edge))
    return float(np.mean(np.where(indexes < 512, indexes, indexes - 1024)) * 234375)


def bias(edge):
    return float((-center(edge) + 0.5 / TS) % (1 / TS) - 0.5 / TS)


@lru_cache(maxsize=16)
def physical_frame(sample_rate_hz, edge, *, symbol_roll=0):
    """Full-carrier OFDM followed by a continuous pilot-center mixer."""
    sample_times = np.arange(round(sample_rate_hz / 750)) / sample_rate_hz
    symbol = np.floor(sample_times / TS).astype(int)
    indexes = np.asarray(qin_edge_pilot_indices(edge))
    absolute_f = np.where(indexes < 512, indexes, indexes - 1024) * 234375
    codes = qin_edge_pilot_symbols(edge, symbol_roll=symbol_roll)
    valid = (symbol >= 2) & (symbol < 302)
    times = sample_times[valid]
    local = times - symbol[valid] * TS
    carrier = np.exp(
        2j * np.pi * ((local[:, None] - TG) * absolute_f - center(edge) * times[:, None])
    )
    result = np.zeros(len(sample_times), np.complex128)
    result[valid] = np.sum(carrier * codes[symbol[valid] - 2], axis=1) / np.sqrt(8)
    return result


def score_dict(score):
    return {
        "exact": score.exact_score,
        "control": score.control_score,
        "margin": score.margin,
        "residual_cfo_hz": score.residual_cfo_hz,
        "tracking_cfo_hz": score.tracking_cfo_hz,
    }


def score(iq, fs, edge, epoch, fraction, cfo):
    return pilot_methods.conditioned_glrt64_score(
        iq,
        fs,
        epoch_sample=epoch,
        fractional_epoch_offset_samples=fraction,
        acquired_cfo_hz=cfo,
        edge=edge,
    )


def matched_surface(iq, fs, edge, epoch, fraction, cfo, physical=False, shift=0):
    trials = []
    template = physical_frame if physical else qin_edge_pilot_frame
    corrected_cfo = cfo - bias(edge) if physical else cfo
    with patch.object(pilot_methods, "qin_edge_pilot_frame", template):
        for offset in TIMING_OFFSETS:
            s = score(iq, fs, edge, epoch + shift, fraction + offset, corrected_cfo)
            trials.append({"offset_samples": offset, **score_dict(s)})
    best = max(trials, key=lambda t: t["margin"])
    return {"best": best, "trials": trials}


def summarize_gains(gains, times, frequencies):
    """Describe empirical coefficients without calling them analog calibration."""
    gains = np.asarray(gains)
    frame_phase = np.angle(np.sum(gains, axis=(1, 2)))
    aligned = gains * np.exp(-1j * frame_phase[:, None, None])
    mean_gain = np.mean(aligned, axis=(0, 1))
    coherence = np.abs(np.sum(gains, axis=1)) / np.maximum(np.sum(np.abs(gains), axis=1), 1e-20)
    amplitude = np.abs(mean_gain)
    norm = max(float(np.median(amplitude)), 1e-20)
    phase = np.unwrap(np.angle(mean_gain))
    slope, intercept = np.polyfit(frequencies, phase, 1)
    phase_residual = phase - (slope * frequencies + intercept)
    # Each frame has independent phase. A small residual phase-time slope is
    # a diagnostic, not a fitted clock correction or inferred oscillator error.
    temporal_slopes = []
    for frame in gains:
        common = np.sum(frame, axis=1)
        phase_time = np.unwrap(np.angle(common))
        weights = np.abs(common)
        if np.max(weights) > 0:
            temporal_slopes.append(
                float(np.polyfit(times, phase_time, 1, w=weights)[0] / (2 * np.pi))
            )
    # Relative phase per tone to each symbol's common gain removes common CFO.
    # Frequency slope in each symbol yields an apparent delay, then apparent
    # sample-clock drift across symbols; multipath/noise can mimic it.
    delay_slopes = []
    for frame in gains:
        common = np.mean(frame, axis=1)
        relative = frame / np.where(np.abs(common[:, None]) > 1e-20, common[:, None], 1)
        tone_phase = np.unwrap(np.angle(relative), axis=1)
        apparent_delays = np.array(
            [np.polyfit(frequencies, row, 1)[0] / (-2 * np.pi) for row in tone_phase]
        )
        delay_slopes.append(float(np.polyfit(times, apparent_delays, 1)[0] * 1e6))
    return {
        "frames": int(len(gains)),
        "symbols_per_frame": int(gains.shape[1]),
        "tone_gain_real": mean_gain.real.tolist(),
        "tone_gain_imag": mean_gain.imag.tolist(),
        "tone_relative_amplitude_db": (20 * np.log10(np.maximum(amplitude / norm, 1e-20))).tolist(),
        "tone_coherence_median": np.median(coherence, axis=0).tolist(),
        "amplitude_spread_db": float(
            20 * np.log10(max(amplitude.max(), 1e-20) / max(amplitude.min(), 1e-20))
        ),
        "phase_slope_apparent_delay_ns": float(-slope / (2 * np.pi) * 1e9),
        "phase_slope_residual_rms_rad": float(np.sqrt(np.mean(phase_residual**2))),
        "residual_common_phase_time_slope_hz_median": float(np.median(temporal_slopes)),
        "apparent_clock_drift_ppm_median": float(np.median(delay_slopes)),
        "frame_median_tone_coherence": np.median(coherence, axis=1).tolist(),
        "symbol_gain_phase_rad_first_frame": np.angle(gains[0]).tolist(),
        "symbol_common_amplitude_first_frame": np.abs(np.mean(gains[0], axis=1)).tolist(),
    }


def per_tone_projection(iq, fs, edge, epoch, fraction, physical_cfo):
    symbols = np.arange(2, 66)
    frequencies = edge_frequencies_hz(edge)
    codes = qin_edge_pilot_symbols(edge)[symbols - 2]
    models = []
    for symbol in symbols:
        indexes = np.arange(round(symbol * TS * fs), round((symbol + 1) * TS * fs))
        local = indexes / fs - symbol * TS
        indexes = indexes[(local >= TG) & (local < TS)]
        t = indexes / fs
        local = t - symbol * TS
        design = np.exp(
            2j * np.pi * ((local[:, None] - TG) * frequencies - center(edge) * (symbol * TS + TG))
        ) / np.sqrt(8)
        models.append((indexes, np.linalg.pinv(design)))
    frames = []
    frame = 0
    while True:
        start = epoch + round(frame * fs / 750)
        if start + models[-1][0][-1] + fraction >= len(iq) - 8:
            break
        if start + models[0][0][0] + fraction < 8:
            frame += 1
            continue
        gains = []
        for s, (relative, inverse) in enumerate(models):
            absolute = start + relative.astype(float) + fraction
            received = fractional_take(iq, absolute)
            corrected = received * np.exp(-2j * np.pi * physical_cfo * absolute / fs)
            gains.append((inverse @ corrected) / codes[s])
        frames.append(gains)
        frame += 1
    return summarize_gains(np.asarray(frames), symbols * TS, frequencies)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    report = {
        "settings": SETTINGS,
        "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "scientific_source": spec["scientific_source"],
        "selection": spec["selection"],
        "results": [],
    }
    # Save settings before any IQ evaluation as a reproducible freeze record.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    store = AdaptiveHopIqStore(Path(spec["bulk_root"]), read_only=True)
    started = time.monotonic()
    try:
        for scan in spec["scans"]:
            fs, edge, sid = scan["rate"], scan["edge"], scan["session_id"]
            with store.reader(sid) as reader:
                assert (
                    sha256_digest(
                        canonical_json_bytes(reader.session.manifest.model_dump(mode="json"))
                    )
                    == reader.session.manifest_sha256
                )
                retained = {
                    v.event.visit_index: i
                    for i, v in enumerate(reader.session.manifest.receipt.visits)
                }
                for example in sorted(scan["examples"], key=lambda e: e["visit_index"]):
                    visit, ci16 = reader.read_visit_ci16(retained[example["visit_index"]])
                    assert visit.event.visit_index == example["visit_index"]
                    rx = example["receiver_id"]
                    # Reader validates compressed and uncompressed chunk SHA-256.
                    start = example["probe_start_ms"] * fs // 1000
                    raw = ci16[start : start + fs // 50, rx, :]
                    iq = raw[:, 0].astype(float) + 1j * raw[:, 1].astype(float)
                    w = example["candidate"]
                    epoch, fraction, cfo = (
                        w["integer_epoch_sample"],
                        w["fractional_epoch_offset_samples"],
                        w["acquired_cfo_hz"],
                    )
                    assert (
                        int(w["integer_device_sample_counter"])
                        == visit.event.valid_start_counter + start + epoch
                    )
                    integer = score(iq, fs, edge, epoch, 0.0, cfo)
                    baseline = score(iq, fs, edge, epoch, fraction, cfo)
                    errors = {}
                    for label, sc in (("integer", integer), ("fractional", baseline)):
                        errors[label] = max(
                            abs(getattr(sc, field) - w[f"{label}_{saved}"])
                            for field, saved in (
                                ("exact_score", "exact_score"),
                                ("control_score", "control_score"),
                                ("margin", "margin"),
                                ("residual_cfo_hz", "residual_cfo_hz"),
                                ("tracking_cfo_hz", "tracking_cfo_hz"),
                            )
                        )
                        assert errors[label] < 1e-7, (sid, example["lane"], errors)
                    legacy = matched_surface(iq, fs, edge, epoch, fraction, cfo)
                    physical = matched_surface(iq, fs, edge, epoch, fraction, cfo, physical=True)
                    shift = round(fs * TS)
                    shifted_legacy = matched_surface(
                        iq, fs, edge, epoch, fraction, cfo, shift=shift
                    )
                    shifted_physical = matched_surface(
                        iq, fs, edge, epoch, fraction, cfo, physical=True, shift=shift
                    )
                    chosen = physical["best"]
                    projection = per_tone_projection(
                        iq,
                        fs,
                        edge,
                        epoch,
                        fraction + chosen["offset_samples"],
                        chosen["tracking_cfo_hz"],
                    )
                    result = {
                        "session_id": sid,
                        "split": scan["split"],
                        "rate": fs,
                        "edge": edge,
                        "channel": example["channel"],
                        "receiver_id": rx,
                        "lane": example["lane"],
                        "visit_index": example["visit_index"],
                        "retained_reader_index": retained[example["visit_index"]],
                        "candidate_rank": w["candidate_rank"],
                        "epoch": epoch,
                        "saved_fraction_samples": fraction,
                        "acquired_cfo_hz": cfo,
                        "cfo_bias_hz": bias(edge),
                        "input_manifest_sha256": reader.session.manifest_sha256,
                        "probe_ci16_sha256": hashlib.sha256(
                            raw.astype("<i2").tobytes()
                        ).hexdigest(),
                        "counter_asserted": True,
                        "chunk_hashes_asserted_by_reader": True,
                        "saved_reproduction_max_errors": errors,
                        "baseline": score_dict(baseline),
                        "legacy": legacy,
                        "physical": physical,
                        "plus_symbol_legacy": shifted_legacy,
                        "plus_symbol_physical": shifted_physical,
                        "projection": projection,
                    }
                    report["results"].append(result)
                    report["elapsed_seconds"] = time.monotonic() - started
                    args.output.write_text(json.dumps(report, indent=2))
                    print(
                        f"{len(report['results']):2} {scan['split']:11} {sid} "
                        f"{example['lane']:12} margin {baseline.margin:.4f} "
                        f"-> {physical['best']['margin']:.4f}; "
                        f"elapsed {report['elapsed_seconds']:.1f}s",
                        flush=True,
                    )
    finally:
        store.close()


if __name__ == "__main__":
    main()
