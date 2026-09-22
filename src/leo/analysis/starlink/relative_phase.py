"""Within-dwell relative phase with training-only response and matched pilot checks.

Pure numerical implementation; no recording, report, or transport dependencies.
"""

from dataclasses import dataclass, replace

import numpy as np
from scipy.signal import fftconvolve, firwin

from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    ReceiverPhaseSeed,
    extract_dual_receiver_phase_with_offset_authority_shared_residual,
)
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking


@dataclass(frozen=True)
class PairedPilotProbe:
    start_sample: int
    epoch_sample: int
    seeds: tuple[ReceiverPhaseSeed, ReceiverPhaseSeed]


def wrap(value):
    return np.angle(np.exp(1j * value))


def normalize_response(left, right, frequency, initial_indexes, initial_transfer, eligible):
    kernel = np.ones(31) / 31
    p0 = np.convolve(np.sum(abs(left) ** 2, axis=0), kernel, "same")
    p1 = np.convolve(np.sum(abs(right) ** 2, axis=0), kernel, "same")
    indexes = np.asarray(initial_indexes)
    transfer = np.asarray(initial_transfer)
    for _ in range(3):
        a = (indexes % 64 >= 4) & (indexes % 64 < 60) & ((indexes // 64) % 2 == 0)
        if not np.any(a):
            raise ValueError("No A-band support for response normalization")
        phase = np.angle(
            np.sum(np.conj(left[:, indexes[a]] * transfer[a]) * right[:, indexes[a]], axis=1)
        )
        corrected = right * np.exp(-1j * phase[:, None])
        cross = np.convolve(np.sum(np.conj(left) * corrected, axis=0), kernel, "same")
        denominator = np.sqrt(np.maximum(p0 * p1, 1e-30))
        null = np.convolve(
            np.sum(np.conj(left) * np.roll(corrected, 7, axis=0), axis=0), kernel, "same"
        )
        if not np.any(eligible):
            raise ValueError("No physical common bandwidth")
        gate = max(0.05, 3 * float(np.median(abs(null[eligible]) / denominator[eligible])))
        indexes = np.flatnonzero(eligible & (abs(cross) / denominator >= gate))
        if len(indexes) < 8:
            raise ValueError("No qualified shared response")
        transfer = cross[indexes] / np.maximum(p0[indexes], 1e-30)
    return indexes, transfer


def refined_pilot(iq, rate, edge, probe, authority):
    fn = extract_dual_receiver_phase_with_offset_authority_shared_residual
    first = fn(
        iq,
        rate,
        edge,
        probe.epoch_sample,
        probe.seeds,
        authority,
        common_reference_sample=0,
        frame_radius=16,
    ).observation
    if abs(first.relative_frequency_hz - authority) >= 375:
        raise ValueError("Pilot refinement leaves common frequency branch")
    return fn(
        iq,
        rate,
        edge,
        probe.epoch_sample,
        probe.seeds,
        first.relative_frequency_hz,
        common_reference_sample=0,
        frame_radius=16,
    ).observation


def extract_relative_phase(iq, rate, edge, probes):
    """Return scalar trajectory, disjoint-band checks and matched-frame pilot phase.

    Each call is one retuned dwell. No phase continuity across calls is inferred.
    Pilot association is supplied by the caller without phase-based selection.
    """
    values = np.asarray(iq)
    split = len(values) // 2
    training = [p for p in probes if p.start_sample + rate * 20 // 1000 <= split]
    if not training:
        raise ValueError("No training-half paired pilot frequency evidence")
    seed = float(
        np.median([p.seeds[1].acquired_cfo_hz - p.seeds[0].acquired_cfo_hz for p in training])
    )
    model = estimate_broadband_alignment(
        values, rate, receiver_cfo_seed_hz=seed, cfo_search_half_width_hz=900_000
    ).model

    def carrier(sample):
        dt = (np.asarray(sample) - model.reference_sample) / rate
        return 2 * np.pi * (model.relative_cfo_hz * dt + 0.5 * model.relative_cfo_rate_hz_s * dt**2)

    n = 4096
    frequencies = np.fft.fftshift(np.fft.fftfreq(n, 1 / rate))
    left, right = [], []
    for start in range(0, split - n + 1, n):
        window = np.hanning(n)
        left.append(np.fft.fftshift(np.fft.fft(values[start : start + n, 0] * window)))
        right.append(
            np.fft.fftshift(
                np.fft.fft(
                    values[start : start + n, 1]
                    * np.exp(-1j * carrier(np.arange(start, start + n)))
                    * window
                )
            )
        )
    eligible = abs(frequencies) < rate / 2 - 40000
    shifts = [
        model.relative_cfo_hz + model.relative_cfo_rate_hz_s * (s - model.reference_sample) / rate
        for s in (0, len(values) - 1)
    ]
    for shift in shifts:
        eligible &= abs(frequencies + shift) < rate / 2 - 40000
    ids, transfer = normalize_response(
        np.array(left),
        np.array(right),
        frequencies,
        np.searchsorted(frequencies, model.frequency_hz),
        model.channel_transfer,
        eligible,
    )
    updated = replace(model, frequency_hz=tuple(frequencies[ids]), channel_transfer=tuple(transfer))
    held = frequency_held_out_tracking(values, rate, updated)
    error = np.array([r["held_band_residual_phase_rad"] for r in held["rows"]])
    resultant = float(abs(np.mean(np.exp(1j * error))))
    supported = (
        held["tracked"]["coherence"] > max(0.05, 3 * held["wrong_time"]["coherence"])
        and resultant > 0.8
    )
    # Correct delay and restrict to the physical common recorded band, never FFT-wrap it.
    aligned = values.copy()
    y = values[:, 1] * np.exp(-1j * carrier(np.arange(len(values))))
    taps = np.sinc(np.arange(-32, 33) + model.fractional_delay_samples) * np.hanning(65)
    y = fftconvolve(y, taps / taps.sum(), mode="same")
    low = max([-rate / 2] + [-rate / 2 - s for s in shifts]) + 40000
    high = min([rate / 2] + [rate / 2 - s for s in shifts]) - 40000
    if high <= low:
        raise ValueError("No usable physical common bandwidth")
    taps = firwin(513, (high - low) / 2, fs=rate) * np.exp(
        2j * np.pi * (high + low) / 2 * (np.arange(513) - 256) / rate
    )
    aligned[:, 0] = fftconvolve(values[:, 0], taps, mode="same")
    aligned[:, 1] = fftconvolve(y, taps, mode="same")
    size, stride = rate // 2000, rate // 5000
    times, phases, coherences = [], [], []
    for start in range(size, len(values) - 2 * size, stride):
        x, y = aligned[start : start + size].T
        z = np.vdot(x, y)
        times.append((start + (size - 1) / 2) / rate)
        phases.append(float(np.angle(z)))
        coherences.append(
            float(abs(z) / max(np.sqrt(np.vdot(x, x).real * np.vdot(y, y).real), 1e-30))
        )
    unwrapped = np.unwrap(phases)
    observations, failures = [], []
    for probe in probes:
        start = probe.start_sample
        stop = start + rate * 20 // 1000
        authority = (
            model.relative_cfo_hz
            + model.relative_cfo_rate_hz_s * ((start + stop) / 2 - model.reference_sample) / rate
        )
        try:
            obs = refined_pilot(values[start:stop], rate, edge, probe, authority)
            center = (start + obs.center_sample) / rate
            frames = (start + np.asarray(obs.receivers[0].frame_starts)) / rate
            if min(frames) < min(times) or max(frames) > max(times):
                raise ValueError("Pilot frames outside valid broadband centers")
            weights = np.sqrt(
                abs(np.asarray(obs.receivers[0].frame_phasors))
                * abs(np.asarray(obs.receivers[1].frame_phasors))
            )
            basef = model.relative_cfo_hz + model.relative_cfo_rate_hz_s * (
                center - model.reference_sample / rate
            )
            phasors = np.exp(
                1j
                * (
                    np.interp(frames, times, unwrapped)
                    + carrier(frames * rate)
                    - carrier(center * rate)
                    - 2 * np.pi * basef * (frames - center)
                )
            )
            frequency, phase, strength = fit_linear_phasor(phasors, frames, weights, center)
            pilot_phase = float(wrap(obs.wrapped_phase_rad - carrier(center * rate)))
            observations.append(
                dict(
                    time_s=center,
                    support_start_s=start / rate,
                    support_stop_s=stop / rate,
                    pilot_phase_rad=pilot_phase,
                    broadband_phase_rad=float(phase),
                    difference_rad=float(wrap(pilot_phase - phase)),
                    pilot_resultant=obs.resultant_length,
                    pilot_standard_error_deg=obs.phase_standard_error_deg,
                    broadband_resultant=float(strength),
                    pilot_residual_frequency_hz=obs.relative_frequency_hz - basef,
                    broadband_residual_frequency_hz=float(frequency),
                    frame_count=len(frames),
                )
            )
        except ValueError as exc:
            failures.append(str(exc))
    train = [o for o in observations if o["support_stop_s"] <= split / rate]
    test = [o for o in observations if o["support_start_s"] >= split / rate]
    offset, rms = None, None
    if train and test:
        offset = float(
            np.angle(np.mean(np.exp(1j * np.array([o["difference_rad"] for o in train]))))
        )
        for o in observations:
            o["difference_deg"] = float(np.degrees(wrap(o["difference_rad"] - offset)))
        rms = float(np.sqrt(np.mean([o["difference_deg"] ** 2 for o in test])))
    return dict(
        supported=bool(supported),
        reference_sample=model.reference_sample,
        frequency_reference_hz=model.frequency_reference_hz,
        relative_cfo_hz=model.relative_cfo_hz,
        relative_cfo_rate_hz_s=model.relative_cfo_rate_hz_s,
        fractional_delay_samples=model.fractional_delay_samples,
        scalar_time_s=times,
        scalar_phase_rad=phases,
        scalar_coherence=coherences,
        tracked_coherence=held["tracked"]["coherence"],
        wrong_time_coherence=held["wrong_time"]["coherence"],
        band_phase_rms_deg=float(np.degrees(np.sqrt(np.mean(error**2)))),
        band_phase_resultant=resultant,
        retained_bandwidth_hz=len(ids) * rate / n,
        pilot_rows=observations,
        pilot_failures=failures,
        training_offset_rad=offset,
        pilot_held_rms_deg=rms,
        pilot_held_count=len(test),
    )
