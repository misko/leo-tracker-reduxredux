#!/usr/bin/env python3
"""Cross-fit exact fractional PSS timing over the full recorded bandwidth."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band
from leo.analysis.starlink.pss_timing import PSS_NATIVE_SAMPLE_RATE_HZ, pss_native_time_samples
from leo.storage.adaptive_hop import AdaptiveHopIqStore

BULK_ROOT = Path("/srv/bulk/leo")
SESSION_ID = "scan-fw-d6704a759a9ec176"
FRAME_RATE_HZ = 750.0
GRID = np.arange(-0.75, 0.75001, 1.0 / 64.0)
BANDWIDTHS_HZ = (2_500_000.0, 5_000_000.0, 10_000_000.0)


def arguments() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-root", type=Path, default=BULK_ROOT)
    parser.add_argument("--output", type=Path, default=here)
    parser.add_argument(
        "--input",
        type=Path,
        default=here.parent / "2026_09_25_five_glrt_tracks_pss",
    )
    return parser.parse_args()


def mode_id(visit_index: int, receiver: int, frequency: float, candidate) -> str:
    identity = (
        f"pss-10m-band-mode-v1:{SESSION_ID}:{visit_index}:{receiver}:"
        f"{frequency:.9f}:{candidate.global_epoch_device_sample}"
    )
    return "sha256:" + hashlib.sha256(identity.encode()).hexdigest()


def capture_band(event, geometry) -> PssCaptureBand:
    center = event.actual_lo_frequency_hz + event.actual_if_offset_hz
    reference = starlink_pss_channel_reference_hz(event.target.channel, event.target.edge)
    half = min(geometry.sample_rate_hz, geometry.bandwidth_hz) / 2
    return PssCaptureBand(geometry.sample_rate_hz, center - reference, -half, half)


def iq_from_raw(raw: np.ndarray, receiver: int) -> np.ndarray:
    return (
        raw[:, receiver, 0].astype(np.float32)
        + 1j * raw[:, receiver, 1].astype(np.float32)
    ).astype(np.complex64)


def circular(values: np.ndarray, reference: float, period: float) -> np.ndarray:
    return (values - reference + period / 2) % period - period / 2


def huber_line(times: np.ndarray, values: np.ndarray):
    center = float(np.mean(times))
    design = np.column_stack((times - center, np.ones(len(times))))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    weights = np.ones(len(times))
    for _ in range(20):
        residuals = values - design @ coefficients
        scale = float(np.median(np.abs(residuals - np.median(residuals))) / 0.6744897501960817)
        if not math.isfinite(scale) or scale < 1e-15:
            break
        cutoff = 1.345 * scale
        weights = np.minimum(1.0, cutoff / np.maximum(np.abs(residuals), 1e-30))
        root = np.sqrt(weights)
        updated, *_ = np.linalg.lstsq(design * root[:, None], values * root, rcond=None)
        if np.max(np.abs(updated - coefficients)) < 1e-12:
            coefficients = updated
            break
        coefficients = updated
    residuals = values - design @ coefficients
    sigma = None
    if len(times) > 2:
        variance = float(np.sum(weights * residuals**2) / (len(times) - 2))
        covariance = variance * np.linalg.pinv(design.T @ (weights[:, None] * design))
        sigma = math.sqrt(max(float(covariance[0, 0]), 0.0))
    return float(coefficients[0]), float(coefficients[1]), sigma, residuals


@lru_cache(maxsize=16)
def fractional_template_bank(
    sample_rate_hz: float,
    center_offset_hz: float,
    cfo_hz: float,
    bandwidth_hz: float,
) -> np.ndarray:
    """Evaluate the finite published PSS projection at exact fractional delays."""

    fft_size = 16_384
    native = pss_native_time_samples()
    frequencies = np.fft.fftfreq(fft_size, 1 / PSS_NATIVE_SAMPLE_RATE_HZ)
    receiver_frequencies = frequencies + cfo_hz - center_offset_hz
    half = bandwidth_hz / 2
    mask = (receiver_frequencies >= -half) & (receiver_frequencies < half)
    spectrum = np.fft.fft(native, fft_size)[mask]
    projected_frequencies = frequencies[mask] - center_offset_hz
    count = math.ceil(len(native) * sample_rate_hz / PSS_NATIVE_SAMPLE_RATE_HZ)
    samples = np.arange(count, dtype=float)
    cfo_phasor = np.exp(2j * np.pi * cfo_hz * samples / sample_rate_hz)
    output = np.empty((len(GRID), count), dtype=np.complex64)
    for index, delay in enumerate(GRID):
        times = (samples - delay) / sample_rate_hz
        phase = 2j * np.pi * times[:, None] * projected_frequencies[None, :]
        template = (np.exp(phase) @ spectrum / fft_size) * cfo_phasor
        template /= np.linalg.norm(template)
        output[index] = template
    output.flags.writeable = False
    return output


def refine_frame(samples: np.ndarray, measured: int, templates: np.ndarray):
    segment = samples[measured : measured + templates.shape[1]]
    correlations = templates.conj() @ segment
    scores = np.abs(correlations) ** 2 / max(float(np.vdot(segment, segment).real), 1e-30)
    best = int(np.argmax(scores))
    delay = float(GRID[best])
    if 0 < best < len(GRID) - 1:
        selected = np.log(np.maximum(scores[best - 1 : best + 2], np.finfo(float).tiny))
        denominator = selected[0] - 2 * selected[1] + selected[2]
        if math.isfinite(float(denominator)) and abs(denominator) > np.finfo(float).eps:
            fraction = np.clip(0.5 * (selected[0] - selected[2]) / denominator, -0.5, 0.5)
            delay += float(fraction / 64.0)
    return delay, complex(correlations[best]), best in (0, len(GRID) - 1)


def timing_metrics(global_samples: np.ndarray, rate: float) -> dict:
    period = rate / FRAME_RATE_HZ
    times = global_samples / rate
    phases = global_samples % period
    reference = float(np.median(phases))
    residual_s = circular(phases, reference, period) / rate
    _slope, intercept, _sigma, all_residual = huber_line(times, residual_s)
    center_phase = (reference + intercept * rate) % period
    split_centers = []
    crossfit_rms = []
    indexes = np.arange(len(times))
    for parity in (0, 1):
        training = indexes % 2 == parity
        evaluation = ~training
        slope, fitted_intercept, _sigma, _ = huber_line(times[training], residual_s[training])
        predicted = fitted_intercept + slope * (times[evaluation] - np.mean(times[training]))
        # Re-express around the training-time center used internally by huber_line.
        actual = residual_s[evaluation]
        crossfit_rms.append(float(np.sqrt(np.mean((actual - predicted) ** 2))))
        split_centers.append((reference + fitted_intercept * rate) % period)
    split_difference_s = circular(
        np.asarray([split_centers[0]]), split_centers[1], period
    )[0] / rate
    return {
        "center_phase_samples": float(center_phase),
        "frame_residual_mad_ns": float(
            np.median(np.abs(all_residual - np.median(all_residual))) * 1e9
        ),
        "split_even_odd_difference_ns": float(split_difference_s * 1e9),
        "crossfit_frame_rms_ns": float(np.sqrt(np.mean(np.square(crossfit_rms))) * 1e9),
    }


def phase_cfo(global_samples: np.ndarray, phases: np.ndarray, rate: float, coarse_hz: float):
    times = global_samples / rate
    unwrapped = np.unwrap(phases) / (2 * np.pi)
    slope, _intercept, sigma, residual = huber_line(times, unwrapped)
    return {
        "wide_base_cfo_hz": coarse_hz + slope,
        "wide_slope_sigma_hz": sigma,
        "wide_phase_residual_rms_cycles": float(np.sqrt(np.mean(residual**2))),
    }


def synthetic_validation() -> dict:
    templates = fractional_template_bank(
        10_000_000.0,
        114_882_812.5,
        -200_000.0,
        10_000_000.0,
    )
    indexes = (8, 20, 35, 48, 65, 80, 90)
    rng = np.random.default_rng(20260925)
    errors = []
    for index in indexes:
        noise = (
            rng.normal(size=templates.shape[1])
            + 1j * rng.normal(size=templates.shape[1])
        ) * 0.03
        observed = np.asarray(templates[index] + noise, dtype=np.complex64)
        estimated, _correlation, edge = refine_frame(observed, 0, templates)
        if edge:
            raise ValueError("synthetic fractional validation reached the grid boundary")
        errors.append(estimated - float(GRID[index]))
    return {
        "case_count": len(indexes),
        "complex_noise_sigma_relative_to_unit_template": 0.03,
        "maximum_absolute_error_samples": float(np.max(np.abs(errors))),
        "maximum_absolute_error_ns_at_10msps": float(np.max(np.abs(errors)) * 100.0),
    }


def main() -> None:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    prior = json.loads((args.input / "summary.json").read_text())
    source_rows = list(csv.DictReader((args.input / "paired-track-points.csv").open()))
    by_track = {
        result["rank"]: [
            row for row in source_rows if int(row["track_rank"]) == result["rank"]
        ]
        for result in prior["results"]
        if result["pss"]["reconstructed"]
    }

    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    session = store.inspect(SESSION_ID)
    receipt = session.manifest.receipt
    geometry = receipt.plan.geometry
    ordinal_by_visit = {
        retained.event.visit_index: ordinal for ordinal, retained in enumerate(receipt.visits)
    }
    output_rows = []
    with store.reader(SESSION_ID, expected=session) as reader:
        for rank, rows in sorted(by_track.items()):
            rows.sort(key=lambda item: float(item["time_s"]))
            for index, row in enumerate(rows, start=1):
                visit_index = int(row["visit_index"])
                receiver = int(row["receiver_id"])
                coarse = float(row["pss_coarse_cfo_hz"])
                retained, raw = reader.read_visit_ci16(ordinal_by_visit[visit_index])
                event = retained.event
                band = capture_band(event, geometry)
                samples = iq_from_raw(raw, receiver)
                search = acquire_pss_band(
                    samples,
                    band,
                    device_sample_start=(
                        event.valid_start_counter - receipt.terminal.first_counter
                    ),
                    continuity_segment_index=ordinal_by_visit[visit_index],
                    frequency_offsets_hz=(coarse,),
                )
                matches = []
                for hypothesis in search.hypotheses:
                    for candidate in hypothesis.qualified_candidates:
                        if mode_id(visit_index, receiver, coarse, candidate) == row["pss_mode_id"]:
                            windows = tuple(
                                item
                                for item in hypothesis.windows
                                if item.candidate_index == candidate.candidate_index
                            )
                            matches.append((candidate, windows))
                if len(matches) != 1:
                    raise ValueError(f"could not reproduce PSS mode {row['pss_mode_id']}")
                candidate, windows = matches[0]
                strong = tuple(item for item in windows if item.peak_to_local_median >= 1.20)
                chosen = strong or windows
                current_global = np.asarray(
                    [item.fractional_global_device_sample for item in chosen], dtype=float
                )
                visit_row = {
                    "track_rank": rank,
                    "visit_index": visit_index,
                    "time_s": float(row["time_s"]),
                    "glrt_cfo_hz": float(row["glrt_cfo_hz"]),
                    "prior_pss_cfo_hz": float(row["pss_unwrapped_cfo_hz"]),
                    "frame_count": len(chosen),
                    **{f"current_{key}": value for key, value in timing_metrics(
                        current_global, geometry.sample_rate_hz
                    ).items()},
                }
                for bandwidth in BANDWIDTHS_HZ:
                    templates = fractional_template_bank(
                        geometry.sample_rate_hz,
                        band.center_offset_hz,
                        coarse,
                        bandwidth,
                    )
                    global_values = []
                    phases = []
                    edge_hits = 0
                    for item in chosen:
                        delay, correlation, edge_hit = refine_frame(
                            samples, item.measured_local_sample, templates
                        )
                        global_sample = item.global_device_sample + delay
                        global_values.append(global_sample)
                        edge_hits += edge_hit
                        absolute_phase = correlation * np.exp(
                            -2j * np.pi * coarse * item.global_device_sample
                            / geometry.sample_rate_hz
                        )
                        phases.append(float(np.angle(absolute_phase)))
                    label = f"wide_{bandwidth / 1e6:g}mhz"
                    metrics = timing_metrics(
                        np.asarray(global_values), geometry.sample_rate_hz
                    )
                    visit_row.update({f"{label}_{key}": value for key, value in metrics.items()})
                    visit_row[f"{label}_grid_edge_count"] = edge_hits
                    if bandwidth == BANDWIDTHS_HZ[-1]:
                        visit_row.update(
                            phase_cfo(
                                np.asarray(global_values),
                                np.asarray(phases),
                                geometry.sample_rate_hz,
                                coarse,
                            )
                        )
                output_rows.append(visit_row)
                print(f"track {rank} wideband {index}/{len(rows)}", flush=True)
    store.close()

    methods = ["current", "wide_2.5mhz", "wide_5mhz", "wide_10mhz"]
    timing_summary = {}
    for method in methods:
        split = np.asarray(
            [row[f"{method}_split_even_odd_difference_ns"] for row in output_rows]
        )
        crossfit = np.asarray([row[f"{method}_crossfit_frame_rms_ns"] for row in output_rows])
        residual = np.asarray([row[f"{method}_frame_residual_mad_ns"] for row in output_rows])
        timing_summary[method] = {
            "visit_count": len(output_rows),
            "split_median_absolute_ns": float(np.median(np.abs(split))),
            "split_rms_ns": float(np.sqrt(np.mean(split**2))),
            "crossfit_frame_rms_median_ns": float(np.median(crossfit)),
            "frame_residual_mad_median_ns": float(np.median(residual)),
        }
        if method.startswith("wide_"):
            edge_count = sum(
                int(row[f"{method}_grid_edge_count"]) for row in output_rows
            )
            frame_count = sum(int(row["frame_count"]) for row in output_rows)
            edge_fraction = edge_count / frame_count
            timing_summary[method].update(
                {
                    "fractional_grid_edge_count": edge_count,
                    "fractional_grid_edge_fraction": edge_fraction,
                    "search_interior_qualified": edge_fraction <= 0.001,
                }
            )
    current_split = timing_summary["current"]["split_median_absolute_ns"]
    for method in methods[1:]:
        timing_summary[method]["split_median_absolute_improvement_fraction"] = float(
            1.0 - timing_summary[method]["split_median_absolute_ns"] / current_split
        )
    current_split_values = np.abs(
        np.asarray(
            [row["current_split_even_odd_difference_ns"] for row in output_rows]
        )
    )
    wide_split_values = np.abs(
        np.asarray(
            [row["wide_10mhz_split_even_odd_difference_ns"] for row in output_rows]
        )
    )
    current_crossfit_values = np.asarray(
        [row["current_crossfit_frame_rms_ns"] for row in output_rows]
    )
    wide_crossfit_values = np.asarray(
        [row["wide_10mhz_crossfit_frame_rms_ns"] for row in output_rows]
    )
    rng = np.random.default_rng(250925)
    bootstrap_indexes = rng.integers(0, len(output_rows), (10_000, len(output_rows)))

    def median_difference_interval(left: np.ndarray, right: np.ndarray) -> list[float]:
        differences = np.median(right[bootstrap_indexes], axis=1) - np.median(
            left[bootstrap_indexes], axis=1
        )
        return np.quantile(differences, [0.025, 0.975]).tolist()

    full_band_comparison = {
        "split_median_difference_wide_minus_current_ns": float(
            np.median(wide_split_values) - np.median(current_split_values)
        ),
        "split_median_difference_bootstrap_95_ns": median_difference_interval(
            current_split_values, wide_split_values
        ),
        "split_visits_improved": int(np.count_nonzero(wide_split_values < current_split_values)),
        "crossfit_median_difference_wide_minus_current_ns": float(
            np.median(wide_crossfit_values) - np.median(current_crossfit_values)
        ),
        "crossfit_median_difference_bootstrap_95_ns": median_difference_interval(
            current_crossfit_values, wide_crossfit_values
        ),
        "crossfit_visits_improved": int(
            np.count_nonzero(wide_crossfit_values < current_crossfit_values)
        ),
        "visit_count": len(output_rows),
    }

    carrier_results = []
    for rank, _rows in sorted(by_track.items()):
        rows = sorted(
            [row for row in output_rows if row["track_rank"] == rank],
            key=lambda item: item["time_s"],
        )
        times = np.asarray([row["time_s"] for row in rows])
        prior_cfo = np.asarray([row["prior_pss_cfo_hz"] for row in rows])
        prior_rate, prior_center, _sigma, _ = huber_line(times, prior_cfo)
        predicted = prior_center + prior_rate * (times - np.mean(times))
        wide_base = np.asarray([row["wide_base_cfo_hz"] for row in rows])
        wide = wide_base + np.round((predicted - wide_base) / FRAME_RATE_HZ) * FRAME_RATE_HZ
        glrt = np.asarray([row["glrt_cfo_hz"] for row in rows])
        alignment = float(np.median(glrt - wide))
        error = wide + alignment - glrt
        wide_rate, _center, wide_sigma, _ = huber_line(times, wide)
        glrt_rate, _center, _sigma, _ = huber_line(times, glrt)
        carrier_results.append(
            {
                "track_rank": rank,
                "visit_count": len(rows),
                "wide_cfo_median_absolute_error_hz": float(np.median(np.abs(error))),
                "wide_cfo_rmse_hz": float(np.sqrt(np.mean(error**2))),
                "wide_huber_rate_hz_s": wide_rate,
                "wide_rate_sigma_hz_s": wide_sigma,
                "glrt_huber_rate_hz_s": glrt_rate,
                "wide_minus_glrt_rate_hz_s": wide_rate - glrt_rate,
            }
        )

    summary = {
        "schema_version": "org.leo.research.pss-wideband-fractional-alignment/v1",
        "source": {
            "session_id": SESSION_ID,
            "capture_manifest_sha256": session.manifest_sha256,
            "input_summary_sha256": "sha256:"
            + hashlib.sha256((args.input / "summary.json").read_bytes()).hexdigest(),
        },
        "method": {
            "recorded_bandwidth_hz": geometry.sample_rate_hz,
            "native_pss_bandwidth_hz": PSS_NATIVE_SAMPLE_RATE_HZ,
            "fractional_grid_samples": GRID.tolist(),
            "template": (
                "published finite PSS projected by spectral quadrature and evaluated at exact "
                "fractional delays; fine log-parabola interpolation on a 1/64-sample grid"
            ),
            "validation": (
                "even/odd PSS frames are fit independently and alternately used for "
                "time-blocked prediction; identical frozen PSS modes and strong-frame gate"
            ),
            "claim_boundary": (
                "full recorded 10 MHz only, not the missing parts of the native 240 MHz PSS; "
                "template-relative timing without calibrated analogue response"
            ),
        },
        "timing": timing_summary,
        "exact_full_band_vs_current": full_band_comparison,
        "synthetic_validation": synthetic_validation(),
        "carrier": carrier_results,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fields = sorted({key for row in output_rows for key in row})
    with (args.output / "visit-metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    labels = ["Current\n3-point", "Exact-grid\n10 MHz"]
    compared_methods = ["current", "wide_10mhz"]
    split = [timing_summary[item]["split_median_absolute_ns"] for item in compared_methods]
    held = [timing_summary[item]["crossfit_frame_rms_median_ns"] for item in compared_methods]
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.7))
    axes[0].bar(labels, split, color=["#777777", "#08519c"])
    axes[0].set_title("Independent even/odd timing locks", loc="left")
    axes[0].set_ylabel("median absolute difference (ns)")
    axes[1].bar(labels, held, color=["#777777", "#006d2c"])
    axes[1].set_title("Held-frame timing prediction", loc="left")
    axes[1].set_ylabel("median cross-fit RMS (ns)")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("PSS fractional alignment versus used recorded bandwidth · 134 visits")
    figure.tight_layout()
    figure.savefig(args.output / "pss-wideband-fractional-alignment.png", dpi=180)
    plt.close(figure)
    print(json.dumps(summary["timing"], indent=2), flush=True)


if __name__ == "__main__":
    main()
