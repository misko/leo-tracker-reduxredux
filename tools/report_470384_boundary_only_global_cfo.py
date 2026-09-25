#!/usr/bin/env python3
"""Fit a global CFO line from raw 1.333 ms frames using only known boundaries."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.templates import FRAME_RATE_HZ
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    import report_470384_direct_frame_cfo as direct_frame
    import report_470384_global_frame_line as frame_line
    import report_470384_semicoherent_recovery as semicoherent
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_direct_frame_cfo as direct_frame
    from tools import report_470384_global_frame_line as frame_line
    from tools import report_470384_semicoherent_recovery as semicoherent


START_S = 33.7
END_S = 37.7
BRANCH_INDEX = 3
FFT_SIZE = 32_768
DEFAULT_PRIOR_RESULTS = Path(
    "reports/figures/2026_08_23_470384_joint_frame_surface/joint-all-frame-cfo-results.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_boundary_only_global_cfo")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_boundary_only_global_cfo.md")

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
RED = "#bd5b52"


@dataclass(frozen=True, slots=True)
class BlindLineFit:
    reference_time_s: float
    frequency_at_reference_hz: float
    slope_hz_s: float
    train_score: float
    validation_exact_score: float
    validation_control_score: float
    validation_exact_control_db: float

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        result = self.frequency_at_reference_hz + self.slope_hz_s * (
            np.asarray(time_s, dtype=float) - self.reference_time_s
        )
        return float(result) if np.ndim(result) == 0 else result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--frame-results", type=Path, default=semicoherent.DEFAULT_FRAME_RESULTS)
    parser.add_argument("--prior-results", type=Path, default=DEFAULT_PRIOR_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--start-s", type=float, default=START_S)
    parser.add_argument("--end-s", type=float, default=END_S)
    parser.add_argument("--fft-size", type=int, default=FFT_SIZE)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def boundary_manifest(source_document: dict[str, Any]) -> dict[str, Any]:
    """Reduce selected evidence to frame starts; retain no per-window measurement."""

    frame_period = semicoherent.SAMPLE_RATE_HZ / FRAME_RATE_HZ
    starts = set()
    for item in source_document["candidate_windows"]:
        if (
            int(item["branch_index"]) != BRANCH_INDEX
            or not START_S <= float(item["detection_time_s"]) < END_S
            or float(item["selection_model_error_hz"]) > semicoherent.MAXIMUM_MODEL_ERROR_HZ
        ):
            continue
        aligned_start = int(item["aligned_sample_start"])
        for frame_index in range(15):
            starts.add(aligned_start + round(frame_index * frame_period))
    return {
        "schema_version": 1,
        "session_id": semicoherent.SESSION_ID,
        "stream_id": "stream-0",
        "receiver_id": 0,
        "sample_rate_hz": semicoherent.SAMPLE_RATE_HZ,
        "frame_start_samples": sorted(starts),
    }


def validate_boundary_manifest(document: dict[str, Any]) -> tuple[int, ...]:
    allowed = {
        "schema_version",
        "session_id",
        "stream_id",
        "receiver_id",
        "sample_rate_hz",
        "frame_start_samples",
    }
    unexpected = set(document) - allowed
    if unexpected:
        raise ValueError(f"boundary manifest contains forbidden metadata: {sorted(unexpected)}")
    starts = tuple(int(value) for value in document["frame_start_samples"])
    if not starts or any(b <= a for a, b in zip(starts[:-1], starts[1:], strict=True)):
        raise ValueError("frame boundaries must be nonempty and strictly increasing")
    return starts


def full_band_likelihoods(
    *,
    bulk_root: Path,
    boundary_document: dict[str, Any],
    fft_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute an absolute-CFO matched-filter spectrum from each raw frame."""

    boundaries = validate_boundary_manifest(boundary_document)
    if fft_size < 4_096 or fft_size & (fft_size - 1):
        raise ValueError("FFT size must be a power of two of at least 4096")
    samples = direct_frame.build_symbol_samples(even=True)
    read_start = boundaries[0]
    read_stop = boundaries[-1] + int(np.max(samples.positions)) + 1
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(semicoherent.SESSION_ID), "stream-0", verify=True)
        raw = reader.read(read_start, read_stop - read_start, receiver_ids=(0,))
        iq = direct_frame._complex_receiver(raw)
    finally:
        if store is not None:
            store.close()
    frequencies = np.fft.fftshift(
        np.fft.fftfreq(fft_size, d=1.0 / semicoherent.SAMPLE_RATE_HZ)
    )
    likelihoods = np.empty((len(boundaries), fft_size), dtype=np.float32)
    independent_scores = np.empty(len(boundaries), dtype=float)
    workspace = np.zeros(fft_size, dtype=np.complex128)
    for index, boundary in enumerate(boundaries):
        offset = boundary - read_start
        received = iq[offset + samples.positions]
        products = np.conj(samples.exact_reference) * received
        denominator = float(
            np.vdot(samples.exact_reference, samples.exact_reference).real
            * np.vdot(received, received).real
        )
        workspace.fill(0.0)
        workspace[samples.positions] = products
        power = np.abs(np.fft.fftshift(np.fft.fft(workspace))) ** 2
        normalized = power / max(denominator, 1e-20)
        likelihoods[index] = normalized.astype(np.float32)
        independent_scores[index] = float(np.max(normalized))
        if (index + 1) % 250 == 0 or index + 1 == len(boundaries):
            print(f"computed full-band frame spectra {index + 1}/{len(boundaries)}", flush=True)
    center_position = float(np.mean(samples.positions))
    times = (np.asarray(boundaries, dtype=float) + center_position) / semicoherent.SAMPLE_RATE_HZ
    return times, frequencies, likelihoods, independent_scores


def score_lines(
    likelihoods: np.ndarray,
    times_s: np.ndarray,
    frequencies_hz: np.ndarray,
    *,
    reference_time_s: float,
    parameters: np.ndarray,
) -> np.ndarray:
    """Score intercept/rate pairs by sampling every boundary-only likelihood."""

    curves = np.asarray(likelihoods, dtype=float)
    times = np.asarray(times_s, dtype=float)
    grid = np.asarray(frequencies_hz, dtype=float)
    candidates = np.asarray(parameters, dtype=float)
    if curves.shape != (len(times), len(grid)) or candidates.ndim != 2 or candidates.shape[1] != 2:
        raise ValueError("line-score inputs have incompatible shapes")
    step = float(grid[1] - grid[0])
    predictions = candidates[:, :1] + candidates[:, 1:] * (times[None, :] - reference_time_s)
    positions = (predictions - grid[0]) / step
    valid = (positions >= 0.0) & (positions <= len(grid) - 1)
    lower = np.clip(np.floor(positions).astype(int), 0, len(grid) - 2)
    fraction = np.clip(positions - lower, 0.0, 1.0)
    frame_rows = np.arange(len(times))[None, :]
    sampled = (
        curves[frame_rows, lower] * (1.0 - fraction)
        + curves[frame_rows, lower + 1] * fraction
    )
    return np.mean(np.where(valid, sampled, 0.0), axis=1)


def fit_blind_global_line(
    likelihoods: np.ndarray,
    times_s: np.ndarray,
    frequencies_hz: np.ndarray,
    *,
    seed: int = 470_384,
    population_size: int = 320,
    generations: int = 120,
) -> tuple[float, float, float]:
    """Search the full receiver band without an external CFO initialization."""

    reference_time_s = float(np.mean(times_s))
    independent = frequencies_hz[np.argmax(likelihoods, axis=1)]
    strongest = np.max(likelihoods, axis=1) >= np.percentile(np.max(likelihoods, axis=1), 50)
    slope_seed, intercept_seed = np.polyfit(
        times_s[strongest] - reference_time_s,
        independent[strongest],
        1,
    )
    frequency_bounds = (float(frequencies_hz[0]), float(frequencies_hz[-1]))
    slope_bounds = (-50_000.0, 50_000.0)
    rng = np.random.default_rng(seed)
    population = np.column_stack(
        (
            rng.uniform(*frequency_bounds, size=population_size),
            rng.uniform(*slope_bounds, size=population_size),
        )
    )
    population[0] = (np.clip(intercept_seed, *frequency_bounds), np.clip(slope_seed, *slope_bounds))
    scores = score_lines(
        likelihoods,
        times_s,
        frequencies_hz,
        reference_time_s=reference_time_s,
        parameters=population,
    )
    for _generation in range(generations):
        a = population[rng.integers(0, population_size, size=population_size)]
        b = population[rng.integers(0, population_size, size=population_size)]
        c = population[rng.integers(0, population_size, size=population_size)]
        mutant = a + 0.82 * (b - c)
        mutant[:, 0] = np.clip(mutant[:, 0], *frequency_bounds)
        mutant[:, 1] = np.clip(mutant[:, 1], *slope_bounds)
        crossover = rng.random((population_size, 2)) < 0.75
        crossover[np.arange(population_size), rng.integers(0, 2, size=population_size)] = True
        trial = np.where(crossover, mutant, population)
        trial_scores = score_lines(
            likelihoods,
            times_s,
            frequencies_hz,
            reference_time_s=reference_time_s,
            parameters=trial,
        )
        improved = trial_scores > scores
        population[improved] = trial[improved]
        scores[improved] = trial_scores[improved]
    best = population[int(np.argmax(scores))].copy()
    best_score = float(np.max(scores))
    for frequency_step, slope_step in ((100.0, 250.0), (25.0, 50.0), (5.0, 10.0), (1.0, 2.0)):
        offsets = np.asarray(
            [
                (frequency_offset, slope_offset)
                for frequency_offset in np.arange(-5, 6) * frequency_step
                for slope_offset in np.arange(-5, 6) * slope_step
            ]
        )
        candidates = best[None, :] + offsets
        scores = score_lines(
            likelihoods,
            times_s,
            frequencies_hz,
            reference_time_s=reference_time_s,
            parameters=candidates,
        )
        position = int(np.argmax(scores))
        best = candidates[position]
        best_score = float(scores[position])
    return float(best[0]), float(best[1]), best_score


def validate_fit(
    *,
    bulk_root: Path,
    boundary_document: dict[str, Any],
    reference_time_s: float,
    frequency_at_reference_hz: float,
    slope_hz_s: float,
) -> tuple[float, float, np.ndarray]:
    boundaries = validate_boundary_manifest(boundary_document)
    samples = direct_frame.build_symbol_samples(even=False)
    read_start = boundaries[0]
    read_stop = boundaries[-1] + int(np.max(samples.positions)) + 1
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(semicoherent.SESSION_ID), "stream-0", verify=True)
        raw = reader.read(read_start, read_stop - read_start, receiver_ids=(0,))
        iq = direct_frame._complex_receiver(raw)
    finally:
        if store is not None:
            store.close()
    center_position = float(np.mean(samples.positions))
    times = (np.asarray(boundaries, dtype=float) + center_position) / semicoherent.SAMPLE_RATE_HZ
    predictions = frequency_at_reference_hz + slope_hz_s * (times - reference_time_s)
    exact_scores = []
    control_scores = []
    for boundary, frequency in zip(boundaries, predictions, strict=True):
        offset = boundary - read_start
        received = iq[offset + samples.positions]
        exact_products = np.conj(samples.exact_reference) * received
        control_products = np.conj(samples.control_reference) * received
        exact_denominator = float(
            np.vdot(samples.exact_reference, samples.exact_reference).real
            * np.vdot(received, received).real
        )
        control_denominator = float(
            np.vdot(samples.control_reference, samples.control_reference).real
            * np.vdot(received, received).real
        )
        exact_scores.append(
            direct_frame._normalized_score(
                exact_products,
                exact_denominator,
                samples.positions,
                float(frequency),
            )
        )
        control_scores.append(
            direct_frame._normalized_score(
                control_products,
                control_denominator,
                samples.positions,
                float(frequency),
            )
        )
    return float(np.mean(exact_scores)), float(np.mean(control_scores)), np.asarray(exact_scores)


def render(
    path: Path,
    *,
    times_s: np.ndarray,
    frequencies_hz: np.ndarray,
    likelihoods: np.ndarray,
    independent_scores: np.ndarray,
    validation_scores: np.ndarray,
    fit: BlindLineFit,
) -> None:
    maxima = frequencies_hz[np.argmax(likelihoods, axis=1)]
    prediction = np.asarray(fit.frequency_hz(times_s))
    strong = validation_scores >= np.percentile(validation_scores, 30)
    figure = Figure(figsize=(18, 13), constrained_layout=True)
    axes = figure.subplots(3, 1, sharex=True, gridspec_kw={"height_ratios": (1, 1.15, 0.85)})
    figure.suptitle(
        "Boundary-only global CFO fit from raw IQ · no 20 ms CFO, score, or grouping",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    axes[0].scatter(
        times_s[~strong],
        maxima[~strong] / 1e3,
        s=7,
        color=GRAY,
        alpha=0.20,
        linewidths=0,
        rasterized=True,
        label="independent full-band frame maximum · weaker 30%",
    )
    axes[0].scatter(
        times_s[strong],
        maxima[strong] / 1e3,
        s=9,
        color=BLUE,
        alpha=0.55,
        linewidths=0,
        rasterized=True,
        label="independent full-band frame maximum · stronger 70%",
    )
    axes[0].plot(
        times_s,
        prediction / 1e3,
        color=AMBER,
        linewidth=2.4,
        label=f"blind global optimum · {fit.slope_hz_s / 1e3:.3f} kHz/s",
    )
    axes[0].legend(loc="lower left", ncol=2)
    residual = maxima - prediction
    central = np.abs(residual) <= 8_000.0
    axes[1].scatter(
        times_s[~central],
        np.clip(residual[~central], -8_000.0, 8_000.0),
        s=6,
        color=GRAY,
        alpha=0.14,
        linewidths=0,
        rasterized=True,
        label=f"full-band maximum outside ±8 kHz ({np.count_nonzero(~central)})",
    )
    axes[1].scatter(
        times_s[central],
        residual[central],
        s=9,
        color=GREEN,
        alpha=0.58,
        linewidths=0,
        rasterized=True,
        label=f"full-band maximum within ±8 kHz ({np.count_nonzero(central)})",
    )
    axes[1].axhline(0.0, color=INK, linewidth=0.8, alpha=0.55)
    axes[1].set_ylim(-8_300.0, 8_300.0)
    axes[1].legend(loc="lower left", ncol=2)
    axes[2].scatter(
        times_s,
        10.0 * np.log10(np.maximum(validation_scores, 1e-20)),
        s=8,
        color=BLUE,
        alpha=0.48,
        linewidths=0,
        rasterized=True,
    )
    titles = (
        "A · Independent frame maxima across the complete receiver band",
        "B · Independent maximum minus the boundary-only global line",
        "C · Held-out odd-symbol Qin score evaluated on the global line",
    )
    ylabels = (
        "absolute CFO (kHz)",
        "frame maximum − line (Hz)",
        "held-out Qin score (dB)",
    )
    for axis, title, ylabel in zip(axes, titles, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_ylabel(ylabel, color=INK)
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, document: dict[str, Any]) -> None:
    figure = os.path.relpath(document["figure"], path.parent)
    fit = document["blind_global_fit"]
    comparison = document["external_comparison"]
    frame_count = document["inventory"]["frame_count"]
    comparison_row = (
        "| difference from prior fit | "
        f"{comparison['frequency_difference_hz']:+.1f} Hz, "
        f"{comparison['slope_difference_hz_s']:+.1f} Hz/s |"
    )
    text = f"""# Boundary-only global CFO optimization from raw IQ

## Input isolation

The optimizer receives raw IQ and {frame_count} absolute 1.333 ms frame-start samples.
Its boundary manifest contains no 20 ms window identifiers, CFOs,
GLRT scores, branch labels, or grouping.  Every frame likelihood spans the
complete ±1.25 MHz receiver band.

![Boundary-only global CFO fit]({figure})

| result | value |
| --- | ---: |
| CFO at {fit['reference_time_s']:.6f} s | {fit['frequency_at_reference_hz']:.1f} Hz |
| global CFO rate | {fit['slope_hz_s'] / 1e3:.3f} kHz/s |
| held-out exact/control | {fit['validation_exact_control_db']:.2f} dB |
{comparison_row}

The earlier fit is loaded only after optimization for the final comparison; it
cannot seed or constrain this result.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    source_document = _load(arguments.frame_results)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    manifest = boundary_manifest(source_document)
    manifest_path = arguments.output_root / "frame-boundaries-only.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    isolated_manifest = _load(manifest_path)
    times, frequencies, likelihoods, independent_scores = full_band_likelihoods(
        bulk_root=arguments.bulk_root,
        boundary_document=isolated_manifest,
        fft_size=arguments.fft_size,
    )
    reference_time_s = float(np.mean(times))
    frequency, slope, train_score = fit_blind_global_line(likelihoods, times, frequencies)
    validation_exact, validation_control, validation_scores = validate_fit(
        bulk_root=arguments.bulk_root,
        boundary_document=isolated_manifest,
        reference_time_s=reference_time_s,
        frequency_at_reference_hz=frequency,
        slope_hz_s=slope,
    )
    fit = BlindLineFit(
        reference_time_s=reference_time_s,
        frequency_at_reference_hz=frequency,
        slope_hz_s=slope,
        train_score=train_score,
        validation_exact_score=validation_exact,
        validation_control_score=validation_control,
        validation_exact_control_db=10.0
        * math.log10(validation_exact / max(validation_control, 1e-20)),
    )
    prior_document = _load(arguments.prior_results)
    prior = frame_line.LinearFit(**prior_document["joint_fit"])
    figure_path = arguments.output_root / "boundary-only-global-cfo.png"
    render(
        figure_path,
        times_s=times,
        frequencies_hz=frequencies,
        likelihoods=likelihoods,
        independent_scores=independent_scores,
        validation_scores=validation_scores,
        fit=fit,
    )
    document = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-boundary-only-full-band-global-cfo-v1",
            "input": {
                "session_id": semicoherent.SESSION_ID,
                "boundary_manifest": str(manifest_path),
                "stream_id": "stream-0",
                "receiver_id": 0,
            },
            "configuration": {
                "fft_size": arguments.fft_size,
                "frequency_search_hz": [
                    float(frequencies[0]),
                    float(frequencies[-1]),
                ],
                "slope_search_hz_s": [-50_000.0, 50_000.0],
                "optimizer_inputs": "raw IQ plus absolute frame-start samples only",
                "train_symbols": "even Qin symbols",
                "validation_symbols": "odd Qin symbols",
                "control": "odd symbols from rolled Qin control",
            },
            "inventory": {
                "frame_count": len(times),
                "boundary_manifest_field_count": len(manifest),
            },
            "blind_global_fit": asdict(fit),
            "external_comparison": {
                "prior_loaded_after_optimization": True,
                "frequency_difference_hz": frequency - prior.frequency_at_reference_hz,
                "slope_difference_hz_s": slope - prior.slope_hz_s,
            },
            "independent_frame_maximum": {
                "median_score": float(np.median(independent_scores)),
                "p10_score": float(np.percentile(independent_scores, 10)),
                "p90_score": float(np.percentile(independent_scores, 90)),
            },
            "figure": str(figure_path),
        }
    )
    results_path = arguments.output_root / "boundary-only-global-cfo-results.json"
    results_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, document)
    print(
        json.dumps(
            {
                "inventory": document["inventory"],
                "blind_global_fit": document["blind_global_fit"],
                "external_comparison": document["external_comparison"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
