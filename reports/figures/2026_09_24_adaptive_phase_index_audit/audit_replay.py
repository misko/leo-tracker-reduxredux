"""Read-only perturbation replay for the frozen adaptive relative-phase scan.

This is an audit artifact.  It imports the deployed release without changing
the stored analysis, capture, or production source tree.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import ReceiverPhaseSeed
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking
from leo.analysis.starlink.relative_phase import (
    PairedPilotProbe,
    normalize_response,
    refined_pilot,
)
from leo.application.adaptive_relative_phase import relative_phase_probes
from leo.scanner.adaptive_hop_analysis import analyze_adaptive_hop_visit
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

ROOT = Path("/srv/bulk/leo")
SESSION = "scan-fw-1aa1d50103d97388"
VISITS = (569, 590, 1677, 324)
NFFT = 4096


def r_of_errors(errors: np.ndarray) -> float:
    return float(abs(np.mean(np.exp(1j * np.asarray(errors)))))


def broad_r(
    values: np.ndarray,
    rate: float,
    probes: tuple[PairedPilotProbe, ...],
    *,
    cfo_delta_hz: float = 0.0,
    response_bin_delta: int = 0,
    swap_receivers: bool = False,
    wrong_cfo_sign: bool = False,
) -> dict[str, float | int]:
    """Replicate the broadband R path with exactly one declared perturbation."""
    iq = np.asarray(values[:, ::-1] if swap_receivers else values)
    training = [p for p in probes if p.start_sample + rate * 20 // 1000 <= len(iq) // 2]
    if not training:
        raise ValueError("no training probes")
    seed = float(
        np.median([p.seeds[1].acquired_cfo_hz - p.seeds[0].acquired_cfo_hz for p in training])
    )
    if swap_receivers:
        seed = -seed
    model = estimate_broadband_alignment(
        iq, rate, receiver_cfo_seed_hz=seed, cfo_search_half_width_hz=900_000
    ).model
    changed_cfo = model.relative_cfo_hz + cfo_delta_hz
    if wrong_cfo_sign:
        changed_cfo = -model.relative_cfo_hz
    model = replace(model, relative_cfo_hz=changed_cfo)

    def carrier(sample: np.ndarray) -> np.ndarray:
        dt = (np.asarray(sample) - model.reference_sample) / rate
        return 2 * np.pi * (model.relative_cfo_hz * dt + 0.5 * model.relative_cfo_rate_hz_s * dt**2)

    frequencies = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / rate))
    left, right = [], []
    split = len(iq) // 2
    for start in range(0, split - NFFT + 1, NFFT):
        window = np.hanning(NFFT)
        left.append(np.fft.fftshift(np.fft.fft(iq[start : start + NFFT, 0] * window)))
        right.append(
            np.fft.fftshift(
                np.fft.fft(
                    iq[start : start + NFFT, 1]
                    * np.exp(-1j * carrier(np.arange(start, start + NFFT)))
                    * window
                )
            )
        )
    eligible = abs(frequencies) < rate / 2 - 40_000
    shifts = [
        model.relative_cfo_hz + model.relative_cfo_rate_hz_s * (s - model.reference_sample) / rate
        for s in (0, len(iq) - 1)
    ]
    for shift in shifts:
        eligible &= abs(frequencies + shift) < rate / 2 - 40_000
    initial = np.searchsorted(frequencies, model.frequency_hz) + response_bin_delta
    ids, transfer = normalize_response(
        np.asarray(left), np.asarray(right), frequencies, initial, model.channel_transfer, eligible
    )
    updated = replace(model, frequency_hz=tuple(frequencies[ids]), channel_transfer=tuple(transfer))
    held = frequency_held_out_tracking(iq, rate, updated)
    errors = np.asarray([row["held_band_residual_phase_rad"] for row in held["rows"]])
    return {
        "band_R": r_of_errors(errors),
        "rms_deg": float(np.degrees(np.sqrt(np.mean(errors**2)))),
        "tracked_coherence": float(held["tracked"]["coherence"]),
        "wrong_time_coherence": float(held["wrong_time"]["coherence"]),
        "relative_cfo_hz": float(model.relative_cfo_hz),
        "frequency_reference_hz": float(model.frequency_reference_hz),
        "retained_bins": int(len(ids)),
    }


def pilot_r(
    values: np.ndarray,
    rate: float,
    edge: str,
    probe: PairedPilotProbe,
    *,
    frame_shift_samples: int = 0,
    symbol_shift: int = 0,
    authority_delta_hz: float = 0.0,
    swap_receivers: bool = False,
    wrong_edge: bool = False,
) -> dict[str, float | int]:
    """Replay one source with frame/symbol/CFO/channel perturbations."""
    iq = np.asarray(values[:, ::-1] if swap_receivers else values)
    seeds = probe.seeds[::-1] if swap_receivers else probe.seeds
    authority = seeds[1].acquired_cfo_hz - seeds[0].acquired_cfo_hz + authority_delta_hz
    changed = PairedPilotProbe(
        probe.start_sample,
        probe.epoch_sample + frame_shift_samples,
        tuple(ReceiverPhaseSeed(seed.acquired_cfo_hz, seed.reference_sample) for seed in seeds),
    )
    # The normal path uses a contiguous [2, 65] grid; intentionally move the whole grid.
    if symbol_shift:
        from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
            extract_dual_receiver_phase_with_offset_authority_shared_residual,
        )

        result = extract_dual_receiver_phase_with_offset_authority_shared_residual(
            iq[changed.start_sample : changed.start_sample + rate * 20 // 1000],
            rate,
            "lower" if (wrong_edge and edge == "upper") else "upper" if wrong_edge else edge,
            changed.epoch_sample,
            changed.seeds,
            authority,
            common_reference_sample=0,
            frame_radius=16,
            symbol_indices=np.arange(2 + symbol_shift, 66 + symbol_shift),
        ).observation
    else:
        result = refined_pilot(
            iq[changed.start_sample : changed.start_sample + rate * 20 // 1000],
            rate,
            "lower" if (wrong_edge and edge == "upper") else "upper" if wrong_edge else edge,
            changed,
            authority,
        )
    return {
        "pilot_R": float(result.resultant_length),
        "phase_deg": float(np.degrees(result.wrapped_phase_rad)),
        "relative_frequency_hz": float(result.relative_frequency_hz),
        "frame_count": int(result.independent_frame_count),
        "center_sample": float(result.center_sample),
    }


def main() -> None:
    store = AdaptiveHopIqStore(ROOT, read_only=True)
    try:
        capture = store.inspect(SESSION)
        binding = bind_actual_visit_analysis(
            capture.manifest.receipt,
            input_manifest_sha256=capture.manifest_sha256,
            probe_stride_ms=120,
        )
        config = binding.configuration.model_copy(update={"probe_stride_ms": 20})
        with AdaptiveHopAnalysisInputStore(store).source(SESSION) as source:
            ordinals = {row.event.visit_index: index for index, row in enumerate(source.visits)}
            output: dict[str, object] = {
                "session_id": SESSION,
                "sample_rate_hz": config.sample_rate_hz,
                "fft_size": NFFT,
                "fft_bin_hz": config.sample_rate_hz / NFFT,
                "visits": [],
            }
            for visit in VISITS:
                ordinal = ordinals[visit]
                analysis = analyze_adaptive_hop_visit(source, ordinal, configuration=config)
                probes = relative_phase_probes(analysis)
                iq = source.read_visit(ordinal)
                row: dict[str, object] = {
                    "visit_index": visit,
                    "iq_ordinal": ordinal,
                    "channel": analysis.target.channel,
                    "edge": str(analysis.target.edge),
                    "probe_count": len(probes),
                    "broadband": [],
                    "pilot": [],
                }
                broad_cases = [
                    ("nominal", {}),
                    ("cfo_minus_1_fft_bin", {"cfo_delta_hz": -config.sample_rate_hz / NFFT}),
                    ("cfo_plus_1_fft_bin", {"cfo_delta_hz": config.sample_rate_hz / NFFT}),
                    ("cfo_minus_2_fft_bins", {"cfo_delta_hz": -2 * config.sample_rate_hz / NFFT}),
                    ("cfo_plus_2_fft_bins", {"cfo_delta_hz": 2 * config.sample_rate_hz / NFFT}),
                    ("response_bin_minus_1", {"response_bin_delta": -1}),
                    ("response_bin_plus_1", {"response_bin_delta": 1}),
                    ("response_bin_minus_2", {"response_bin_delta": -2}),
                    ("response_bin_plus_2", {"response_bin_delta": 2}),
                    ("rx_swap_consistent", {"swap_receivers": True}),
                    ("cfo_sign_reversed", {"wrong_cfo_sign": True}),
                ]
                for name, kwargs in broad_cases:
                    try:
                        row["broadband"].append({"case": name, **broad_r(iq, config.sample_rate_hz, probes, **kwargs)})
                    except Exception as exc:  # record an invalid perturbation, never hide it
                        row["broadband"].append({"case": name, "failure": str(exc)})
                if probes:
                    probe = probes[0]
                    pilot_cases = [
                        ("nominal", {}),
                        ("frame_minus_1_sample", {"frame_shift_samples": -1}),
                        ("frame_plus_1_sample", {"frame_shift_samples": 1}),
                        ("frame_minus_2_samples", {"frame_shift_samples": -2}),
                        ("frame_plus_2_samples", {"frame_shift_samples": 2}),
                        ("symbol_minus_1", {"symbol_shift": -1}),
                        ("symbol_plus_1", {"symbol_shift": 1}),
                        ("symbol_minus_2", {"symbol_shift": -2}),
                        ("symbol_plus_2", {"symbol_shift": 2}),
                        ("authority_minus_1_fft_bin", {"authority_delta_hz": -config.sample_rate_hz / NFFT}),
                        ("authority_plus_1_fft_bin", {"authority_delta_hz": config.sample_rate_hz / NFFT}),
                        ("rx_swap_consistent", {"swap_receivers": True}),
                        ("wrong_edge", {"wrong_edge": True}),
                    ]
                    for name, kwargs in pilot_cases:
                        try:
                            row["pilot"].append({"case": name, **pilot_r(iq, config.sample_rate_hz, str(analysis.target.edge), probe, **kwargs)})
                        except Exception as exc:
                            row["pilot"].append({"case": name, "failure": str(exc)})
                output["visits"].append(row)
    finally:
        store.close()
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
