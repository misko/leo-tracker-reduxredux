from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path("/srv/bulk/leo")
REPORT_DIR = Path(__file__).resolve().parent
START_NS = int(datetime(2026, 9, 25, 6, 20, tzinfo=UTC).timestamp() * 1e9)
STOP_NS = int(datetime(2026, 9, 25, 14, 20, tzinfo=UTC).timestamp() * 1e9)
HIGH_RATE = 10_000_000
LOW_RATE = 2_500_000
DWELL_SECONDS = 0.120
WINDOW_SECONDS = 8192 / 2_500_000
STRIDE_SECONDS = 4096 / 2_500_000
WEAK_BIN_DB = -15.0


def circular_r(phase: np.ndarray, weight: np.ndarray | None = None) -> float:
    phase = np.asarray(phase)
    if weight is None:
        weight = np.ones_like(phase, dtype=float)
    keep = np.isfinite(phase) & np.isfinite(weight) & (weight > 0)
    vector = np.sum(weight[keep] * np.exp(1j * phase[keep]))
    return float(abs(vector) / np.sum(weight[keep])) if np.any(keep) else float("nan")


def wrap_rad(value: np.ndarray) -> np.ndarray:
    return (np.asarray(value) + np.pi) % (2 * np.pi) - np.pi


def finite_median(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None and np.isfinite(row[key])]
    return float(np.median(values)) if values else None


def phase_product_rows() -> tuple[list[dict], list[dict]]:
    sessions: list[dict] = []
    visits: list[dict] = []
    phase_root = ROOT / "scanner-adaptive-relative-phase-v1"
    for manifest_path in phase_root.glob("scan-fw-*/*/manifest.json"):
        phase = json.loads(manifest_path.read_text())["document"]
        session_id = phase["session_id"]
        source_path = ROOT / "scanner-adaptive-recordings" / session_id / "manifest.json"
        if not source_path.exists():
            continue
        source = json.loads(source_path.read_text())["manifest"]
        start_ns = source["timing"]["first_sample_estimate_utc_ns"]
        if not START_NS <= start_ns < STOP_NS:
            continue
        binding = phase["glrt_binding_sha256"].split(":")[-1]
        binding_path = ROOT / "scanner-adaptive-analysis" / session_id / binding / "binding.v8.json"
        glrt = json.loads(binding_path.read_text())["document"]
        sample_rate = glrt["configuration"]["sample_rate_hz"]
        session = {
            "session_id": session_id,
            "start_utc": datetime.fromtimestamp(start_ns / 1e9, UTC).isoformat(),
            "sample_rate_hz": sample_rate,
            "total_visits": phase["total_visit_count"],
            "selected_visits": len(phase["selected_visits"]),
            "supported_visits": phase["supported_visit_count"],
            "pilot_checked_visits": phase["pilot_checked_visit_count"],
            "state": phase["state"],
        }
        sessions.append(session)
        for visit_path in manifest_path.parent.glob("visit-*.json"):
            visit = json.loads(visit_path.read_text())["document"]
            evidence = visit.get("evidence") or {}
            row = {
                "session_id": session_id,
                "sample_rate_hz": sample_rate,
                "visit_index": visit["visit_index"],
                "supported": bool(evidence.get("supported", False)),
                "reason": visit["reason"],
                "band_phase_resultant": evidence.get("band_phase_resultant"),
                "band_phase_rms_deg": evidence.get("band_phase_rms_deg"),
                "retained_bandwidth_hz": evidence.get("retained_bandwidth_hz"),
                "pilot_held_count": evidence.get("pilot_held_count"),
                "pilot_held_rms_deg": evidence.get("pilot_held_rms_deg"),
            }
            for source_key, output_key in (
                ("scalar_coherence", "median_scalar_coherence"),
                ("tracked_coherence", "median_tracked_coherence"),
                ("wrong_time_coherence", "median_wrong_time_coherence"),
            ):
                values = evidence.get(source_key) or []
                row[output_key] = float(np.median(values)) if values else None
            visits.append(row)
    sessions.sort(key=lambda row: row["start_utc"])
    visits.sort(key=lambda row: (row["session_id"], row["visit_index"]))
    return sessions, visits


def summarize_rates(sessions: list[dict], visits: list[dict]) -> list[dict]:
    output = []
    for rate in sorted({row["sample_rate_hz"] for row in sessions}):
        rate_sessions = [row for row in sessions if row["sample_rate_hz"] == rate]
        rate_visits = [row for row in visits if row["sample_rate_hz"] == rate]
        supported = [row for row in rate_visits if row["supported"]]
        session_support_rates = [
            row["supported_visits"] / row["selected_visits"]
            for row in rate_sessions
            if row["selected_visits"]
        ]
        output.append(
            {
                "sample_rate_hz": rate,
                "session_count": len(rate_sessions),
                "sessions_with_paired_selection": sum(
                    row["selected_visits"] > 0 for row in rate_sessions
                ),
                "selected_visit_count": len(rate_visits),
                "supported_visit_count": len(supported),
                "pooled_supported_fraction": len(supported) / len(rate_visits),
                "median_session_supported_fraction": float(np.median(session_support_rates)),
                "median_band_phase_resultant": finite_median(supported, "band_phase_resultant"),
                "median_band_phase_rms_deg": finite_median(supported, "band_phase_rms_deg"),
                "median_retained_bandwidth_hz": finite_median(supported, "retained_bandwidth_hz"),
                "median_pilot_held_rms_deg": finite_median(supported, "pilot_held_rms_deg"),
                "median_scalar_coherence": finite_median(supported, "median_scalar_coherence"),
                "median_tracked_coherence": finite_median(supported, "median_tracked_coherence"),
                "median_wrong_time_coherence": finite_median(
                    supported, "median_wrong_time_coherence"
                ),
            }
        )
    return output


def window_geometry(rate: int) -> tuple[int, int, int, np.ndarray]:
    sample_count = round(rate * DWELL_SECONDS)
    window = round(rate * WINDOW_SECONDS)
    stride = round(rate * STRIDE_SECONDS)
    half_original_stride = stride // 2
    starts = np.arange(0, sample_count - stride + 1, stride) - half_original_stride
    starts = starts[(starts >= 0) & (starts + window <= sample_count)]
    return sample_count, window, stride, starts.astype(int)


def load_visit(session_id: str, visit_index: int, expected_rate: int) -> tuple[np.ndarray, dict]:
    session_root = ROOT / "scanner-adaptive-recordings" / session_id
    manifest = json.loads((session_root / "manifest.json").read_text())["manifest"]
    if manifest["timing"]["sample_rate_hz"] != expected_rate:
        raise RuntimeError(f"sample-rate mismatch for {session_id}")
    chunk = next(
        item
        for item in manifest["chunks"]
        if item["first_visit_index"]
        <= visit_index
        < item["first_visit_index"] + item["visit_count"]
    )
    compressed = (session_root / chunk["relative_path"]).read_bytes()
    compressed_sha = "sha256:" + hashlib.sha256(compressed).hexdigest()
    if compressed_sha != chunk["compressed_sha256"]:
        raise RuntimeError(f"compressed IQ digest mismatch for {session_id}/{visit_index}")
    raw = zstd.ZstdDecompressor().decompress(
        compressed, max_output_size=chunk["uncompressed_bytes"]
    )
    packed = np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)
    dwell_samples, _, _, _ = window_geometry(expected_rate)
    offset = (visit_index - chunk["first_visit_index"]) * dwell_samples
    packed = packed[offset : offset + dwell_samples]
    iq = np.empty((dwell_samples, 2), dtype=np.complex64)
    iq.real = packed[:, :, 0]
    iq.imag = packed[:, :, 1]
    return iq, {"chunk": chunk, "manifest_sha256": manifest["uncompressed_sha256"]}


def correction_cycles(time_s: np.ndarray, frequency_hz: float, rate_hz_s: float) -> np.ndarray:
    centered = time_s - DWELL_SECONDS / 2
    return frequency_hz * time_s + 0.5 * rate_hz_s * (centered**2 - (DWELL_SECONDS / 2) ** 2)


def time_phasors(
    iq: np.ndarray,
    sample_rate: int,
    frequency_hz: float,
    rate_hz_s: float,
    starts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    _, window, _, _ = window_geometry(sample_rate)
    taper = np.hanning(window)
    phasors = []
    coherence = []
    for start in starts:
        times = np.arange(start, start + window) / sample_rate
        left = iq[start : start + window, 0].astype(np.complex128)
        right = iq[start : start + window, 1].astype(np.complex128)
        right *= np.exp(-2j * np.pi * correction_cycles(times, frequency_hz, rate_hz_s))
        phasor = np.sum(np.conj(left) * right * taper**2)
        denominator = math.sqrt(
            max(float(np.sum(abs(left * taper) ** 2) * np.sum(abs(right * taper) ** 2)), 1e-30)
        )
        phasors.append(phasor)
        coherence.append(abs(phasor) / denominator)
    centers = (starts + (window - 1) / 2) / sample_rate
    return np.asarray(phasors), np.asarray(coherence), centers


def fit_frequency_rate(
    iq: np.ndarray,
    sample_rate: int,
    seed_hz: float,
    starts: np.ndarray,
    frequency_limit_hz: float,
    rate_limit_hz_s: float,
) -> tuple[float, float, float]:
    seed, _, centers = time_phasors(iq, sample_rate, seed_hz, 0.0, starts)
    denominator = np.sum(abs(seed))
    coarse_frequency = np.arange(-frequency_limit_hz, frequency_limit_hz + 0.1, 1.0)
    coarse_rotation = np.exp(-2j * np.pi * coarse_frequency[:, None] * centers[None, :])
    coarse_score = abs(coarse_rotation @ seed) / denominator
    constant = seed_hz + float(coarse_frequency[int(np.argmax(coarse_score))])
    constant_phasors, _, centers = time_phasors(iq, sample_rate, constant, 0.0, starts)
    x = centers - DWELL_SECONDS / 2
    frequency_grid = np.arange(-30.0, 30.001, 0.5)
    frequency_rotation = np.exp(-2j * np.pi * frequency_grid[:, None] * centers[None, :])
    best = (-1.0, 0.0, 0.0)
    for rate in np.arange(-rate_limit_hz_s, rate_limit_hz_s + 0.1, 25.0):
        rate_phasors = constant_phasors * np.exp(
            -1j * np.pi * rate * (x**2 - (DWELL_SECONDS / 2) ** 2)
        )
        score = abs(frequency_rotation @ rate_phasors)
        index = int(np.argmax(score))
        candidate = (float(score[index]), float(frequency_grid[index]), float(rate))
        if candidate[0] > best[0]:
            best = candidate
    frequency = constant + best[1]
    final, _, _ = time_phasors(iq, sample_rate, frequency, best[2], starts)
    return frequency, best[2], circular_r(np.angle(final), abs(final))


def random_holdout(iq: np.ndarray, sample_rate: int, seed_hz: float, authority: str) -> dict:
    _, window, _, _ = window_geometry(sample_rate)
    stratum = round(0.020 * sample_rate)
    offset = max(1, (stratum - 6 * window) // 2)
    starts = np.asarray(
        [group * stratum + offset + index * window for group in range(6) for index in range(6)]
    )
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(authority.encode()).digest()[:8]))
    train = []
    held = []
    for group in range(6):
        order = rng.permutation(np.arange(group * 6, group * 6 + 6))
        train.extend(order[:3])
        held.extend(order[3:])
    train = np.sort(train)
    held = np.sort(held)
    frequency, rate, _ = fit_frequency_rate(iq, sample_rate, seed_hz, starts[train], 100.0, 2000.0)
    phasors, _, _ = time_phasors(iq, sample_rate, frequency, rate, starts)
    return {
        "frequency_hz": frequency,
        "rate_hz_s": rate,
        "train_r": circular_r(np.angle(phasors[train])),
        "held_r": circular_r(np.angle(phasors[held])),
        "train_starts": starts[train].tolist(),
        "held_starts": starts[held].tolist(),
    }


def fft_observables(
    iq: np.ndarray,
    sample_rate: int,
    frequency_hz: float,
    rate_hz_s: float,
    starts: np.ndarray,
) -> dict:
    _, window, _, _ = window_geometry(sample_rate)
    taper = np.hanning(window)
    frequencies = np.fft.fftfreq(window, 1 / sample_rate)
    widths = (0.5e6, 1e6, 2e6, 4e6, 8e6)
    full = []
    common = []
    phat = []
    by_width = {width: [] for width in widths}
    retained = []
    for start in starts:
        times = np.arange(start, start + window) / sample_rate
        center_s = (start + (window - 1) / 2) / sample_rate
        local_frequency = frequency_hz + rate_hz_s * (center_s - DWELL_SECONDS / 2)
        left = iq[start : start + window, 0].astype(np.complex128)
        right = iq[start : start + window, 1].astype(np.complex128)
        right *= np.exp(-2j * np.pi * correction_cycles(times, frequency_hz, rate_hz_s))
        left_fft = np.fft.fft(left * taper)
        right_fft = np.fft.fft(right * taper)
        cross = np.conj(left_fft) * right_fft
        physical = abs(frequencies + local_frequency) <= sample_rate / 2
        left_relative = abs(left_fft) / max(float(np.max(abs(left_fft))), 1e-30)
        right_relative = abs(right_fft) / max(float(np.max(abs(right_fft))), 1e-30)
        strong = (left_relative >= 10 ** (WEAK_BIN_DB / 20)) & (
            right_relative >= 10 ** (WEAK_BIN_DB / 20)
        )
        keep = physical & strong
        full.append(np.sum(cross))
        common.append(np.sum(cross[keep]))
        phat.append(np.sum(cross[keep] / np.maximum(abs(cross[keep]), 1e-30)))
        retained.append(np.sum(keep) * sample_rate / window)
        for width in widths:
            band = keep & (abs(frequencies) <= width / 2)
            by_width[width].append(np.sum(cross[band]))
    return {
        "full": np.asarray(full),
        "common": np.asarray(common),
        "phat": np.asarray(phat),
        "retained_bandwidth_hz": np.asarray(retained),
        "by_width": {str(int(width)): np.asarray(values) for width, values in by_width.items()},
    }


def decimate_four(iq: np.ndarray) -> np.ndarray:
    """Apply one identical linear-phase anti-alias filter, then retain every fourth sample."""
    taps_count = 257
    cutoff_hz = 1_100_000.0
    centered = np.arange(taps_count) - (taps_count - 1) / 2
    normalized_cutoff = cutoff_hz / HIGH_RATE
    taps = 2 * normalized_cutoff * np.sinc(2 * normalized_cutoff * centered)
    taps *= np.kaiser(taps_count, 8.6)
    taps /= np.sum(taps)
    output = np.empty((len(iq) // 4, 2), dtype=np.complex64)
    for receiver in range(2):
        filtered = np.convolve(iq[:, receiver].astype(np.complex128), taps, mode="same")
        output[:, receiver] = filtered[::4]
    return output


def deployed_visit(session_id: str, visit_index: int) -> dict:
    phase_dir = next((ROOT / "scanner-adaptive-relative-phase-v1" / session_id).glob("*/"))
    return json.loads((phase_dir / f"visit-{visit_index:04d}.json").read_text())["document"]


def replay_selected(selection: dict) -> tuple[list[dict], list[dict]]:
    rows = []
    traces = []
    for item in selection["dwells"]:
        iq, provenance = load_visit(item["session_id"], item["visit_index"], HIGH_RATE)
        _, _, _, starts = window_geometry(HIGH_RATE)
        raw, raw_coherence, centers = time_phasors(iq, HIGH_RATE, 0.0, 0.0, starts)
        frequency, rate, _ = fit_frequency_rate(
            iq, HIGH_RATE, item["branch_resolved_cfo_seed_hz"], starts, 100.0, 3000.0
        )
        direct, coherence, _ = time_phasors(iq, HIGH_RATE, frequency, rate, starts)
        held = random_holdout(
            iq,
            HIGH_RATE,
            item["branch_resolved_cfo_seed_hz"],
            f"{item['session_id']}:{item['visit_index']}:matched-random-nonoverlap-v1",
        )
        fft = fft_observables(iq, HIGH_RATE, frequency, rate, starts)
        decimated = decimate_four(iq)
        _, _, _, decimated_starts = window_geometry(LOW_RATE)
        decimated_frequency, decimated_rate, _ = fit_frequency_rate(
            decimated,
            LOW_RATE,
            item["branch_resolved_cfo_seed_hz"],
            decimated_starts,
            100.0,
            3000.0,
        )
        decimated_direct, decimated_coherence, _ = time_phasors(
            decimated,
            LOW_RATE,
            decimated_frequency,
            decimated_rate,
            decimated_starts,
        )
        decimated_held = random_holdout(
            decimated,
            LOW_RATE,
            item["branch_resolved_cfo_seed_hz"],
            f"{item['session_id']}:{item['visit_index']}:matched-random-nonoverlap-v1",
        )
        deployed = deployed_visit(item["session_id"], item["visit_index"])["evidence"]
        fft_direct_error = np.degrees(wrap_rad(np.angle(fft["full"]) - np.angle(direct)))
        bandwidth_r = {key: circular_r(np.angle(value)) for key, value in fft["by_width"].items()}
        row = {
            **item,
            "chunk_compressed_sha256": provenance["chunk"]["compressed_sha256"],
            "source_uncompressed_sha256": provenance["manifest_sha256"],
            "window_count": len(starts),
            "raw_phase_r": circular_r(np.angle(raw)),
            "fitted_frequency_hz": frequency,
            "fitted_rate_hz_s": rate,
            "direct_phase_r": circular_r(np.angle(direct)),
            "random_training_r": held["train_r"],
            "random_held_r": held["held_r"],
            "median_direct_coherence": float(np.median(coherence)),
            "median_raw_coherence": float(np.median(raw_coherence)),
            "fft_full_phase_r": circular_r(np.angle(fft["full"])),
            "fft_common_masked_phase_r": circular_r(np.angle(fft["common"])),
            "fft_common_phat_phase_r": circular_r(np.angle(fft["phat"])),
            "fft_direct_rms_deg": float(np.sqrt(np.mean(fft_direct_error**2))),
            "median_fft_retained_bandwidth_hz": float(np.median(fft["retained_bandwidth_hz"])),
            "bandwidth_phase_r": bandwidth_r,
            "deployed_response_normalized_r": deployed["band_phase_resultant"],
            "deployed_retained_bandwidth_hz": deployed["retained_bandwidth_hz"],
            "deployed_pilot_held_rms_deg": deployed["pilot_held_rms_deg"],
            "decimated_2p5m_frequency_hz": decimated_frequency,
            "decimated_2p5m_rate_hz_s": decimated_rate,
            "decimated_2p5m_direct_phase_r": circular_r(np.angle(decimated_direct)),
            "decimated_2p5m_random_training_r": decimated_held["train_r"],
            "decimated_2p5m_random_held_r": decimated_held["held_r"],
            "decimated_2p5m_median_direct_coherence": float(np.median(decimated_coherence)),
        }
        rows.append(row)
        traces.append(
            {
                "label": item["label"],
                "time_ms": centers * 1000,
                "raw_phase_deg": np.degrees(np.angle(raw)),
                "direct_phase_deg": np.degrees(np.angle(direct)),
                "fft_common_phase_deg": np.degrees(np.angle(fft["common"])),
            }
        )
        print(
            f"{item['label']} {item['session_id']}/{item['visit_index']}: "
            f"direct R={row['direct_phase_r']:.3f}, held R={row['random_held_r']:.3f}, "
            f"common FFT R={row['fft_common_masked_phase_r']:.3f}",
            flush=True,
        )
    return rows, traces


def plot_rate_comparison(summary: list[dict]) -> None:
    labels = [f"{row['sample_rate_hz'] / 1e6:g} MS/s" for row in summary]
    x = np.arange(len(summary))
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.0))
    metrics = [
        ("pooled_supported_fraction", "Supported selected dwells", "Fraction", 1.0),
        ("median_band_phase_resultant", "Held-band phase concentration", "Median R", 1.0),
        ("median_band_phase_rms_deg", "Held-band phase scatter", "Median RMS (deg)", None),
        ("median_pilot_held_rms_deg", "Pilot/broadband agreement", "Median RMS (deg)", None),
    ]
    for axis, (key, title, ylabel, upper) in zip(axes.flat, metrics, strict=True):
        values = [row[key] for row in summary]
        axis.bar(x, values, width=0.58)
        axis.set_xticks(x, labels)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        if upper is not None:
            axis.set_ylim(0, upper)
        axis.grid(axis="y", alpha=0.25)
        for index, value in enumerate(values):
            axis.text(
                index,
                value,
                f"{value:.3f}" if value < 1 else f"{value:.1f}",
                ha="center",
                va="bottom",
            )
    figure.suptitle("Eight-hour deployed phase evidence by acquisition bandwidth")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "rate-comparison.png", dpi=180, facecolor="white")
    plt.close(figure)


def plot_replay(rows: list[dict], traces: list[dict]) -> None:
    figure, axes = plt.subplots(len(rows), 1, figsize=(13.0, 13.5), sharex=True, sharey=True)
    for axis, row, trace in zip(axes, rows, traces, strict=True):
        axis.plot(trace["time_ms"], trace["raw_phase_deg"], color="0.72", linewidth=0.8)
        axis.plot(
            trace["time_ms"],
            trace["direct_phase_deg"],
            ".-",
            linewidth=1.2,
            markersize=2.5,
            label="direct IQ",
        )
        axis.plot(
            trace["time_ms"],
            trace["fft_common_phase_deg"],
            ".-",
            linewidth=1.0,
            markersize=2.0,
            label="physical-common-band FFT",
        )
        axis.set_ylabel(f"{row['label']}\nphase (deg)")
        axis.set_ylim(-185, 185)
        axis.grid(alpha=0.22)
        axis.text(
            0.995,
            0.90,
            f"direct R={row['direct_phase_r']:.3f} · held R={row['random_held_r']:.3f}",
            transform=axis.transAxes,
            ha="right",
            va="top",
        )
    axes[0].legend(loc="lower left", ncol=2)
    axes[-1].set_xlabel("Dwell time (ms)")
    figure.suptitle("10 MS/s zero-delay, identity-channel phase replay")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "high-bandwidth-phase-traces.png", dpi=180, facecolor="white")
    plt.close(figure)


def plot_bandwidth_ablation(rows: list[dict]) -> None:
    widths = np.asarray([0.5, 1, 2, 4, 8])
    figure, axes = plt.subplots(1, 2, figsize=(12.0, 4.8))
    for row in rows:
        values = [row["bandwidth_phase_r"][str(int(width * 1e6))] for width in widths]
        axes[0].plot(widths, values, ".-", label=row["label"])
    axes[0].set_xlabel("Centered analysis band (MHz)")
    axes[0].set_ylabel("Phase concentration R")
    axes[0].set_ylim(0, 1.02)
    axes[0].set_title("Identity-channel FFT bandwidth ablation")
    axes[0].grid(alpha=0.25)
    axes[0].legend(ncol=3)
    x = np.arange(len(rows))
    width = 0.25
    axes[1].bar(x - width, [r["direct_phase_r"] for r in rows], width, label="direct IQ")
    axes[1].bar(x, [r["fft_common_masked_phase_r"] for r in rows], width, label="common-band FFT")
    axes[1].bar(
        x + width,
        [r["deployed_response_normalized_r"] for r in rows],
        width,
        label="response-normalized A/B",
    )
    axes[1].scatter(
        x,
        [r["random_held_r"] for r in rows],
        marker="D",
        color="black",
        label="direct random-held",
        zorder=4,
    )
    axes[1].set_xticks(x, [r["label"] for r in rows])
    axes[1].set_ylim(0, 1.02)
    axes[1].set_ylabel("Phase concentration R")
    axes[1].set_title("Estimator comparison")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "bandwidth-and-methods.png", dpi=180, facecolor="white")
    plt.close(figure)


def plot_matched_decimation(rows: list[dict]) -> None:
    x = np.arange(len(rows))
    width = 0.34
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    for axis, native_key, decimated_key, title, ylabel in (
        (
            axes[0],
            "direct_phase_r",
            "decimated_2p5m_direct_phase_r",
            "Whole-dwell fit",
            "Phase concentration R",
        ),
        (
            axes[1],
            "random_held_r",
            "decimated_2p5m_random_held_r",
            "Random non-overlapping holdout",
            "Held phase concentration R",
        ),
    ):
        axis.bar(x - width / 2, [row[native_key] for row in rows], width, label="native 10 MS/s")
        axis.bar(
            x + width / 2,
            [row[decimated_key] for row in rows],
            width,
            label="same IQ low-pass/decimated to 2.5 MS/s",
        )
        axis.set_xticks(x, [row["label"] for row in rows])
        axis.set_ylim(0, 1.02)
        axis.set_ylabel(ylabel)
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    figure.suptitle("Matched bandwidth control for the identity-channel estimator")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "matched-decimation.png", dpi=180, facecolor="white")
    plt.close(figure)


def write_csv(path: Path, rows: list[dict]) -> None:
    keys = sorted({key for row in rows for key in row if not isinstance(row[key], (dict, list))})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in keys} for row in rows)


def main() -> None:
    selection = json.loads((REPORT_DIR / "selection.json").read_text())
    sessions, visits = phase_product_rows()
    summary = summarize_rates(sessions, visits)
    replay, traces = replay_selected(selection)
    plot_rate_comparison(summary)
    plot_replay(replay, traces)
    plot_bandwidth_ablation(replay)
    plot_matched_decimation(replay)
    write_csv(REPORT_DIR / "sessions.csv", sessions)
    write_csv(REPORT_DIR / "selected-visits.csv", visits)
    write_csv(REPORT_DIR / "raw-replay.csv", replay)
    payload = {
        "schema_version": 1,
        "interval_start_utc": selection["interval_start_utc"],
        "interval_stop_utc": selection["interval_stop_utc"],
        "production_phase_summary": summary,
        "raw_replay": replay,
        "raw_replay_summary": {
            "median_direct_phase_r": float(np.median([row["direct_phase_r"] for row in replay])),
            "median_random_held_r": float(np.median([row["random_held_r"] for row in replay])),
            "median_fft_common_phase_r": float(
                np.median([row["fft_common_masked_phase_r"] for row in replay])
            ),
            "median_deployed_response_normalized_r": float(
                np.median([row["deployed_response_normalized_r"] for row in replay])
            ),
            "median_direct_coherence": float(
                np.median([row["median_direct_coherence"] for row in replay])
            ),
            "median_decimated_2p5m_direct_phase_r": float(
                np.median([row["decimated_2p5m_direct_phase_r"] for row in replay])
            ),
            "median_decimated_2p5m_random_held_r": float(
                np.median([row["decimated_2p5m_random_held_r"] for row in replay])
            ),
            "median_decimated_2p5m_direct_coherence": float(
                np.median([row["decimated_2p5m_median_direct_coherence"] for row in replay])
            ),
        },
    }
    (REPORT_DIR / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["raw_replay_summary"], indent=2))


if __name__ == "__main__":
    main()
