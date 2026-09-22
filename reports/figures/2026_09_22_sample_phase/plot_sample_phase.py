"""Plot every paired IQ sample in a fixed strong dual-detection saved interval.

Run with the research checkout's Python and PYTHONPATH=src:tools, supplying
--research-root and --output. Reads saved IQ only; never selects by phase.
"""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from scipy.signal import fftconvolve, firwin

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def compensate(iq, rate, model):
    t = (np.arange(len(iq)) - model["reference_sample"]) / rate
    y = iq[:, 1] * np.exp(
        -2j * np.pi * (model["relative_cfo_hz"] * t + model["relative_cfo_rate_hz_s"] * t * t / 2)
    )
    # Symmetric centered FIR advances RX1 by positive fitted envelope delay.
    n = np.arange(-32, 33)
    h = np.sinc(n + model["effective_delay_samples"]) * np.hanning(65)
    h /= h.sum()
    y = fftconvolve(y, h, mode="same")
    return np.column_stack((iq[:, 0], y))


def check_compensation():
    rate = 2_500_000
    n = np.arange(10000)
    f, cfo, delay, phi = 123456, -675400, 2.375, 0.71
    x = np.exp(2j * np.pi * f * n / rate)
    y = np.exp(2j * np.pi * f * (n - delay) / rate + 2j * np.pi * cfo * n / rate + 1j * phi)
    z = compensate(
        np.column_stack((x, y)),
        rate,
        {
            "reference_sample": 0,
            "relative_cfo_hz": cfo,
            "relative_cfo_rate_hz_s": 0,
            "effective_delay_samples": delay,
        },
    )
    error = np.angle(z[100:-100, 1] * z[100:-100, 0].conj() * np.exp(-1j * phi))
    assert np.max(abs(error)) < 1e-4, "CFO/delay sign or centering error"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    check_compensation()
    args.output.mkdir(parents=True, exist_ok=True)
    session, visit_index, rate = "scan-hop-e46d3aba244cf641", 588, 2_500_000
    evidence_path = (
        args.research_root
        / "reports/figures/2026_09_21_glrt_guided_phase/e46d3aba244cf641-588.json"
    )
    evidence = json.loads(evidence_path.read_text())
    model = evidence["evolution_result"]["map_model"]
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    with AdaptiveHopAnalysisInputStore(store).source(session) as source:
        iq = source.read_visit(visit_index)
        manifest = source.input_manifest_sha256
        assert manifest == evidence["input_manifest_sha256"]
        analysis = analyze_adaptive_hop_visit(
            source,
            visit_index,
            configuration=AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=rate, probe_stride_ms=20
            ),
        )
    probes = tuple(p for p in analysis.probes if p.probe_index == 1)
    pairs = _phase_blind_pairs(analysis.model_copy(update={"probes": probes}))
    assert pairs, "No dual GLRT pair in the preselected 20–40 ms probe"
    left, right, offset, start = pairs[0]
    corrected = compensate(iq, rate, model)
    # All of this common passband is retained: no pilot-only or phase-based mask.
    # RX0 f and RX1 f+CFO must both be physically recorded; allow FIR transitions.
    low, high = -500_000.0, 1_175_000.0
    center, halfwidth = (low + high) / 2, (high - low) / 2
    taps = firwin(513, halfwidth, fs=rate)
    taps = taps * np.exp(2j * np.pi * center * (np.arange(513) - 256) / rate)
    common = np.column_stack([fftconvolve(corrected[:, r], taps, mode="same") for r in (0, 1)])
    begin, end = 72500, 77500  # 29–31 ms: every one of 5000 samples.
    samples = np.arange(begin, end)
    raw = np.angle(iq[begin:end, 1] * iq[begin:end, 0].conj())
    residual = np.angle(common[begin:end, 1] * common[begin:end, 0].conj())
    # Retain all samples, including weak-amplitude/noisy ones, without unwrapping.
    rows = np.column_stack(
        (
            samples,
            samples / rate,
            np.degrees(raw),
            np.degrees(residual),
            abs(iq[begin:end, 0]),
            abs(iq[begin:end, 1]),
            abs(common[begin:end, 0]),
            abs(common[begin:end, 1]),
        )
    )
    np.savetxt(
        args.output / "sample-phase.csv",
        rows,
        delimiter=",",
        fmt="%.12g",
        header="sample_index,time_s,raw_phase_deg,compensated_common_band_phase_deg,raw_rx0_abs,raw_rx1_abs,common_rx0_abs,common_rx1_abs",
        comments="",
    )
    fig, axes = plt.subplots(2, 2, figsize=(14, 7), sharey=True)
    for column, mask in enumerate(
        (np.ones(len(samples), bool), (samples >= 75000) & (samples < 75050))
    ):
        for row, phase in enumerate((raw, residual)):
            ax = axes[row, column]
            x = samples[mask] / rate * 1000 if column == 0 else (samples[mask] - 75000) / rate * 1e6
            ax.scatter(
                x,
                np.degrees(phase[mask]),
                s=2 if column == 0 else 22,
                alpha=0.45 if column == 0 else 0.9,
                linewidths=0,
            )
            ax.set_ylim(-185, 185)
            ax.set_yticks([-180, -90, 0, 90, 180])
            ax.grid(alpha=0.2)
            ax.set_xlabel("Time from dwell start (ms)" if column == 0 else "Time from 30 ms (µs)")
            ax.set_title(
                ("Raw RX1 − RX0" if row == 0 else "CFO/drift + delay corrected; common band")
                + (" — 5,000 individual samples" if column == 0 else " — 50 individual samples")
            )
    for ax in axes[:, 0]:
        ax.set_ylabel("Wrapped phase difference (degrees)")
    fig.suptitle(
        f"{session}, visit {visit_index}: strong paired GLRT detection in 20–40 ms\n"
        "Every sample shown; 400 ns spacing; no phase averaging or constant-phase subtraction"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(args.output / "sample-phase.png", dpi=180)
    cross = common[begin:end, 1] * common[begin:end, 0].conj()
    power0 = float(np.sum(abs(common[begin:end, 0]) ** 2))
    power1 = float(np.sum(abs(common[begin:end, 1]) ** 2))
    cross_sum = np.sum(cross)
    coherence = float(abs(cross_sum) / np.sqrt(power0 * power1))
    best_phase = float(np.angle(cross_sum))
    candidate_phase = np.linspace(-np.pi, np.pi, 1441)
    signed_coherence = np.real(np.exp(-1j * candidate_phase) * cross_sum) / np.sqrt(power0 * power1)
    best_gain = abs(cross_sum) / power0
    normalized_error_squared = (
        power1
        + best_gain**2 * power0
        - 2 * best_gain * np.real(np.exp(-1j * candidate_phase) * cross_sum)
    ) / power1
    profile = np.column_stack(
        (
            np.degrees(candidate_phase),
            signed_coherence,
            np.sqrt(normalized_error_squared),
            np.full(len(candidate_phase), coherence),
        )
    )
    np.savetxt(
        args.output / "constant-phase-profile.csv",
        profile,
        delimiter=",",
        fmt="%.12g",
        header=(
            "candidate_rx1_minus_rx0_phase_deg,signed_coherence,"
            "normalized_prediction_error,ordinary_coherence_magnitude"
        ),
        comments="",
    )
    groups = np.array_split(np.arange(len(cross)), 10)
    delete_phase = np.asarray([np.angle(cross_sum - np.sum(cross[group])) for group in groups])
    delete_delta = np.angle(np.exp(1j * (delete_phase - best_phase)))
    phase_jackknife_se = float(np.sqrt(9 / 10 * np.sum(delete_delta**2)))
    fig, ax_error = plt.subplots(figsize=(10, 5))
    ax_coherence = ax_error.twinx()
    phase_degrees = np.degrees(candidate_phase)
    (line_error,) = ax_error.plot(
        phase_degrees,
        np.sqrt(normalized_error_squared),
        label="Normalized prediction error",
        color="tab:blue",
    )
    (line_coherence,) = ax_coherence.plot(
        phase_degrees,
        signed_coherence,
        label="Signed coherence",
        color="tab:orange",
    )
    ax_coherence.axhline(coherence, color="tab:orange", alpha=0.25, linestyle=":")
    ax_error.axvline(np.degrees(best_phase), color="black", alpha=0.7, linestyle="--")
    ax_error.annotate(
        f"best phase = {np.degrees(best_phase):+.2f}°\n"
        f"conditional block SE = {np.degrees(phase_jackknife_se):.2f}°",
        xy=(np.degrees(best_phase), np.sqrt(1 - coherence**2)),
        xytext=(18, 18),
        textcoords="offset points",
        arrowprops={"arrowstyle": "->", "color": "black"},
    )
    ax_error.set(
        xlabel="Candidate constant RX1 − RX0 phase (degrees)",
        ylabel="Normalized prediction error (lower is better)",
        xlim=(-180, 180),
    )
    ax_coherence.set_ylabel("Signed coherence (higher is better)")
    ax_error.grid(alpha=0.2)
    ax_error.legend(
        [line_error, line_coherence],
        [line_error.get_label(), line_coherence.get_label()],
        loc="upper left",
    )
    fig.suptitle(
        "Enumerating every constant phase offset — visit 588, 29–31 ms\n"
        f"ordinary coherence magnitude is invariant at {coherence:.3f}"
    )
    fig.tight_layout()
    fig.savefig(args.output / "constant-phase-profile.png", dpi=180)
    plt.close(fig)
    metadata = {
        "session_id": session,
        "visit_index": visit_index,
        "sample_rate_hz": rate,
        "sample_interval_s": 1 / rate,
        "sample_start_inclusive": begin,
        "sample_stop_exclusive": end,
        "plot_sample_count": len(samples),
        "zoom_sample_count": 50,
        "input_manifest_sha256": manifest,
        "model": model,
        "paired_glrt_probe_start_sample": start,
        "paired_glrt_probe_duration_ms": 20,
        "rx0_glrt": left.model_dump(mode="json"),
        "rx1_glrt": right.model_dump(mode="json"),
        "glrt_relative_frequency_hz": offset,
        "common_bandpass_hz": [low, high],
        "filter_taps": 513,
        "weighted_complex_coherence_of_plotted_interval": coherence,
        "most_likely_constant_rx1_minus_rx0_phase_deg": float(np.degrees(best_phase)),
        "rx1_correction_to_apply_deg": float(-np.degrees(best_phase)),
        "minimum_normalized_prediction_error": float(np.sqrt(1 - coherence**2)),
        "ten_contiguous_group_delete_jackknife_phase_se_deg": float(np.degrees(phase_jackknife_se)),
        "candidate_phase_grid_step_deg": 0.25,
        "ordinary_coherence_is_phase_invariant": True,
        "mean_unit_phasor_resultant": float(abs(np.mean(np.exp(1j * residual)))),
        "identity_claim": (
            "phase-blind paired Starlink candidate; individual satellite identity unverified"
        ),
        "phase_definition": (
            "arg(RX1 * conj(RX0)); raw or temporally compensated common-band waveform, "
            "not calibrated geometric phase"
        ),
        "channel_response_equalized": False,
        "fitting_scope": (
            "frozen previous model fitted to first 60 ms; plotted interval is descriptive "
            "in-sample, not new held-out validation"
        ),
        "model_evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: metadata[k]
                for k in (
                    "weighted_complex_coherence_of_plotted_interval",
                    "mean_unit_phasor_resultant",
                )
            }
        )
    )
    for candidate in (left, right):
        print(candidate.model_dump_json())


if __name__ == "__main__":
    main()
