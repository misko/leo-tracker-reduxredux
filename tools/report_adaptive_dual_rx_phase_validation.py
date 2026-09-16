#!/usr/bin/env python3
"""Validate the updated adaptive dual-RX phase estimator and plot its replay."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink.adaptive_dual_rx_phase import (  # noqa: E402
    coherent_pilot_frames,
    fit_linear_phasor,
    pilot_symbol_reference_offsets_s,
    restore_receiver_relative_phase,
)
from leo.analysis.starlink.templates import (  # noqa: E402
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)

RATE = 2_500_000.0
SYMBOLS = np.arange(2, 66)


def load_report_tool() -> ModuleType:
    path = Path(__file__).with_name("report_adaptive_dual_rx_phase.py")
    spec = importlib.util.spec_from_file_location("adaptive_phase_report", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_documents(path: Path) -> list[dict[str, Any]]:
    files = sorted(path.glob("scan-hop-*-adaptive-double-difference.json"))
    if len(files) != 5:
        raise ValueError(f"expected five replay documents in {path}, found {len(files)}")
    return [json.loads(file.read_text()) for file in files]


def legacy_coherent_frames(
    correlations: np.ndarray,
) -> tuple[np.ndarray, float]:
    size = 512
    spectrum = np.fft.fft(correlations, n=size, axis=1)
    power = np.sum(abs(spectrum) ** 2, axis=0)
    residual_hz = float(np.fft.fftfreq(size, d=OFDM_SYMBOL_DURATION_S)[int(np.argmax(power))])
    lags_s = np.arange(correlations.shape[1]) * OFDM_SYMBOL_DURATION_S
    frames = np.sum(
        correlations * np.exp(-2j * np.pi * residual_hz * lags_s)[None, :],
        axis=1,
    )
    return frames, residual_hz


def synthetic_correlations(
    template: np.ndarray,
    starts: np.ndarray,
    reference_sample: int,
    residual_hz: float,
    receiver_phase_rad: float,
    common_phase_rad: np.ndarray,
) -> np.ndarray:
    begins = np.rint(SYMBOLS * RATE * OFDM_SYMBOL_DURATION_S).astype(int)
    ends = np.minimum(
        np.rint((SYMBOLS + 1) * RATE * OFDM_SYMBOL_DURATION_S).astype(int),
        len(template),
    )
    rows = np.empty((len(starts), len(SYMBOLS)), dtype=np.complex128)
    for frame_index, start in enumerate(starts):
        for symbol_index, (begin, end) in enumerate(zip(begins, ends, strict=True)):
            local = np.arange(begin, end)
            phase = (
                common_phase_rad[frame_index]
                + receiver_phase_rad
                + 2 * np.pi * residual_hz * (start + local - reference_sample) / RATE
            )
            rows[frame_index, symbol_index] = np.sum(abs(template[local]) ** 2 * np.exp(1j * phase))
    return rows


def synthetic_reference_sweep() -> dict[str, Any]:
    template = np.asarray(qin_edge_pilot_frame(RATE, "lower"), np.complex128)
    offsets_s = pilot_symbol_reference_offsets_s(RATE, OFDM_SYMBOL_DURATION_S, SYMBOLS, template)
    starts = np.asarray([5_000 + round(index * RATE / FRAME_RATE_HZ) for index in range(9)])
    frame_times_s = starts / RATE
    center_sample = float(np.mean(starts))
    center_s = center_sample / RATE
    references = (4_713, 4_719)
    receiver_phase_rad = (-0.41, 0.83)
    common_phase_rad = np.asarray([0.2, -1.3, 2.1, 0.7, -2.4, 1.2, 2.8, -0.6, 1.7])
    residual0_hz = 83.25
    residual1_values_hz = np.linspace(-900, 900, 73)
    actual_hz = (-80_321.25, -700_456.75)
    errors: dict[str, list[float]] = {"legacy": [], "updated": []}
    for residual1_hz in residual1_values_hz:
        residuals = (residual0_hz, float(residual1_hz))
        acquired_hz = tuple(
            actual - residual for actual, residual in zip(actual_hz, residuals, strict=True)
        )
        correlations = [
            synthetic_correlations(
                template,
                starts,
                references[receiver],
                residuals[receiver],
                receiver_phase_rad[receiver],
                common_phase_rad,
            )
            for receiver in (0, 1)
        ]
        legacy_frames = [legacy_coherent_frames(row)[0] for row in correlations]
        updated_frames = [
            coherent_pilot_frames(
                row,
                np.zeros_like(row),
                offsets_s,
                OFDM_SYMBOL_DURATION_S,
            )[0]
            for row in correlations
        ]
        expected = (
            receiver_phase_rad[1]
            - receiver_phase_rad[0]
            + 2
            * np.pi
            * (
                actual_hz[1] * (center_sample - references[1])
                - actual_hz[0] * (center_sample - references[0])
            )
            / RATE
        )
        for label, frames in (("legacy", legacy_frames), ("updated", updated_frames)):
            product = frames[1] * np.conj(frames[0])
            _, phase_rad, _ = fit_linear_phasor(
                product, frame_times_s, np.ones(len(starts)), center_s
            )
            restored = restore_receiver_relative_phase(
                phase_rad,
                acquired_hz,
                center_sample,
                references,
                RATE,
            )
            error_deg = np.degrees(np.angle(np.exp(1j * (restored - expected))))
            errors[label].append(float(error_deg))
    return {
        "receiver_0_residual_hz": residual0_hz,
        "receiver_1_residual_hz": residual1_values_hz.tolist(),
        "legacy_error_deg": errors["legacy"],
        "updated_error_deg": errors["updated"],
        "legacy_max_abs_error_deg": float(np.max(abs(np.asarray(errors["legacy"])))),
        "updated_max_abs_error_deg": float(np.max(abs(np.asarray(errors["updated"])))),
    }


def hypothesis_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    frequencies = sorted(float(value) for value in row["signal_frequencies_hz"])
    return (
        int(row["visit_index"]),
        int(row["target_index"]),
        round(frequencies[0]),
        round(frequencies[1]),
    )


def matched_window_metrics(window_documents: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    by_radius: dict[int, dict[tuple[str, tuple[int, int, int, int]], dict[str, Any]]] = {}
    counts: dict[int, dict[str, int]] = {}
    for radius, documents in window_documents.items():
        by_radius[radius] = {
            (document["session_id"], hypothesis_key(row)): row
            for document in documents
            for row in document["hypotheses"]
        }
        counts[radius] = {
            "qualified": sum(
                int(document["qualified_double_difference_visits"]) for document in documents
            ),
            "attempted": sum(int(document["attempted_two_pair_visits"]) for document in documents),
        }
    baseline = by_radius[min(by_radius)]
    comparisons = {}
    for radius in sorted(by_radius):
        if radius == min(by_radius):
            continue
        common = sorted(baseline.keys() & by_radius[radius].keys())
        raw_differences = []
        differences = []
        for key in common:
            reference = baseline[key]
            comparison = by_radius[radius][key]
            raw_delta_deg = comparison["double_difference_deg"] - reference["double_difference_deg"]
            propagated_deg = comparison["double_difference_deg"] + 360 * comparison[
                "double_relative_frequency_hz"
            ] * (reference["common_stored_time_s"] - comparison["common_stored_time_s"])
            propagated_delta_deg = propagated_deg - reference["double_difference_deg"]
            raw_differences.append(
                float(np.degrees(np.angle(np.exp(1j * np.radians(raw_delta_deg)))))
            )
            differences.append(
                float(np.degrees(np.angle(np.exp(1j * np.radians(propagated_delta_deg)))))
            )
        comparisons[str(radius)] = {
            "matched_hypotheses": len(common),
            "median_abs_phase_shift_deg": float(np.median(abs(np.asarray(differences))))
            if differences
            else None,
            "rms_phase_shift_deg": float(np.sqrt(np.mean(np.asarray(differences) ** 2)))
            if differences
            else None,
            "p90_abs_phase_shift_deg": float(np.percentile(abs(np.asarray(differences)), 90))
            if differences
            else None,
            "within_20_deg_fraction": float(np.mean(abs(np.asarray(differences)) <= 20))
            if differences
            else None,
            "phase_shifts_deg": differences,
            "raw_different_epoch_phase_shifts_deg": raw_differences,
        }
    return {
        "coverage": {str(key): value for key, value in counts.items()},
        "comparisons_to_radius_9": comparisons,
    }


def best_track(summary: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    choices = [
        (metric, states)
        for session in summary
        for metric, states in zip(session["tracks"], session["track_states"], strict=True)
    ]
    return max(choices, key=lambda pair: (pair[0]["count"], pair[0]["increment_concentration"]))


def plot_synthetic(result: dict[str, Any], output: Path) -> None:
    x = np.asarray(result["receiver_1_residual_hz"]) - result["receiver_0_residual_hz"]
    figure, axis = plt.subplots(figsize=(10, 5), layout="constrained")
    axis.plot(x, result["legacy_error_deg"], label="Legacy symbol-zero reference", alpha=0.85)
    axis.plot(x, result["updated_error_deg"], label="Actual sampled-symbol reference", linewidth=2)
    axis.axhline(0, color="0.25", linewidth=0.8)
    axis.set(
        xlabel="Injected RX1−RX0 residual frequency (Hz)",
        ylabel="Recovered phase error (degrees)",
        title="Synthetic phase-reference invariance through the coherent pilot estimator",
    )
    axis.grid(alpha=0.25)
    axis.legend()
    figure.savefig(output, dpi=190)
    plt.close(figure)


def plot_historical_comparison(
    legacy_documents: list[dict[str, Any]],
    legacy_summary: list[dict[str, Any]],
    updated_documents: list[dict[str, Any]],
    updated_summary: list[dict[str, Any]],
    output: Path,
) -> None:
    sessions = sorted(document["session_id"] for document in updated_documents)
    old_docs = {row["session_id"]: row for row in legacy_documents}
    new_docs = {row["session_id"]: row for row in updated_documents}
    labels = [session[-4:] for session in sessions]
    old_fraction = [
        100
        * old_docs[s]["qualified_double_difference_visits"]
        / old_docs[s]["attempted_two_pair_visits"]
        for s in sessions
    ]
    new_fraction = [
        100
        * new_docs[s]["qualified_double_difference_visits"]
        / new_docs[s]["attempted_two_pair_visits"]
        for s in sessions
    ]
    old_metric, old_states = best_track(legacy_summary)
    new_metric, new_states = best_track(updated_summary)
    figure, axes = plt.subplots(2, 1, figsize=(11, 9), layout="constrained")
    positions = np.arange(len(sessions))
    width = 0.38
    axes[0].bar(positions - width / 2, old_fraction, width, label="Legacy", alpha=0.75)
    axes[0].bar(positions + width / 2, new_fraction, width, label="Updated", alpha=0.85)
    axes[0].set(
        xticks=positions,
        xticklabels=labels,
        ylabel="Qualified visits (%)",
        title="All-five replay coverage",
    )
    axes[0].grid(axis="y", alpha=0.2)
    axes[0].legend()
    for states, label, marker in (
        (old_states, "Legacy best path", "o"),
        (new_states, "Updated best path", "s"),
    ):
        time_s = np.asarray([row["time_s"] for row in states])
        phase_deg = np.degrees(np.unwrap(np.radians([row["phase_deg"] for row in states])))
        phase_deg -= phase_deg[0]
        axes[1].plot(time_s - time_s[0], phase_deg, marker=marker, label=label)
    axes[1].set(
        xlabel="Time from path start (s)",
        ylabel="Unwrapped phase relative to first point (degrees)",
        title="Strongest phase-blind path",
    )
    axes[1].grid(alpha=0.2)
    axes[1].legend()
    count = new_metric["count"]
    concentration = new_metric["increment_concentration"]
    rms_deg = new_metric["linear_residual_rms_deg"]
    figure.suptitle(f"Updated best: {count} visits, R={concentration:.3f}, RMS={rms_deg:.2f}°")
    figure.savefig(output, dpi=190)
    plt.close(figure)


def plot_window_metrics(result: dict[str, Any], output: Path) -> None:
    radii = sorted(int(key) for key in result["coverage"])
    coverage = [
        100
        * result["coverage"][str(radius)]["qualified"]
        / result["coverage"][str(radius)]["attempted"]
        for radius in radii
    ]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    axes[0].plot(radii, coverage, marker="o")
    axes[0].set(
        xlabel="Frame radius", ylabel="Qualified two-signal visits (%)", title="Replay coverage"
    )
    axes[0].grid(alpha=0.2)
    box_values = [
        result["comparisons_to_radius_9"][str(radius)]["phase_shifts_deg"] for radius in radii[1:]
    ]
    axes[1].boxplot(box_values, tick_labels=[str(radius) for radius in radii[1:]], showfliers=True)
    axes[1].axhline(0, color="0.25", linewidth=0.8)
    axes[1].set(
        xlabel="Frame radius compared with radius 9",
        ylabel="Common-epoch phase shift (degrees)",
        title="Same-visit phase stability after within-dwell propagation",
    )
    axes[1].grid(axis="y", alpha=0.2)
    figure.savefig(output, dpi=190)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-dir", type=Path, required=True)
    parser.add_argument("--updated-dir", type=Path, required=True)
    parser.add_argument("--window", action="append", required=True, help="RADIUS=PATH")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_tool = load_report_tool()
    legacy_documents = load_documents(args.legacy_dir)
    updated_documents = load_documents(args.updated_dir)
    legacy_summary = report_tool.summarize_documents(legacy_documents)
    updated_summary = report_tool.summarize_documents(updated_documents)
    windows = {}
    for item in args.window:
        radius, path = item.split("=", 1)
        windows[int(radius)] = load_documents(Path(path))
    synthetic = synthetic_reference_sweep()
    window_metrics = matched_window_metrics(windows)
    old_metric, _ = best_track(legacy_summary)
    new_metric, _ = best_track(updated_summary)
    result = {
        "synthetic_reference_sweep": synthetic,
        "matched_window_analysis": window_metrics,
        "legacy_best_track": old_metric,
        "updated_best_track": new_metric,
        "updated_summary": updated_summary,
    }
    (args.output_dir / "adaptive-phase-validation-summary.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    plot_synthetic(synthetic, args.output_dir / "synthetic-phase-reference-validation.png")
    plot_historical_comparison(
        legacy_documents,
        legacy_summary,
        updated_documents,
        updated_summary,
        args.output_dir / "updated-historical-replay.png",
    )
    plot_window_metrics(window_metrics, args.output_dir / "matched-window-phase-stability.png")


if __name__ == "__main__":
    main()
