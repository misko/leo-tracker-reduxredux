#!/usr/bin/env python3
"""Render a quantization-aware audit of the detailed GLRT epoch curve."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SAMPLE_RATE_HZ = 2_500_000.0
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / 750.0
PROBE_STEP_SAMPLES = round(0.025 * SAMPLE_RATE_HZ)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def polynomial_fit(
    train_t: np.ndarray,
    train_y: np.ndarray,
    eval_t: np.ndarray,
    *,
    degree: int,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    center = float(np.mean(train_t))
    scale = float(np.ptp(train_t) / 2.0)
    coefficients = np.polyfit((train_t - center) / scale, train_y, degree)
    prediction = np.polyval(coefficients, (eval_t - center) / scale)
    return prediction, coefficients, center, scale


def blocked_polynomial_prediction(
    times: np.ndarray,
    values: np.ndarray,
    *,
    degree: int,
    block_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    origin = float(np.floor(times[0] / block_s) * block_s)
    block_index = np.floor((times - origin) / block_s).astype(int)
    prediction = np.full(values.shape, np.nan)
    for block in np.unique(block_index):
        validation = block_index == block
        training = ~validation
        prediction[validation] = polynomial_fit(
            times[training],
            values[training],
            times[validation],
            degree=degree,
        )[0]
    return prediction, block_index


def quantized_prediction(
    continuous_prediction: np.ndarray,
    absolute_epoch_samples: np.ndarray,
    *,
    reference_epoch_sample: int,
) -> np.ndarray:
    frame_index = np.rint(
        (absolute_epoch_samples - reference_epoch_sample) / FRAME_PERIOD_SAMPLES
    ).astype(np.int64)
    nominal_epoch = reference_epoch_sample + frame_index * FRAME_PERIOD_SAMPLES
    return np.rint(nominal_epoch + continuous_prediction) - nominal_epoch


def nonuniform_sinusoid_explained_fraction(
    times: np.ndarray,
    values: np.ndarray,
    frequencies_hz: np.ndarray,
) -> np.ndarray:
    """Return descriptive sinusoid R-squared values on the actual time base."""
    centered_time = times - float(times[0])
    centered_values = values - float(np.mean(values))
    total_sum_squares = float(np.sum(np.square(centered_values)))
    output = np.empty(frequencies_hz.shape, dtype=float)
    for index, frequency_hz in enumerate(frequencies_hz):
        phase = 2.0 * np.pi * frequency_hz * centered_time
        design = np.column_stack((np.ones(times.size), np.sin(phase), np.cos(phase)))
        coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
        residual = values - design @ coefficients
        output[index] = 1.0 - float(np.sum(np.square(residual))) / total_sum_squares
    return output


def render(
    output: Path,
    *,
    times: np.ndarray,
    values: np.ndarray,
    sample_starts: np.ndarray,
    quadratic: np.ndarray,
    cubic: np.ndarray,
    quantized_quadratic: np.ndarray,
    quantized_cubic: np.ndarray,
    degrees: np.ndarray,
    training_rms: np.ndarray,
    blocked_rms: np.ndarray,
    frequency_hz: np.ndarray,
    observed_explained_fraction: np.ndarray,
    quantizer_explained_fraction: np.ndarray,
    zoom_start_s: float,
    zoom_stop_s: float,
    cubic_rate_start_hz_s: float,
    cubic_rate_stop_hz_s: float,
) -> None:
    quadratic_residual = values - quadratic
    cubic_correction = cubic - quadratic
    quadratic_exact = np.isclose(quantized_quadratic, values, atol=1e-7)
    cubic_exact = np.isclose(quantized_cubic, values, atol=1e-7)
    observed_cubic_residual = values - cubic
    predicted_rounding_residual = quantized_cubic - cubic
    rounding_residual_correlation = float(
        np.corrcoef(observed_cubic_residual, predicted_rounding_residual)[0, 1]
    )
    probe_phase = np.rint(sample_starts / PROBE_STEP_SAMPLES).astype(int) % 4
    zoom = (times >= zoom_start_s) & (times <= zoom_stop_s)

    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 7.5,
            "figure.titlesize": 13,
        }
    )
    figure = plt.figure(figsize=(14, 10), dpi=150)
    grid = figure.add_gridspec(
        3,
        2,
        height_ratios=(1.15, 1.15, 1.0),
        left=0.075,
        right=0.97,
        top=0.90,
        bottom=0.10,
        hspace=0.34,
        wspace=0.22,
    )
    ax_residual = figure.add_subplot(grid[0, :])
    ax_zoom = figure.add_subplot(grid[1, :])
    ax_validation = figure.add_subplot(grid[2, 0])
    ax_spectrum = figure.add_subplot(grid[2, 1])
    figure.suptitle(
        "Epoch-residual anatomy: smooth timing plus integer-sample quantization\n"
        "candidate-only persisted branch · 550 nominal-25-ms GLRT detections"
    )

    ax_residual.fill_between(
        (times[0], times[-1]),
        -0.5,
        0.5,
        color="#eeeeee",
        alpha=0.75,
        label="±0.5-sample nearest-integer decision region",
    )
    ax_residual.plot(
        times,
        quadratic_residual,
        color="#9b8be0",
        linewidth=0.55,
        alpha=0.68,
    )
    ax_residual.scatter(
        times[quadratic_exact],
        quadratic_residual[quadratic_exact],
        s=7,
        color="#7561c9",
        alpha=0.50,
        linewidths=0,
        label=(
            "quadratic residual; nearest-integer epoch reproduced "
            f"{np.count_nonzero(quadratic_exact)}/{times.size}"
        ),
    )
    ax_residual.scatter(
        times[~quadratic_exact],
        quadratic_residual[~quadratic_exact],
        s=24,
        marker="x",
        color="#d97706",
        linewidths=1.1,
        label="one-sample reconstruction mismatch",
    )
    ax_residual.plot(
        times,
        cubic_correction,
        color="#21145f",
        linewidth=1.8,
        label="extra structure added by global cubic",
    )
    ax_residual.axhline(0.0, color="#222222", linewidth=0.8)
    ax_residual.set_ylabel("Residual / cubic correction (samples)")
    ax_residual.set_title(
        "The visible teeth are mostly the integer epoch quantizer; the cubic correction "
        f"is {rms(cubic_correction):.3f} sample RMS / "
        f"{np.max(np.abs(cubic_correction)):.3f} maximum"
    )
    ax_residual.grid(True, alpha=0.22)
    ax_residual.legend(loc="upper right", ncol=2)
    secondary = ax_residual.secondary_yaxis(
        "right",
        functions=(
            lambda samples: samples * 1_000_000.0 / SAMPLE_RATE_HZ,
            lambda microseconds: microseconds * SAMPLE_RATE_HZ / 1_000_000.0,
        ),
    )
    secondary.set_ylabel("Equivalent timing (µs)")

    colors = ("#4338ca", "#0f766e", "#ca8a04", "#c2410c")
    for phase, color in enumerate(colors):
        selected = zoom & (probe_phase == phase)
        ax_zoom.scatter(
            times[selected],
            values[selected],
            s=25,
            color=color,
            edgecolors="white",
            linewidths=0.4,
            zorder=4,
            label=f"observed epoch · probe phase {phase}/4",
        )
    ax_zoom.plot(
        times[zoom],
        quadratic[zoom],
        color="#666666",
        linestyle="--",
        linewidth=1.2,
        label="continuous quadratic",
    )
    ax_zoom.plot(
        times[zoom],
        cubic[zoom],
        color="#21145f",
        linewidth=1.6,
        label="continuous cubic",
    )
    ax_zoom.step(
        times[zoom],
        quantized_cubic[zoom],
        where="mid",
        color="#d97706",
        linewidth=0.9,
        alpha=0.80,
        label="cubic after integer-epoch quantization",
    )
    ax_zoom.set_xlim(zoom_start_s, zoom_stop_s)
    ax_zoom.set_ylabel("Observed − fixed lattice (samples)")
    ax_zoom.set_xlabel("Time from dwell start (s)")
    ax_zoom.set_title(
        f"One-second zoom: cubic reproduces {np.count_nonzero(cubic_exact)}/{times.size} "
        "quantized epochs over the full interval"
    )
    ax_zoom.grid(True, alpha=0.22)
    ax_zoom.legend(loc="best", ncol=3)

    ax_validation.plot(
        degrees,
        training_rms,
        marker="o",
        color="#7561c9",
        linewidth=1.3,
        label="same-data RMS",
    )
    ax_validation.plot(
        degrees,
        blocked_rms,
        marker="s",
        color="#d97706",
        linewidth=1.3,
        label="held calendar-1-s-block RMS",
    )
    ax_validation.axhline(
        1.0 / np.sqrt(12.0),
        color="#555555",
        linewidth=1.0,
        linestyle=":",
        label="uniform ±0.5-sample rounding reference",
    )
    ax_validation.set_xticks(degrees)
    ax_validation.set_ylim(0.285, max(0.305, float(np.max(blocked_rms)) + 0.001))
    ax_validation.set_ylabel("Epoch prediction RMS (samples)")
    ax_validation.set_xlabel("Global polynomial degree")
    ax_validation.set_title(
        "Added polynomial detail does not materially improve blocked prediction"
    )
    ax_validation.grid(True, alpha=0.22)
    ax_validation.legend(loc="best")

    ax_spectrum.plot(
        frequency_hz,
        100.0 * observed_explained_fraction,
        color="#7561c9",
        linewidth=1.0,
        label="observed cubic residual",
    )
    ax_spectrum.plot(
        frequency_hz,
        100.0 * quantizer_explained_fraction,
        color="#555555",
        linewidth=0.8,
        alpha=0.72,
        label="predicted integer-rounding residual",
    )
    strongest = int(np.argmax(observed_explained_fraction))
    ax_spectrum.scatter(
        [frequency_hz[strongest]],
        [100.0 * observed_explained_fraction[strongest]],
        color="#d97706",
        s=28,
        zorder=3,
        label=(
            f"largest observed line {frequency_hz[strongest]:.2f} Hz · "
            f"{100.0 * observed_explained_fraction[strongest]:.2f}%"
        ),
    )
    ax_spectrum.set_xlim(0.0, 20.0)
    ax_spectrum.set_xlabel("Descriptive residual frequency (Hz)")
    ax_spectrum.set_ylabel("Variance explained by one sinusoid (%)")
    ax_spectrum.set_title("Actual-time sinusoid scan: no single residual frequency explains much")
    ax_spectrum.grid(True, alpha=0.22)
    ax_spectrum.legend(loc="best")

    improvement_ns = (blocked_rms[0] - blocked_rms[1]) * 1_000_000_000.0 / SAMPLE_RATE_HZ
    figure.text(
        0.5,
        0.016,
        f"Predicted-v-observed rounding-residual correlation: "
        f"{rounding_residual_correlation:.3f}. Quadratic→cubic blocked-RMS improvement: "
        f"{improvement_ns:.3f} ns; "
        "exploratory same-sign Doppler-equivalent frame-clock curvature runs "
        f"{cubic_rate_start_hz_s:.0f} to "
        f"{cubic_rate_stop_hz_s:.0f} Hz/s, but is not promoted by this comparison.\n"
        "The epoch quantizer is conditional on the frame index recovered from each "
        "observed epoch; selection and the sinusoid scan are descriptive, not iid.\n"
        "Conventional propagation-delay sign is opposite for observed−nominal epoch, "
        "and clock drift remains confounded. Finer physical timing requires an "
        "independently qualified fractional-timing observable from IQ.",
        ha="center",
        va="bottom",
        fontsize=7.2,
        color="#333333",
    )
    figure.savefig(output, dpi=150, metadata={"Software": "Matplotlib"})
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-evidence", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--zoom-start-s", type=float, default=45.5)
    parser.add_argument("--zoom-stop-s", type=float, default=46.5)
    args = parser.parse_args()

    manifest = load(args.input_manifest)
    if sha256(args.input_evidence) != manifest["evidence"]["sha256"]:
        raise ValueError("input evidence does not match its plot manifest")
    evidence = load(args.input_evidence)
    rows = evidence["detections"]
    if len(rows) != 550:
        raise ValueError("expected the frozen 550-detection cohort")

    times = np.asarray([float(row["absolute_epoch_sample"]) / SAMPLE_RATE_HZ for row in rows])
    values = np.asarray([float(row["epoch_residual_samples"]) for row in rows])
    absolute_epoch_samples = np.asarray(
        [int(row["absolute_epoch_sample"]) for row in rows], dtype=np.int64
    )
    sample_starts = np.asarray([int(row["detection_sample_start"]) for row in rows], dtype=np.int64)
    margins = np.asarray([float(row["margin"]) for row in rows])
    reference_epoch_sample = int(evidence["reference_epoch_sample"])

    degrees = np.arange(2, 9)
    training_rms = []
    blocked_rms = []
    fits: dict[int, np.ndarray] = {}
    block_predictions: dict[int, np.ndarray] = {}
    block_index: np.ndarray | None = None
    for degree in degrees:
        fit = polynomial_fit(times, values, times, degree=int(degree))[0]
        blocked, current_block_index = blocked_polynomial_prediction(
            times,
            values,
            degree=int(degree),
            block_s=1.0,
        )
        fits[int(degree)] = fit
        block_predictions[int(degree)] = blocked
        block_index = current_block_index
        training_rms.append(rms(values - fit))
        blocked_rms.append(rms(values - blocked))
    if block_index is None:
        raise AssertionError("blocked validation did not produce block identifiers")
    training_rms_array = np.asarray(training_rms)
    blocked_rms_array = np.asarray(blocked_rms)

    quadratic = fits[2]
    cubic = fits[3]
    quantized_quadratic = quantized_prediction(
        quadratic,
        absolute_epoch_samples,
        reference_epoch_sample=reference_epoch_sample,
    )
    quantized_cubic = quantized_prediction(
        cubic,
        absolute_epoch_samples,
        reference_epoch_sample=reference_epoch_sample,
    )
    quadratic_exact = np.isclose(quantized_quadratic, values, atol=1e-7)
    cubic_exact = np.isclose(quantized_cubic, values, atol=1e-7)
    observed_cubic_residual = values - cubic
    predicted_rounding_residual = quantized_cubic - cubic

    frequency_hz = np.linspace(0.05, 19.95, 1_991)
    observed_explained_fraction = nonuniform_sinusoid_explained_fraction(
        times,
        observed_cubic_residual,
        frequency_hz,
    )
    quantizer_explained_fraction = nonuniform_sinusoid_explained_fraction(
        times,
        predicted_rounding_residual,
        frequency_hz,
    )

    cubic_center = float(np.mean(times))
    cubic_coefficients_seconds = np.polyfit(times - cubic_center, values, 3)
    endpoint_x = np.asarray([times[0] - cubic_center, times[-1] - cubic_center])
    second_derivative = (
        6.0 * cubic_coefficients_seconds[0] * endpoint_x + 2.0 * cubic_coefficients_seconds[1]
    )
    scale_hz_per_sample = float(evidence["rf_tuning_center_hz"]) / float(evidence["sample_rate_hz"])
    cubic_endpoint_rates = scale_hz_per_sample * second_derivative

    block_rows = []
    for block in np.unique(block_index):
        selected = block_index == block
        block_rows.append(
            {
                "block_index": int(block),
                "count": int(np.count_nonzero(selected)),
                "quadratic_mse_samples2": float(
                    np.mean(np.square(values[selected] - block_predictions[2][selected]))
                ),
                "cubic_mse_samples2": float(
                    np.mean(np.square(values[selected] - block_predictions[3][selected]))
                ),
            }
        )

    output_evidence = {
        "schema": "org.leo.research.epoch-residual-detailed-fit/v1",
        "candidate_only": True,
        "fit_semantics": "retrospective descriptive integer-epoch model",
        "input_evidence": {
            "path": str(args.input_evidence),
            "sha256": sha256(args.input_evidence),
        },
        "detection_count": len(rows),
        "global_polynomial": [
            {
                "degree": int(degree),
                "same_data_rms_samples": float(train),
                "held_calendar_1s_block_rms_samples": float(blocked),
            }
            for degree, train, blocked in zip(
                degrees,
                training_rms_array,
                blocked_rms_array,
                strict=True,
            )
        ],
        "quadratic": {
            "quantized_epoch_exact_count": int(np.count_nonzero(quadratic_exact)),
            "quantized_epoch_exact_fraction": float(np.mean(quadratic_exact)),
            "maximum_absolute_continuous_residual_samples": float(
                np.max(np.abs(values - quadratic))
            ),
        },
        "cubic": {
            "quantized_epoch_exact_count": int(np.count_nonzero(cubic_exact)),
            "quantized_epoch_exact_fraction": float(np.mean(cubic_exact)),
            "maximum_absolute_correction_from_quadratic_samples": float(
                np.max(np.abs(cubic - quadratic))
            ),
            "rms_correction_from_quadratic_samples": rms(cubic - quadratic),
            "predicted_observed_rounding_residual_correlation": float(
                np.corrcoef(observed_cubic_residual, predicted_rounding_residual)[0, 1]
            ),
            "mean_margin_exact_quantized_epoch": float(np.mean(margins[cubic_exact])),
            "mean_margin_one_sample_mismatch": float(np.mean(margins[~cubic_exact])),
            "rf_scaled_same_sign_rate_at_interval_start_hz_s": float(cubic_endpoint_rates[0]),
            "rf_scaled_same_sign_rate_at_interval_stop_hz_s": float(cubic_endpoint_rates[1]),
        },
        "blocked_quadratic_to_cubic_rms_improvement_samples": float(
            blocked_rms_array[0] - blocked_rms_array[1]
        ),
        "blocked_quadratic_to_cubic_rms_improvement_ns": float(
            (blocked_rms_array[0] - blocked_rms_array[1]) * 1_000_000_000.0 / SAMPLE_RATE_HZ
        ),
        "one_second_block_rows": block_rows,
        "sinusoid_scan": {
            "descriptive_only": True,
            "method": "least_squares_sinusoid_scan_on_actual_epoch_times",
            "frequency_grid_count": int(frequency_hz.size),
            "minimum_frequency_hz": float(frequency_hz[0]),
            "maximum_frequency_hz": float(frequency_hz[-1]),
            "look_elsewhere_correction_applied": False,
            "strongest_frequency_hz": float(frequency_hz[np.argmax(observed_explained_fraction)]),
            "strongest_period_s": float(1.0 / frequency_hz[np.argmax(observed_explained_fraction)]),
            "strongest_explained_fraction": float(np.max(observed_explained_fraction)),
        },
        "interpretation_limits": [
            "the one-third-sample visible levels arise from integer absolute epochs "
            "minus the 3333-and-one-third-sample nominal lattice",
            "the quantizer reconstruction is conditional on frame indexes recovered "
            "from the observed absolute epochs",
            "polynomial and sinusoid-scan results are conditioned on the persisted "
            "trajectory and joint all-Qin epoch/CFO GLRT selection",
            "held-calendar-block prediction contains 13 interior interpolation blocks "
            "and two partial edge extrapolation blocks; it is not a causal forecast",
            "the 1991-frequency sinusoid scan has no look-elsewhere correction and is "
            "descriptive only",
            "the cubic rate variation is exploratory because its blocked improvement "
            "over the quadratic is negligible at the available sample resolution",
            "the RF-scaled rate uses a same-sign internal-CFO comparison convention; "
            "conventional propagation-delay sign is opposite for observed-minus-nominal epoch",
            "transmitter frame-clock and receiver sample-clock drift remain confounded, "
            "so this is not identified physical Doppler",
            "sub-sample physical timing requires a separately qualified fractional "
            "timing observable from IQ",
        ],
    }

    args.output_root.mkdir(parents=True, exist_ok=True)
    evidence_path = args.output_root / "epoch-residual-detailed-fit.json"
    evidence_path.write_text(
        json.dumps(output_evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    plot_path = args.output_root / "detailed-epoch-residual-fit.png"
    render(
        plot_path,
        times=times,
        values=values,
        sample_starts=sample_starts,
        quadratic=quadratic,
        cubic=cubic,
        quantized_quadratic=quantized_quadratic,
        quantized_cubic=quantized_cubic,
        degrees=degrees,
        training_rms=training_rms_array,
        blocked_rms=blocked_rms_array,
        frequency_hz=frequency_hz,
        observed_explained_fraction=observed_explained_fraction,
        quantizer_explained_fraction=quantizer_explained_fraction,
        zoom_start_s=args.zoom_start_s,
        zoom_stop_s=args.zoom_stop_s,
        cubic_rate_start_hz_s=float(cubic_endpoint_rates[0]),
        cubic_rate_stop_hz_s=float(cubic_endpoint_rates[1]),
    )
    output_manifest = {
        "schema": "org.leo.research.epoch-residual-detailed-fit-matplotlib/v1",
        "renderer": "matplotlib",
        "script_sha256": sha256(Path(__file__)),
        "evidence": {
            "path": str(evidence_path),
            "sha256": sha256(evidence_path),
            "bytes": evidence_path.stat().st_size,
        },
        "plot": {
            "path": str(plot_path),
            "sha256": sha256(plot_path),
            "bytes": plot_path.stat().st_size,
        },
    }
    manifest_path = args.output_root / "epoch-residual-detailed-fit-manifest.json"
    manifest_path.write_text(
        json.dumps(output_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output_manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
