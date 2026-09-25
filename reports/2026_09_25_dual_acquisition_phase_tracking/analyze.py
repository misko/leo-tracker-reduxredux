from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402

RATE = 2_500_000
DWELL_SAMPLES = 300_000
FFT_SAMPLES = 8192
STRIDE = 4096
OVERSAMPLE = 16
WEAK_BIN_DB = -15.0
WRONG_PAIR_SHIFT_SAMPLES = 8_192
ROOT = Path("/srv/bulk/leo/scanner-adaptive-recordings")
REPORT_DIR = Path(__file__).resolve().parent


def wrap_rad(value: np.ndarray) -> np.ndarray:
    return (np.asarray(value) + np.pi) % (2.0 * np.pi) - np.pi


def circular_r(phase: np.ndarray, weight: np.ndarray | None = None) -> float:
    phase = np.asarray(phase)
    if weight is None:
        weight = np.ones_like(phase, dtype=float)
    keep = np.isfinite(phase) & np.isfinite(weight) & (weight > 0)
    if not np.any(keep):
        return float("nan")
    vector = np.sum(weight[keep] * np.exp(1j * phase[keep]))
    return float(abs(vector) / np.sum(weight[keep]))


def correction_cycles(
    time_s: np.ndarray | float, center_frequency_hz: float, rate_hz_s: float
) -> np.ndarray:
    time_s = np.asarray(time_s)
    centered = time_s - 0.060
    return center_frequency_hz * time_s + 0.5 * rate_hz_s * (centered**2 - 0.060**2)


def centered_starts() -> np.ndarray:
    starts = np.arange(0, DWELL_SAMPLES - 4096 + 1, STRIDE) - 2048
    return starts[(starts >= 0) & (starts + FFT_SAMPLES <= DWELL_SAMPLES)]


def load_visit(session_id: str, visit_index: int) -> tuple[np.ndarray, dict]:
    session_root = ROOT / session_id
    manifest = json.loads((session_root / "manifest.json").read_text())["manifest"]
    chunk = next(
        item
        for item in manifest["chunks"]
        if item["first_visit_index"]
        <= visit_index
        < item["first_visit_index"] + item["visit_count"]
    )
    raw = zstd.ZstdDecompressor().decompress(
        (session_root / chunk["relative_path"]).read_bytes(),
        max_output_size=chunk["uncompressed_bytes"],
    )
    packed = np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)
    start = (visit_index - chunk["first_visit_index"]) * DWELL_SAMPLES
    compact = packed[start : start + DWELL_SAMPLES]
    iq = np.empty((DWELL_SAMPLES, 2), dtype=np.complex64)
    iq.real = compact[:, :, 0]
    iq.imag = compact[:, :, 1]
    return iq, manifest


def window_phasors(
    iq: np.ndarray,
    center_frequency_hz: float,
    rate_hz_s: float,
    starts: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if starts is None:
        starts = centered_starts()
    centers_s = (starts + (FFT_SAMPLES - 1) / 2) / RATE
    hann = np.hanning(FFT_SAMPLES)
    phasors = []
    coherence = []
    for start in starts:
        time_s = np.arange(start, start + FFT_SAMPLES) / RATE
        left = iq[start : start + FFT_SAMPLES, 0].astype(np.complex128)
        right = iq[start : start + FFT_SAMPLES, 1].astype(np.complex128)
        right *= np.exp(-2j * np.pi * correction_cycles(time_s, center_frequency_hz, rate_hz_s))
        phasor = np.sum(np.conj(left) * right * hann**2)
        denominator = math.sqrt(
            max(
                float(np.sum(abs(left * hann) ** 2) * np.sum(abs(right * hann) ** 2)),
                1e-30,
            )
        )
        phasors.append(phasor)
        coherence.append(abs(phasor) / denominator)
    return np.asarray(phasors), np.asarray(coherence), centers_s


def maximize_constant_frequency(iq: np.ndarray, seed_hz: float) -> tuple[float, float, float]:
    phasors, _, centers_s = window_phasors(iq, seed_hz, 0.0)
    denominator = np.sum(abs(phasors))
    coarse = np.linspace(-500.0, 500.0, 10_001)
    score = (
        abs(
            np.sum(
                phasors[None, :] * np.exp(-2j * np.pi * coarse[:, None] * centers_s[None, :]),
                axis=1,
            )
        )
        / denominator
    )
    coarse_best = float(coarse[int(np.argmax(score))])
    fine = np.linspace(coarse_best - 0.1, coarse_best + 0.1, 81)
    fine_score = (
        abs(
            np.sum(
                phasors[None, :] * np.exp(-2j * np.pi * fine[:, None] * centers_s[None, :]),
                axis=1,
            )
        )
        / denominator
    )
    selected = int(np.argmax(fine_score))
    return (
        seed_hz + float(fine[selected]),
        circular_r(np.angle(phasors)),
        float(fine_score[selected]),
    )


def maximize_frequency_and_rate(
    iq: np.ndarray, constant_frequency_hz: float
) -> tuple[float, float, float]:
    phasors, _, centers_s = window_phasors(iq, constant_frequency_hz, 0.0)
    x = centers_s - 0.060
    denominator = np.sum(abs(phasors))
    rate_grid = np.arange(-3000.0, 3000.1, 25.0)
    frequency_grid = np.arange(-100.0, 100.1, 1.0)
    best = (-1.0, 0.0, 0.0)
    frequency_rotation = np.exp(-2j * np.pi * frequency_grid[:, None] * centers_s[None, :])
    for rate in rate_grid:
        rate_phasors = phasors * np.exp(-1j * np.pi * rate * (x**2 - 0.060**2))
        score = abs(np.sum(frequency_rotation * rate_phasors[None, :], axis=1))
        index = int(np.argmax(score))
        candidate = (float(score[index] / denominator), float(frequency_grid[index]), float(rate))
        if candidate[0] > best[0]:
            best = candidate

    _, coarse_frequency, coarse_rate = best
    fine_rate = np.arange(coarse_rate - 30.0, coarse_rate + 30.01, 1.0)
    fine_frequency = np.arange(coarse_frequency - 2.0, coarse_frequency + 2.0001, 0.025)
    fine_frequency_rotation = np.exp(-2j * np.pi * fine_frequency[:, None] * centers_s[None, :])
    best = (-1.0, 0.0, 0.0)
    for rate in fine_rate:
        rate_phasors = phasors * np.exp(-1j * np.pi * rate * (x**2 - 0.060**2))
        score = abs(np.sum(fine_frequency_rotation * rate_phasors[None, :], axis=1))
        index = int(np.argmax(score))
        candidate = (
            float(score[index] / denominator),
            float(fine_frequency[index]),
            float(rate),
        )
        if candidate[0] > best[0]:
            best = candidate
    return constant_frequency_hz + best[1], best[2], best[0]


def random_nonoverlap_holdout(
    iq: np.ndarray, seed_hz: float, seed_rate_hz_s: float, authority: str
) -> dict:
    digest = hashlib.sha256(authority.encode()).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "big"))
    offsets = 256 + np.arange(6) * FFT_SAMPLES
    starts = []
    train = []
    held = []
    for group in range(6):
        group_indices = []
        for offset in offsets:
            group_indices.append(len(starts))
            starts.append(group * 50_000 + int(offset))
        assignment = rng.permutation(group_indices)
        train.extend(assignment[:3])
        held.extend(assignment[3:])
    starts = np.asarray(starts)
    train = np.sort(np.asarray(train))
    held = np.sort(np.asarray(held))
    seed_phasors, _, centers_s = window_phasors(iq, seed_hz, seed_rate_hz_s, starts=starts)

    denominator = np.sum(abs(seed_phasors[train]))
    coarse = np.linspace(-100.0, 100.0, 4_001)
    score = (
        abs(
            np.sum(
                seed_phasors[train][None, :]
                * np.exp(-2j * np.pi * coarse[:, None] * centers_s[train][None, :]),
                axis=1,
            )
        )
        / denominator
    )
    coarse_best = float(coarse[int(np.argmax(score))])
    fine = np.linspace(coarse_best - 0.1, coarse_best + 0.1, 81)
    fine_score = (
        abs(
            np.sum(
                seed_phasors[train][None, :]
                * np.exp(-2j * np.pi * fine[:, None] * centers_s[train][None, :]),
                axis=1,
            )
        )
        / denominator
    )
    constant_hz = seed_hz + float(fine[int(np.argmax(fine_score))])

    constant_phasors, _, _ = window_phasors(iq, constant_hz, seed_rate_hz_s, starts=starts)
    x = centers_s - 0.060
    rate_grid = np.arange(-2000.0, 2000.1, 25.0)
    frequency_grid = np.arange(-30.0, 30.1, 0.5)
    frequency_rotation = np.exp(-2j * np.pi * frequency_grid[:, None] * centers_s[train][None, :])
    best = (-1.0, 0.0, 0.0)
    train_denominator = np.sum(abs(constant_phasors[train]))
    for rate in rate_grid:
        rate_phasors = constant_phasors[train] * np.exp(
            -1j * np.pi * rate * (x[train] ** 2 - 0.060**2)
        )
        rate_score = abs(np.sum(frequency_rotation * rate_phasors[None, :], axis=1))
        index = int(np.argmax(rate_score))
        candidate = (
            float(rate_score[index] / train_denominator),
            float(frequency_grid[index]),
            float(rate),
        )
        if candidate[0] > best[0]:
            best = candidate
    held_frequency_hz = constant_hz + best[1]
    held_rate_hz_s = seed_rate_hz_s + best[2]
    final_phasors, _, _ = window_phasors(iq, held_frequency_hz, held_rate_hz_s, starts=starts)
    return {
        "frequency_hz": held_frequency_hz,
        "rate_hz_s": held_rate_hz_s,
        "training_window_indices": train.tolist(),
        "held_window_indices": held.tolist(),
        "window_starts": starts.tolist(),
        "training_r": circular_r(np.angle(final_phasors[train])),
        "held_r": circular_r(np.angle(final_phasors[held])),
    }


def periodic_interpolate(values: np.ndarray, index: np.ndarray) -> np.ndarray:
    lower = np.floor(index).astype(np.int64)
    fraction = index - lower
    return (
        values[lower % len(values)] * (1.0 - fraction)
        + values[(lower + 1) % len(values)] * fraction
    )


def temporal_bin_concentration(cross: np.ndarray, step: int) -> np.ndarray:
    increment = np.angle(cross[:, step:] * np.conj(cross[:, :-step]))
    weight = np.sqrt(abs(cross[:, step:]) * abs(cross[:, :-step]))
    output = np.full(increment.shape[1], np.nan)
    for column in range(increment.shape[1]):
        keep = (
            np.isfinite(increment[:, column])
            & np.isfinite(weight[:, column])
            & (weight[:, column] > 0)
        )
        if np.any(keep):
            output[column] = circular_r(increment[keep, column], weight[keep, column])
    return output


def fft_analysis(iq: np.ndarray, center_frequency_hz: float, rate_hz_s: float) -> dict:
    starts = centered_starts()
    centers_s = (starts + (FFT_SAMPLES - 1) / 2) / RATE
    hann = np.hanning(FFT_SAMPLES)
    nfft = FFT_SAMPLES * OVERSAMPLE
    base_index = np.arange(FFT_SAMPLES) * OVERSAMPLE
    masked_cross = np.empty((FFT_SAMPLES, len(starts)), dtype=np.complex128)
    aggregate_masked = []
    aggregate_unmasked = []
    phat = []
    retained = []
    for column, (start, center_s) in enumerate(zip(starts, centers_s, strict=True)):
        left = iq[start : start + FFT_SAMPLES, 0].astype(np.complex128)
        right = iq[start : start + FFT_SAMPLES, 1].astype(np.complex128)
        left_fft = np.fft.fft(left * hann, nfft)
        right_fft = np.fft.fft(right * hann, nfft)
        left_bins = left_fft[base_index]
        local_frequency = center_frequency_hz + rate_hz_s * (center_s - 0.060)
        right_bins = periodic_interpolate(right_fft, base_index + local_frequency * nfft / RATE)
        phase_at_start = (
            2.0 * np.pi * float(correction_cycles(start / RATE, center_frequency_hz, rate_hz_s))
        )
        cross_bins = np.conj(left_bins) * right_bins * np.exp(-1j * phase_at_start)
        left_relative = abs(left_bins) / max(float(np.max(abs(left_bins))), 1e-30)
        right_relative = abs(right_bins) / max(float(np.max(abs(right_bins))), 1e-30)
        strong = (left_relative >= 10.0 ** (WEAK_BIN_DB / 20.0)) & (
            right_relative >= 10.0 ** (WEAK_BIN_DB / 20.0)
        )
        masked_cross[:, column] = np.where(strong, cross_bins, np.nan + 1j * np.nan)
        aggregate_unmasked.append(np.sum(cross_bins))
        aggregate_masked.append(np.sum(cross_bins[strong]))
        unit = cross_bins[strong] / np.maximum(abs(cross_bins[strong]), 1e-30)
        phat.append(np.sum(unit))
        retained.append(np.mean(strong))
    overlap = temporal_bin_concentration(masked_cross, 1)
    nonoverlap = temporal_bin_concentration(masked_cross, 2)
    return {
        "masked_cross": masked_cross,
        "aggregate_masked": np.asarray(aggregate_masked),
        "aggregate_unmasked": np.asarray(aggregate_unmasked),
        "phat": np.asarray(phat),
        "retained": np.asarray(retained),
        "overlap_concentration": overlap,
        "nonoverlap_concentration": nonoverlap,
    }


def wrong_pair_coherence(iq: np.ndarray, center_frequency_hz: float, rate_hz_s: float) -> float:
    hann = np.hanning(FFT_SAMPLES)
    values = []
    for start in centered_starts():
        right_start = start + WRONG_PAIR_SHIFT_SAMPLES
        if right_start + FFT_SAMPLES > len(iq):
            continue
        left = iq[start : start + FFT_SAMPLES, 0].astype(np.complex128)
        right = iq[right_start : right_start + FFT_SAMPLES, 1].astype(np.complex128)
        right_time = np.arange(right_start, right_start + FFT_SAMPLES) / RATE
        right *= np.exp(-2j * np.pi * correction_cycles(right_time, center_frequency_hz, rate_hz_s))
        cross = np.sum(np.conj(left) * right * hann**2)
        denominator = math.sqrt(
            max(
                float(np.sum(abs(left * hann) ** 2) * np.sum(abs(right * hann) ** 2)),
                1e-30,
            )
        )
        values.append(abs(cross) / denominator)
    return float(np.median(values))


def lag_coherence_curve(
    iq: np.ndarray, center_frequency_hz: float, rate_hz_s: float
) -> tuple[np.ndarray, np.ndarray]:
    sample_time_s = np.arange(len(iq)) / RATE
    left = iq[:, 0].astype(np.complex128)
    right = iq[:, 1].astype(np.complex128) * np.exp(
        -2j * np.pi * correction_cycles(sample_time_s, center_frequency_hz, rate_hz_s)
    )
    lag = np.unique(
        np.concatenate(
            (
                np.arange(0, 150_001, STRIDE),
                np.asarray([50_000, 100_000, 150_000]),
            )
        )
    )
    hann = np.hanning(FFT_SAMPLES)
    values = []
    for offset in lag:
        coherence = []
        for start in centered_starts():
            right_start = start + int(offset)
            if right_start + FFT_SAMPLES > len(iq):
                continue
            left_window = left[start : start + FFT_SAMPLES]
            right_window = right[right_start : right_start + FFT_SAMPLES]
            cross = np.sum(np.conj(left_window) * right_window * hann**2)
            denominator = math.sqrt(
                max(
                    float(
                        np.sum(abs(left_window * hann) ** 2) * np.sum(abs(right_window * hann) ** 2)
                    ),
                    1e-30,
                )
            )
            coherence.append(abs(cross) / denominator)
        values.append(float(np.median(coherence)))
    return lag / RATE * 1000.0, np.asarray(values)


def analyze_dwell(item: dict) -> tuple[dict, dict]:
    iq, manifest = load_visit(item["session_id"], item["visit_index"])
    iq_sha256 = hashlib.sha256(iq.tobytes()).hexdigest()
    if iq_sha256 != item["iq_sha256"]:
        raise RuntimeError(f"IQ digest mismatch for {item['track']}: {iq_sha256}")
    raw, raw_coherence, centers_s = window_phasors(iq, 0.0, 0.0)
    constant_hz, seed_r, constant_weighted_r = maximize_constant_frequency(
        iq, item["seed_relative_cfo_hz"]
    )
    constant, constant_coherence, _ = window_phasors(iq, constant_hz, 0.0)
    linear_hz, linear_rate, linear_weighted_r = maximize_frequency_and_rate(iq, constant_hz)
    linear, linear_coherence, _ = window_phasors(iq, linear_hz, linear_rate)
    held = random_nonoverlap_holdout(
        iq,
        item["seed_relative_cfo_hz"],
        item["seed_relative_cfo_rate_hz_s"],
        f"{item['session_id']}:{item['visit_index']}:random-nonoverlap-v1",
    )
    fft = fft_analysis(iq, linear_hz, linear_rate)
    fft_phase = np.angle(fft["aggregate_masked"])
    fft_unmasked_phase = np.angle(fft["aggregate_unmasked"])
    phat_phase = np.angle(fft["phat"])
    direct_phase = np.angle(linear)
    fft_time_error = np.degrees(wrap_rad(fft_unmasked_phase - direct_phase))
    direct_increment = np.angle(linear[1:] * np.conj(linear[:-1]))
    fft_increment = np.angle(fft["aggregate_masked"][1:] * np.conj(fft["aggregate_masked"][:-1]))
    increment_error = np.degrees(wrap_rad(fft_increment - direct_increment))
    row = {
        **item,
        "raw_uncompressed_sha256": manifest["uncompressed_sha256"],
        "window_count": len(centers_s),
        "seed_only_phase_r": seed_r,
        "constant_frequency_hz": constant_hz,
        "constant_frequency_residual_hz": constant_hz - item["seed_relative_cfo_hz"],
        "constant_phase_r": circular_r(np.angle(constant)),
        "constant_weighted_r": constant_weighted_r,
        "linear_center_frequency_hz": linear_hz,
        "linear_frequency_rate_hz_s": linear_rate,
        "linear_phase_r": circular_r(direct_phase),
        "linear_weighted_r": linear_weighted_r,
        "random_nonoverlap_fit_frequency_hz": held["frequency_hz"],
        "random_nonoverlap_fit_rate_hz_s": held["rate_hz_s"],
        "random_nonoverlap_training_r": held["training_r"],
        "random_nonoverlap_held_r": held["held_r"],
        "random_nonoverlap_training_window_indices": held["training_window_indices"],
        "random_nonoverlap_held_window_indices": held["held_window_indices"],
        "median_direct_coherence": float(np.median(linear_coherence)),
        "wrong_pair_shift_ms": WRONG_PAIR_SHIFT_SAMPLES / RATE * 1000.0,
        "median_wrong_pair_coherence": wrong_pair_coherence(iq, linear_hz, linear_rate),
        "fft_masked_phase_r": circular_r(fft_phase),
        "fft_phat_phase_r": circular_r(phat_phase),
        "median_retained_bin_fraction": float(np.median(fft["retained"])),
        "fft_vs_time_unmasked_phase_rms_deg": float(np.sqrt(np.mean(fft_time_error**2))),
        "fft_vs_direct_increment_rms_deg": float(np.sqrt(np.mean(increment_error**2))),
        "median_adjacent_bin_increment_r": float(np.nanmedian(fft["overlap_concentration"])),
        "median_nonoverlap_bin_increment_r": float(np.nanmedian(fft["nonoverlap_concentration"])),
        "raw_phase_r": circular_r(np.angle(raw)),
        "median_raw_coherence": float(np.median(raw_coherence)),
        "median_constant_coherence": float(np.median(constant_coherence)),
    }
    lag_ms, lag_coherence = lag_coherence_curve(iq, linear_hz, linear_rate)
    traces = {
        "time_ms": centers_s * 1000.0,
        "raw_phase_deg": np.degrees(np.angle(raw)),
        "constant_phase_deg": np.degrees(np.angle(constant)),
        "direct_phase_deg": np.degrees(direct_phase),
        "fft_phase_deg": np.degrees(fft_phase),
        "phat_phase_deg": np.degrees(phat_phase),
        "increment_cross": fft["masked_cross"][:, 1:] * np.conj(fft["masked_cross"][:, :-1]),
        "lag_ms": lag_ms,
        "lag_coherence": lag_coherence,
    }
    return row, traces


def plot_phase_traces(rows: list[dict], traces: list[dict]) -> None:
    figure, axes = plt.subplots(5, 1, figsize=(13.5, 14.0), sharex=True, sharey=True)
    for axis, row, trace in zip(axes, rows, traces, strict=True):
        axis.plot(
            trace["time_ms"],
            trace["raw_phase_deg"],
            color="0.72",
            linewidth=0.9,
            label="raw" if row["track"] == "T1" else None,
        )
        axis.plot(
            trace["time_ms"],
            trace["direct_phase_deg"],
            ".-",
            linewidth=1.2,
            markersize=3,
            label="direct IQ" if row["track"] == "T1" else None,
        )
        axis.plot(
            trace["time_ms"],
            trace["fft_phase_deg"],
            ".-",
            linewidth=1.0,
            markersize=2.5,
            label="masked FFT" if row["track"] == "T1" else None,
        )
        axis.set_ylabel(f"{row['track']}\nphase (deg)")
        axis.set_ylim(-185, 185)
        axis.grid(alpha=0.22)
        axis.text(
            0.995,
            0.88,
            f"visit {row['visit_index']} · R={row['linear_phase_r']:.3f}",
            transform=axis.transAxes,
            ha="right",
            va="top",
        )
    axes[0].legend(loc="lower left", ncol=3)
    axes[-1].set_xlabel("Dwell time (ms)")
    figure.suptitle("RX1−RX0 phase after zero-delay, identity-channel frequency correction")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "phase-traces.png", dpi=180, facecolor="white")
    plt.close(figure)


def plot_method_comparison(rows: list[dict]) -> None:
    labels = [row["track"] for row in rows]
    x = np.arange(len(rows))
    width = 0.16
    methods = [
        ("Raw direct IQ", "raw_phase_r"),
        ("Constant-CFO direct IQ", "constant_phase_r"),
        ("Linear-CFO direct IQ", "linear_phase_r"),
        ("Masked FFT", "fft_masked_phase_r"),
        ("Phase-only FFT", "fft_phat_phase_r"),
    ]
    figure, axes = plt.subplots(2, 1, figsize=(13.0, 9.0))
    for index, (label, key) in enumerate(methods):
        axes[0].bar(
            x + (index - 2) * width,
            [row[key] for row in rows],
            width,
            label=label,
        )
    axes[0].set_xticks(x, labels)
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("Within-dwell circular concentration R")
    axes[0].set_title("Phase tracking by estimator")
    axes[0].scatter(
        x,
        [row["random_nonoverlap_held_r"] for row in rows],
        color="black",
        marker="D",
        s=38,
        label="random non-overlap held R",
        zorder=4,
    )
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(loc="upper left", ncol=3)

    axes[1].bar(
        x - width / 2,
        [row["median_direct_coherence"] for row in rows],
        width,
        label="simultaneous RX0/RX1",
    )
    axes[1].bar(
        x + width / 2,
        [row["median_wrong_pair_coherence"] for row in rows],
        width,
        label=f"RX1 shifted by {WRONG_PAIR_SHIFT_SAMPLES / RATE * 1000:.3f} ms",
    )
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("Median normalized coherence")
    axes[1].set_title("Same-time signal versus wrong-time control")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(loc="upper left")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "method-comparison.png", dpi=180, facecolor="white")
    plt.close(figure)


def plot_lag_coherence(rows: list[dict], traces: list[dict]) -> None:
    figure, axes = plt.subplots(5, 1, figsize=(13.0, 12.0), sharex=True)
    for axis, row, trace in zip(axes, rows, traces, strict=True):
        axis.plot(trace["lag_ms"], trace["lag_coherence"], ".-", linewidth=1.0)
        axis.axvline(20.0, color="black", linewidth=0.8, linestyle="--", alpha=0.6)
        axis.axvline(40.0, color="black", linewidth=0.8, linestyle="--", alpha=0.6)
        axis.set_ylabel(f"{row['track']}\ncoherence")
        axis.grid(alpha=0.22)
    axes[-1].set_xlabel("RX1 lag relative to RX0 (ms)")
    figure.suptitle("Full-dwell cross-correlation after frequency correction")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "lag-coherence.png", dpi=180, facecolor="white")
    plt.close(figure)


def plot_increment_heatmaps(rows: list[dict], traces: list[dict]) -> None:
    frequency_mhz = np.fft.fftshift(np.fft.fftfreq(FFT_SAMPLES, 1.0 / RATE)) / 1e6
    starts = centered_starts()
    centers_ms = (starts + (FFT_SAMPLES - 1) / 2) / RATE * 1000.0
    increment_time = 0.5 * (centers_ms[1:] + centers_ms[:-1])
    half_step = STRIDE / RATE * 1000.0 / 2.0
    cmap = plt.get_cmap("twilight").copy()
    cmap.set_bad("0.88")
    figure, axes = plt.subplots(5, 1, figsize=(13.5, 14.0), sharex=True, sharey=True)
    for axis, row, trace in zip(axes, rows, traces, strict=True):
        phase = np.angle(np.fft.fftshift(trace["increment_cross"], axes=0))
        axis.imshow(
            phase,
            origin="lower",
            aspect="auto",
            interpolation="nearest",
            extent=[
                increment_time[0] - half_step,
                increment_time[-1] + half_step,
                frequency_mhz[0],
                frequency_mhz[-1],
            ],
            cmap=cmap,
            norm=Normalize(-np.pi, np.pi),
            rasterized=True,
        )
        axis.set_ylabel(f"{row['track']}\nMHz")
        axis.text(
            0.995,
            0.88,
            f"median bin R={row['median_adjacent_bin_increment_r']:.3f}",
            transform=axis.transAxes,
            ha="right",
            va="top",
            bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
        )
    axes[-1].set_xlabel("Dwell time (ms)")
    figure.suptitle("Adjacent-window per-bin phase increments after frequency alignment")
    figure.subplots_adjust(left=0.08, right=0.91, top=0.95, bottom=0.06, hspace=0.18)
    colorbar = figure.colorbar(
        plt.cm.ScalarMappable(norm=Normalize(-np.pi, np.pi), cmap=cmap),
        ax=axes,
        fraction=0.018,
        pad=0.015,
    )
    colorbar.set_label("Wrapped phase increment (rad)")
    colorbar.set_ticks([-np.pi, -np.pi / 2, 0, np.pi / 2, np.pi])
    colorbar.set_ticklabels(["−π", "−π/2", "0", "+π/2", "+π"])
    figure.savefig(REPORT_DIR / "fft-bin-increment-heatmaps.png", dpi=180, facecolor="white")
    plt.close(figure)


def write_csv(rows: list[dict]) -> None:
    keys = [
        "track",
        "session_id",
        "visit_index",
        "channel",
        "edge",
        "rx0_track_observations",
        "rx1_track_observations",
        "phase_blind_priority",
        "seed_relative_cfo_hz",
        "constant_frequency_hz",
        "linear_center_frequency_hz",
        "linear_frequency_rate_hz_s",
        "raw_phase_r",
        "constant_phase_r",
        "linear_phase_r",
        "random_nonoverlap_training_r",
        "random_nonoverlap_held_r",
        "fft_masked_phase_r",
        "fft_phat_phase_r",
        "median_direct_coherence",
        "median_wrong_pair_coherence",
        "fft_vs_time_unmasked_phase_rms_deg",
        "fft_vs_direct_increment_rms_deg",
        "median_adjacent_bin_increment_r",
        "median_nonoverlap_bin_increment_r",
        "existing_held_r",
    ]
    with (REPORT_DIR / "per-dwell.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in keys})


def main() -> None:
    selection = json.loads((REPORT_DIR / "selection.json").read_text())
    rows = []
    traces = []
    for item in selection["dwells"]:
        row, trace = analyze_dwell(item)
        rows.append(row)
        traces.append(trace)
        print(
            f"{row['track']} visit {row['visit_index']}: "
            f"direct R={row['linear_phase_r']:.3f}, "
            f"FFT R={row['fft_masked_phase_r']:.3f}, "
            f"same/wrong coherence={row['median_direct_coherence']:.3f}/"
            f"{row['median_wrong_pair_coherence']:.3f}",
            flush=True,
        )
    plot_phase_traces(rows, traces)
    plot_method_comparison(rows)
    plot_increment_heatmaps(rows, traces)
    plot_lag_coherence(rows, traces)
    write_csv(rows)
    payload = {
        "schema_version": 1,
        "selection_id": selection["selection_id"],
        "protocol": {
            "sample_rate_hz": RATE,
            "dwell_samples": DWELL_SAMPLES,
            "fft_samples": FFT_SAMPLES,
            "stride_samples": STRIDE,
            "fft_oversample": OVERSAMPLE,
            "weak_bin_threshold_db_per_receiver": WEAK_BIN_DB,
            "timing_delay_samples": 0.0,
            "channel_response": "identity",
            "phase_intercept_fitted": False,
            "frequency_fit_scope": "all centered windows in the dwell; no time holdout",
            "wrong_pair_shift_samples": WRONG_PAIR_SHIFT_SAMPLES,
        },
        "rows": rows,
        "summary": {
            "median_raw_phase_r": float(np.median([row["raw_phase_r"] for row in rows])),
            "median_constant_phase_r": float(np.median([row["constant_phase_r"] for row in rows])),
            "median_linear_phase_r": float(np.median([row["linear_phase_r"] for row in rows])),
            "median_random_nonoverlap_held_r": float(
                np.median([row["random_nonoverlap_held_r"] for row in rows])
            ),
            "median_fft_masked_phase_r": float(
                np.median([row["fft_masked_phase_r"] for row in rows])
            ),
            "median_fft_phat_phase_r": float(np.median([row["fft_phat_phase_r"] for row in rows])),
            "median_direct_coherence": float(
                np.median([row["median_direct_coherence"] for row in rows])
            ),
            "median_wrong_pair_coherence": float(
                np.median([row["median_wrong_pair_coherence"] for row in rows])
            ),
            "median_fft_vs_time_unmasked_phase_rms_deg": float(
                np.median([row["fft_vs_time_unmasked_phase_rms_deg"] for row in rows])
            ),
            "median_adjacent_bin_increment_r": float(
                np.median([row["median_adjacent_bin_increment_r"] for row in rows])
            ),
            "median_nonoverlap_bin_increment_r": float(
                np.median([row["median_nonoverlap_bin_increment_r"] for row in rows])
            ),
        },
    }
    (REPORT_DIR / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
