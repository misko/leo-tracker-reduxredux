"""Frequency-held-out residual phase tracking using a frozen broadband channel."""

from __future__ import annotations

import math

import numpy as np

from leo.analysis.starlink.broadband_alignment import BroadbandAlignmentModel


def frequency_held_out_tracking(
    iq, sample_rate_hz, model: BroadbandAlignmentModel, *, block_samples=4096, training_fraction=0.5
):
    """Track common phase from A bands; evaluate only disjoint B bands.

    H and mask must have been fit on the first temporal partition. No B-band
    observation from the held partition enters its phase correction. A four-bin
    guard on each side of every 64-bin group reduces Hann-window leakage;
    colored noise and window sidelobes mean this is not exact independence.
    """
    values = np.asarray(iq)
    frequencies = np.fft.fftshift(np.fft.fftfreq(block_samples, 1 / sample_rate_hz))
    indexes = np.searchsorted(frequencies, np.asarray(model.frequency_hz))
    if np.any(indexes >= block_samples) or not np.allclose(
        frequencies[indexes], model.frequency_hz, atol=1e-6
    ):
        raise ValueError("model bins must match tracking FFT grid")
    train_bins = (indexes // 64) % 2 == 0
    guard = (indexes % 64 >= 4) & (indexes % 64 < 60)
    train_bins &= guard
    test_bins = ((indexes // 64) % 2 == 1) & guard
    if min(np.sum(train_bins), np.sum(test_bins)) < 8:
        raise ValueError("insufficient disjoint frequency support")
    start_sample = int(len(values) * training_fraction)
    transfer = np.asarray(model.channel_transfer)
    window = np.hanning(block_samples)
    rows, predictions, observations, baselines, controls = [], [], [], [], []
    # Fixed cap prevents a small number of high-gain bins dominating the tracker.
    cap = np.percentile(abs(transfer), 90)
    weights = np.minimum(1.0, cap / np.maximum(abs(transfer), 1e-30))
    for start in range(start_sample, len(values) - block_samples + 1, block_samples):
        time = (np.arange(start, start + block_samples) - model.reference_sample) / sample_rate_hz
        rotation = np.exp(
            -2j
            * np.pi
            * (model.relative_cfo_hz * time + model.relative_cfo_rate_hz_s * time**2 / 2)
        )
        left = np.fft.fftshift(np.fft.fft(values[start : start + block_samples, 0] * window))[
            indexes
        ]
        right_time = values[start : start + block_samples, 1] * rotation
        right = np.fft.fftshift(np.fft.fft(right_time * window))[indexes]
        predicted = transfer * left
        phase = float(
            np.angle(
                np.sum(weights[train_bins] * np.conj(predicted[train_bins]) * right[train_bins])
            )
        )
        p = predicted[test_bins] * np.exp(1j * phase)
        y = right[test_bins]
        wrong_start = start_sample + (
            start - start_sample + (len(values) - start_sample) // 3 + 17
        ) % (len(values) - start_sample - block_samples + 1)
        wrong_t = (
            np.arange(wrong_start, wrong_start + block_samples) - model.reference_sample
        ) / sample_rate_hz
        wrong_rotation = np.exp(
            -2j
            * np.pi
            * (model.relative_cfo_hz * wrong_t + model.relative_cfo_rate_hz_s * wrong_t**2 / 2)
        )
        wrong = np.fft.fftshift(
            np.fft.fft(
                values[wrong_start : wrong_start + block_samples, 1] * wrong_rotation * window
            )
        )[indexes][test_bins]
        cross = np.vdot(p, y)
        denominator = math.sqrt(max(float(np.vdot(p, p).real * np.vdot(y, y).real), 1e-30))
        rows.append(
            {
                "center_sample": start + (block_samples - 1) / 2,
                "training_band_phase_rad": phase,
                "held_band_residual_phase_rad": float(np.angle(cross)),
                "held_band_coherence": float(abs(cross) / denominator),
                "held_cross_real": float(cross.real),
                "held_cross_imag": float(cross.imag),
            }
        )
        predictions.append(p)
        observations.append(y)
        baselines.append(predicted[test_bins])
        controls.append(wrong)
    if not rows:
        raise ValueError("no complete held-out time blocks")

    def metric(p, y):
        p, y = np.concatenate(p), np.concatenate(y)
        cross = np.vdot(p, y)
        denominator = math.sqrt(max(float(np.vdot(p, p).real * np.vdot(y, y).real), 1e-30))
        return {
            "coherence": float(abs(cross) / denominator),
            "phase_rad": float(np.angle(cross)),
            "real_coherence": float(cross.real / denominator),
            "normalized_complex_error": float(np.linalg.norm(y - p) / np.linalg.norm(y)),
        }

    cross_blocks = np.asarray(
        [complex(row["held_cross_real"], row["held_cross_imag"]) for row in rows]
    )
    # Adjacent-pair resampling preserves dependence at one block lag. It does
    # not include uncertainty in the previously fitted frequency mask or H.
    pairs = np.arange(2 * (len(rows) // 2)).reshape(-1, 2)
    errors = []
    rng = np.random.default_rng(3107)
    if len(pairs) >= 2:
        reference_phase = np.angle(np.sum(cross_blocks[pairs.ravel()]))
        for _ in range(256):
            sampled = pairs[rng.integers(0, len(pairs), len(pairs))].ravel()
            errors.append(
                float(
                    np.angle(
                        np.exp(1j * (np.angle(np.sum(cross_blocks[sampled])) - reference_phase))
                    )
                )
            )
    return {
        "kind": "online_phase_from_A_bands_evaluated_on_disjoint_B_bands",
        "channel_and_mask_fit_on_first_half_only": True,
        "training_band_count": int(np.sum(train_bins)),
        "held_band_count": int(np.sum(test_bins)),
        "training_bandwidth_hz": float(np.sum(train_bins) * sample_rate_hz / block_samples),
        "held_bandwidth_hz": float(np.sum(test_bins) * sample_rate_hz / block_samples),
        "forecast": metric(baselines, observations),
        "tracked": metric(predictions, observations),
        "wrong_time": metric(predictions, controls),
        "wrong_time_control": "different contiguous RX1 interval from held temporal half",
        "conditional_adjacent_pair_phase_error_95_rad": (
            list(map(float, np.quantile(errors, [0.025, 0.975]))) if errors else None
        ),
        "uncertainty_scope": (
            "held-B-band block resampling conditional on frozen H/mask and A-band tracker; "
            "not electrical calibration or total geometric-phase uncertainty"
        ),
        "rows": rows,
        "geometric_phase_claimed": False,
    }
