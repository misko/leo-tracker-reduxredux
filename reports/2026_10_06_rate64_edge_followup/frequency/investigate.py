"""Bounded report-only full-carrier CFO, alias, RF-scaling and dilation audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

TS = 4.4e-6
TG = 2e-6 / 15
SPACING = 234375.0
PERIOD = 1 / TS
LIGHT = 299792458.0


def wrap(value):
    return (np.asarray(value) + PERIOD / 2) % PERIOD - PERIOD / 2


def signed_indices(edge):
    """Independent signed-carrier list from published Appendix-A allocation."""
    name = str(getattr(edge, "value", edge))
    return np.arange(-496, -488) if name == "lower" else np.arange(488, 496)


def center(edge):
    return float(signed_indices(edge).mean() * SPACING)


def bias(edge):
    return float(wrap(-center(edge)))


def independent_codes(edge, symbol_roll=0):
    from leo.analysis.starlink.templates import QIN_EDGE_PILOT_HEX_V1

    # Share only the factual Appendix-A integers, independently decode states.
    bins = signed_indices(edge) % 1024
    states = np.array(
        [
            [(int(QIN_EDGE_PILOT_HEX_V1[int(k)], 16) >> (2 * (299 - i))) & 3 for k in bins]
            for i in range(300)
        ]
    )
    return np.roll(np.exp(0.5j * np.pi * (states + 0.5)), symbol_roll, axis=0)


def physical_frame(sample_rate_hz, edge, *, symbol_roll=0):
    """Full signed-carrier OFDM, followed by a continuous pilot-center mixer.

    Evaluate after ideal band isolation at output sample times. This is not an
    analog-filter model. No production waveform synthesizer is used here.
    """
    time = np.arange(round(sample_rate_hz / 750)) / sample_rate_hz
    symbols = np.floor(time / TS).astype(int)
    frequencies = signed_indices(edge) * SPACING
    codes = independent_codes(edge, symbol_roll)
    output = np.zeros(time.size, dtype=complex)
    for i in range(2, 302):
        use = np.flatnonzero(symbols == i)
        local = time[use] - i * TS - TG
        carriers = np.exp(2j * np.pi * local[:, None] * frequencies)
        output[use] = carriers @ codes[i - 2] / np.sqrt(8)
    return output * np.exp(-2j * np.pi * center(edge) * time)


def coordinate_sweep():
    from leo.analysis.starlink import pilot_methods
    from leo.analysis.starlink.pilot_search_geometry import canonicalize_pilot_cfo
    from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz

    rows = []
    for fs in (2500000, 10000000):
        for edge in ("lower", "upper"):
            nominal = 0 if fs == 2500000 else (-312500 if edge == "lower" else 312500)
            tuned = starlink_edge_rf_center_frequency_hz(1, edge) - 9750000000 - nominal
            truths = [
                0,
                -50000,
                50000,
                -400000,
                400000,
                -PERIOD / 2 - bias(edge) - 1000,
                -PERIOD / 2 - bias(edge) + 1000,
                PERIOD / 2 - bias(edge) - 1000,
                PERIOD / 2 - bias(edge) + 1000,
            ]
            frame = physical_frame(fs, edge)
            times = np.arange(frame.size) / fs
            for truth in truths:
                signal = frame * np.exp(2j * np.pi * (nominal + truth) * times)
                acquired = [nominal + truth + k * PERIOD for k in (-1, 0, 1)]
                scores = pilot_methods.conditioned_glrt64_scores(
                    signal, fs, epoch_samples=[0] * 3, acquired_cfo_hz=acquired, edge=edge
                )
                with patch.object(pilot_methods, "qin_edge_pilot_frame", physical_frame):
                    corrected = pilot_methods.conditioned_glrt64_scores(
                        signal, fs, epoch_samples=[0], acquired_cfo_hz=[nominal + truth], edge=edge
                    )[0]
                assert corrected.exact_score > 0.999999
                assert abs(corrected.tracking_cfo_hz - nominal - truth) < 1e-5
                for branch, score in zip((-1, 0, 1), scores, strict=True):
                    canonical = canonicalize_pilot_cfo(
                        score.tracking_cfo_hz,
                        starlink_channel=1,
                        edge=edge,
                        tuned_center_frequency_hz=int(tuned),
                    )
                    projected = float(wrap(canonical.canonical_residual_cfo_hz - bias(edge)))
                    error = float(wrap(projected - wrap(truth)))
                    # Independent physical injection and production estimator:
                    # the grid has 443.892 Hz cells; allow half a cell + rounding.
                    if branch == 0:
                        assert abs(error) < PERIOD / 1024 + 1, (
                            fs,
                            edge,
                            truth,
                            branch,
                            error,
                            score,
                        )
                    rows.append(
                        {
                            "rate_hz": fs,
                            "edge": edge,
                            "truth_cfo_hz": truth,
                            "nominal_tuning_hz": nominal,
                            "acquired_alias_branch": branch,
                            "raw_detector_hz": score.tracking_cfo_hz,
                            "detector_exact_score": score.exact_score,
                            "published_wrapped_hz": canonical.canonical_residual_cfo_hz,
                            "published_alias_lift": canonical.alias_lift,
                            "corrected_wrapped_hz": projected,
                            "corrected_wrapped_error_hz": error,
                            "physical_template_exact_score": corrected.exact_score,
                            "physical_template_raw_hz": corrected.tracking_cfo_hz,
                        }
                    )
    return rows


def alias_examples():
    rows = []
    for edge in ("lower", "upper"):
        for truth in (PERIOD / 2 - 1000, -PERIOD / 2 + 1000, 400000):
            legacy, detector_lift = (
                float(wrap(truth + bias(edge))),
                math.floor((truth + bias(edge) + PERIOD / 2) / PERIOD),
            )
            naive = legacy - bias(edge)
            projected = float(wrap(naive))
            physical_lift = round((truth - projected) / PERIOD)
            rows.append(
                dict(
                    edge=edge,
                    truth_hz=truth,
                    wrapped_detector_hz=legacy,
                    naive_subtract_hz=naive,
                    physical_wrapped_hz=projected,
                    detector_lift=detector_lift,
                    physical_lift=physical_lift,
                    reconstructed_hz=projected + physical_lift * PERIOD,
                )
            )
    return rows


def doppler_rows():
    from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
    from leo.sky.doppler import doppler_shift_hz

    rows = []
    for channel in (1, 4):
        lower = starlink_edge_rf_center_frequency_hz(channel, "lower")
        upper = starlink_edge_rf_center_frequency_hz(channel, "upper")
        assert upper - lower == 230625000
        for rate in (-7000, -1000, 0, 1000, 7000):
            shifts = [float(doppler_shift_hz(f, rate / 1000)) for f in (lower, upper)]
            assert np.isclose(shifts[1] - shifts[0], -(upper - lower) * rate / LIGHT)
            rows.append(
                dict(
                    channel=channel,
                    illustrative_range_rate_m_s=rate,
                    lower_rf_hz=lower,
                    upper_rf_hz=upper,
                    lower_doppler_hz=shifts[0],
                    upper_doppler_hz=shifts[1],
                    upper_minus_lower_hz=shifts[1] - shifts[0],
                    upper_lower_slope_ratio=upper / lower,
                )
            )
    return rows


def dilation_rows():
    """Isolate frequency dilation after removing the common edge-center CFO.

    Exact tone integration avoids fabricated sample-boundary losses from an
    unfiltered rectangular-symbol model. Code timing, CP, filtering and noise
    are deliberately outside this small calculation.
    """
    offsets = (np.arange(8) - 3.5) * SPACING
    rows = []
    for ppm in (0, 1, 5, 10, 7000 / LIGHT * 1e6, 25, 50, 100):
        for symbols in (64, 300):
            duration = symbols * TS
            residuals = offsets * ppm * 1e-6
            individual = np.sinc(residuals * duration) ** 2
            # Align phase at support midpoint, then coherently combine eight
            # equal-amplitude demodulated tones. A time-scaled model is exact.
            fixed = float(np.mean(np.sinc(residuals * duration)) ** 2)
            rows.append(
                dict(
                    scale_ppm=ppm,
                    symbols=symbols,
                    duration_s=duration,
                    endpoint_residual_hz=float(abs(residuals[-1])),
                    endpoint_phase_span_rad=float(2 * np.pi * abs(residuals[-1]) * duration),
                    timing_drift_ns=duration * ppm * 1e3,
                    fixed_cfo_combined_coherence=fixed,
                    outer_tone_coherence=float(individual[-1]),
                    time_scaled_coherence=1.0,
                )
            )
    return rows


def continuous_periodic_physical(times, edge, *, symbol_roll=0):
    """Analytic repeated local-symbol waveform, continuously mixed globally."""
    within = np.mod(times, 1 / 750)
    symbol = np.floor(within / TS + 1e-9).astype(int)
    use = (symbol >= 2) & (symbol < 302)
    output = np.zeros(times.size, dtype=complex)
    local = within[use] - symbol[use] * TS - TG
    carriers = np.exp(2j * np.pi * local[:, None] * signed_indices(edge) * SPACING)
    codes = independent_codes(edge, symbol_roll)[symbol[use] - 2]
    output[use] = np.sum(carriers * codes, axis=1) / np.sqrt(8)
    return output * np.exp(-2j * np.pi * center(edge) * times)


def repeated_waveform_stress():
    """20 ms rectangular pilot stress: fixed clock versus known-scale oracle.

    Known-scale comparator changes both symbol duration and frame folding in
    the report process. Remaining integer frame rounding is kept visible.
    """
    from leo.analysis.starlink import pilot_methods
    from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz

    rows = []
    for fs in (2500000, 10000000):
        for edge in ("lower", "upper"):
            rf = starlink_edge_rf_center_frequency_hz(1, edge)
            times = np.arange(round(0.020 * fs)) / fs
            for velocity in (-6000, 0, 6000):
                scale = 1 - velocity / LIGHT
                doppler = rf * (scale - 1)
                signal = continuous_periodic_physical(scale * times, edge)
                signal *= np.exp(2j * np.pi * doppler * times)

                def fixed_template(sample_rate_hz, edge, *, symbol_roll=0):
                    t = np.arange(round(sample_rate_hz / 750)) / sample_rate_hz
                    return continuous_periodic_physical(t, edge, symbol_roll=symbol_roll)

                with patch.object(pilot_methods, "qin_edge_pilot_frame", fixed_template):
                    fixed = pilot_methods.conditioned_glrt64_score(
                        signal, fs, epoch_sample=0, acquired_cfo_hz=doppler, edge=edge
                    )

                def scaled_template(sample_rate_hz, edge, *, symbol_roll=0, scale=scale):
                    t = np.arange(round(sample_rate_hz / (750 * scale))) / sample_rate_hz
                    return continuous_periodic_physical(scale * t, edge, symbol_roll=symbol_roll)

                with (
                    patch.object(pilot_methods, "qin_edge_pilot_frame", scaled_template),
                    patch.object(pilot_methods, "FRAME_RATE_HZ", 750 * scale),
                    patch.object(pilot_methods, "OFDM_SYMBOL_DURATION_S", TS / scale),
                ):
                    scaled = pilot_methods.conditioned_glrt64_score(
                        signal, fs, epoch_sample=0, acquired_cfo_hz=doppler, edge=edge
                    )
                rows.append(
                    dict(
                        rate_hz=fs,
                        edge=edge,
                        illustrative_range_rate_m_s=velocity,
                        scale_ppm=(scale - 1) * 1e6,
                        probe_duration_s=0.020,
                        accumulated_timing_drift_ns=abs(scale - 1) * 0.020 * 1e9,
                        accumulated_timing_drift_samples=abs(scale - 1) * 0.020 * fs,
                        known_center_doppler_hz=doppler,
                        fixed_frame_exact_score=fixed.exact_score,
                        fixed_frame_control_score=fixed.control_score,
                        fixed_frame_tracking_error_hz=fixed.tracking_cfo_hz - doppler,
                        known_scale_exact_score=scaled.exact_score,
                        known_scale_control_score=scaled.control_score,
                        known_scale_tracking_error_hz=scaled.tracking_cfo_hz - doppler,
                    )
                )
    return rows


def plots(output, payload):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150}
    )
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.0), constrained_layout=True)
    truth = np.linspace(-170000, 170000, 700)
    for edge, color in (("lower", "#277da1"), ("upper", "#db6d34")):
        axes[0].plot(
            truth / 1000,
            wrap(truth + bias(edge)) / 1000,
            label=f"{edge}: b={bias(edge) / 1000:+.3f} kHz",
            color=color,
        )
    axes[0].plot(
        truth / 1000, wrap(truth) / 1000, "k--", alpha=0.6, label="after correction + wrap"
    )
    axes[0].set(
        xlabel="Injected physical CFO (kHz)",
        ylabel="Wrapped coordinate (kHz)",
        title="Correction moves the alias seam",
    )
    axes[0].legend(fontsize=8, loc="upper left")
    for edge, color in (("lower", "#277da1"), ("upper", "#db6d34")):
        use = [
            r
            for r in payload["coordinate_sweep"]
            if r["edge"] == edge and r["acquired_alias_branch"] == 0
        ]
        axes[1].scatter(
            [r["truth_cfo_hz"] / 1000 for r in use],
            [r["corrected_wrapped_error_hz"] for r in use],
            color=color,
            marker="o" if edge == "lower" else "x",
            label=edge,
        )
    axes[1].axhline(0, color="k", linewidth=0.8)
    for limit in (-PERIOD / 1024, PERIOD / 1024):
        axes[1].axhline(limit, color="#888888", linestyle=":", linewidth=0.8)
    axes[1].set(
        xlabel="Injected physical CFO (kHz)",
        ylabel="Corrected wrapped error (Hz)",
        title="Both rates; known epoch and acquired CFO",
        ylim=(-250, 250),
    )
    axes[1].text(
        0.04,
        0.08,
        "Maximum error: 8.2 × 10⁻⁹ Hz\nDotted: half a GLRT grid cell",
        transform=axes[1].transAxes,
        fontsize=9,
    )
    axes[1].legend()
    fig.suptitle(
        "Full signed-carrier synthesis validates CFO sign, tuning and alias conversion", fontsize=12
    )
    fig.savefig(output / "cfo-coordinate-audit.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.0), constrained_layout=True)
    rate = np.linspace(-7000, 7000, 300)
    axes[0].plot(rate / 1000, -230625000 * rate / LIGHT / 1000, color="#277da1")
    axes[0].axhline(0, color="k", linewidth=0.6)
    axes[0].set(
        xlabel="Illustrative range rate (km/s; receding positive)",
        ylabel="Upper − lower Doppler (kHz)",
        title="Physical edge separation: 230.625 MHz",
    )
    for n, color in ((64, "#277da1"), (300, "#db6d34")):
        use = [r for r in payload["tone_dilation"] if r["symbols"] == n]
        axes[1].plot(
            [r["scale_ppm"] for r in use],
            [100 * (1 - r["fixed_cfo_combined_coherence"]) for r in use],
            "o-",
            color=color,
            label=f"{n} symbols ({n * TS * 1000:.3f} ms)",
        )
    axes[1].axvline(
        7000 / LIGHT * 1e6, color="k", linestyle="--", linewidth=0.8, label="illustrative 7 km/s"
    )
    axes[1].set(
        xlabel="Residual time/frequency scale (ppm)",
        ylabel="Eight-tone coherent power loss (%)",
        title="CFO alone leaves a small per-tone dilation",
    )
    axes[1].legend(fontsize=8)
    fig.suptitle("Physical Doppler differs from the constant template convention bias", fontsize=12)
    fig.savefig(output / "doppler-and-dilation.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4), constrained_layout=True)
    stress = [r for r in payload["repeated_waveform_stress"] if r["illustrative_range_rate_m_s"]]
    x = np.arange(len(stress))
    labels = [
        f"{r['rate_hz'] / 1e6:g}M\n{r['edge'][0].upper()} "
        f"{'app' if r['illustrative_range_rate_m_s'] < 0 else 'rec'}"
        for r in stress
    ]
    for prefix, shift, color, name in (
        ("fixed_frame", -0.1, "#db6d34", "Fixed frame/symbol clock"),
        ("known_scale", 0.1, "#277da1", "Known-scale template + folding"),
    ):
        exact = [100 * r[f"{prefix}_exact_score"] for r in stress]
        margin = [r[f"{prefix}_exact_score"] - r[f"{prefix}_control_score"] for r in stress]
        axes[0].scatter(x + shift, exact, color=color, label=name, zorder=3)
        axes[1].scatter(x + shift, margin, color=color, label=name, zorder=3)
    for ax in axes:
        ax.set_xticks(x, labels, fontsize=8)
        ax.axvline(3.5, color="#aaaaaa", linewidth=0.8)
        ax.grid(axis="y", alpha=0.2)
    axes[0].set(
        ylabel="Conditional exact score (%)",
        title="Exact evidence improves with known scale",
        ylim=(98.5, 100.1),
    )
    axes[1].set(
        ylabel="Exact − control margin", title="Control score also changes; margin is mixed"
    )
    axes[0].legend(fontsize=8, loc="lower right")
    fig.suptitle(
        "20 ms rectangular pilot stress at illustrative ±6 km/s; known epoch and center CFO",
        fontsize=12,
    )
    fig.savefig(output / "twenty-ms-waveform-stress.png")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("/opt/leo-adaptive-memory/9181d637d/src")
    )
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source))
    args.output.mkdir(parents=True, exist_ok=True)
    source_files = [
        "leo/analysis/starlink/templates.py",
        "leo/analysis/starlink/pilot_methods.py",
        "leo/analysis/starlink/pilot_search_geometry.py",
        "leo/analysis/starlink/seeded_acquisition.py",
        "leo/contracts/starlink_frequency.py",
        "leo/sky/doppler.py",
        "leo/storage/scanner_tracking_source.py",
        "leo/application/scanner_trajectory.py",
        "leo/analysis/persistent_hop_trajectory.py",
        "leo/application/scanner_tracking.py",
        "leo/analysis/persistent_hop_tle_match.py",
        "leo/analysis/catalogue_prediction.py",
    ]
    payload = {
        "schema": "report-only-frequency-audit-v1",
        "source_root": str(args.source),
        "source_hashes": {
            f: hashlib.sha256((args.source / f).read_bytes()).hexdigest() for f in source_files
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "alias_period_hz": PERIOD,
        "bias_hz": {e: bias(e) for e in ("lower", "upper")},
        "coordinate_sweep": coordinate_sweep(),
        "alias_examples": alias_examples(),
        "illustrative_doppler": doppler_rows(),
        "tone_dilation": dilation_rows(),
        "repeated_waveform_stress": repeated_waveform_stress(),
        "scope": (
            "Synthetic conditional estimator test and source audit; no acquisition, "
            "analog model, real-IQ performance estimate or localization."
        ),
    }
    manifest = Path(__file__).parent.parent / "data/experiment-spec.json"
    if manifest.exists():
        payload["experiment_spec_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (args.output / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    plots(args.output, payload)
    print(
        json.dumps(
            {
                "cases": len(payload["coordinate_sweep"]),
                "bias_hz": payload["bias_hz"],
                "max_known_seed_wrapped_error_hz": max(
                    abs(r["corrected_wrapped_error_hz"])
                    for r in payload["coordinate_sweep"]
                    if r["acquired_alias_branch"] == 0
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
