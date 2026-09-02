#!/usr/bin/env python3
"""Post-hoc PSS-only association-gate sensitivity for one replay document."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.starlink.pss_search import (
    PssBankMode,
    PssSearchOrigin,
    PssTrackAssociationConfig,
    _best_track_modes,
    _fit_track,
)
from leo.analysis.starlink.pss_timing import PssEpochCandidate


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def lightweight_mode(row: dict[str, Any]) -> PssBankMode:
    return PssBankMode(
        mode_id=row["mode_id"],
        block_index=int(row["block_index"]),
        continuity_segment_index=int(row["continuity_segment_index"]),
        projection_id=row["projection_id"],
        origin=PssSearchOrigin(row["origin"]),
        source_digest=row["source_digest"],
        center_time_s=float(row["center_time_s"]),
        nominal_frequency_offset_hz=float(row["nominal_frequency_offset_hz"]),
        candidate=PssEpochCandidate(**row["candidate"]),
        median_frame_phase_s=float(row["median_frame_phase_s"]),
        window_count=int(row["window_count"]),
        strong_window_count=int(row["strong_window_count"]),
        windows=(),
    )


def evaluate(
    modes: tuple[PssBankMode, ...],
    *,
    label: str,
    phase_radius_us: float,
    cfo_radius_hz: float,
) -> dict[str, Any]:
    config = PssTrackAssociationConfig(
        phase_inlier_radius_s=phase_radius_us * 1e-6,
        maximum_cfo_deviation_hz=cfo_radius_hz,
    )
    selected = _best_track_modes(modes, config)
    result: dict[str, Any] = {
        "label": label,
        "configuration": asdict(config),
        "selected_mode_count": len(selected),
    }
    if not selected:
        return result
    fitted = _fit_track(selected)
    ordered = tuple(sorted(selected, key=lambda item: item.center_time_s))
    times_s = np.asarray([item.center_time_s for item in ordered], dtype=float)
    phases_s = np.asarray([item.median_frame_phase_s for item in ordered], dtype=float)
    period_s = 1.0 / 750.0
    unwrapped_s = np.unwrap(phases_s / period_s * 2.0 * np.pi) * (
        period_s / (2.0 * np.pi)
    )
    fitted_s = np.polyval(
        np.asarray(fitted.coefficients_descending_s, dtype=float),
        times_s - fitted.time_origin_s,
    )
    result.update(
        {
            "time_start_s": fitted.time_start_s,
            "time_stop_s": fitted.time_stop_s,
            "span_s": fitted.time_stop_s - fitted.time_start_s,
            "cfo_min_hz": min(item.nominal_frequency_offset_hz for item in selected),
            "cfo_max_hz": max(item.nominal_frequency_offset_hz for item in selected),
            "robust_z_median": float(
                np.median([item.candidate.robust_z for item in selected])
            ),
            "fit_rms_residual_us": fitted.rms_residual_s * 1e6,
            "fit_maximum_absolute_residual_us": (
                fitted.maximum_absolute_residual_s * 1e6
            ),
            "fit_time_origin_s": fitted.time_origin_s,
            "fit_coefficients_descending_s": list(fitted.coefficients_descending_s),
            "mode_ids": [item.mode_id for item in ordered],
            "times_s": times_s.tolist(),
            "phase_us_modulo_frame": (phases_s * 1e6).tolist(),
            "unwrapped_phase_us": (unwrapped_s * 1e6).tolist(),
            "fitted_unwrapped_phase_us": (fitted_s * 1e6).tolist(),
            "residual_us": [value * 1e6 for value in fitted.residuals_s],
            "would_publish": (
                len(selected) >= config.minimum_block_count
                and fitted.time_stop_s - fitted.time_start_s >= config.minimum_span_s
                and fitted.maximum_absolute_residual_s <= config.phase_inlier_radius_s
            ),
        }
    )
    return result


def render(evidence: dict[str, Any], path: Path) -> None:
    default = evidence["results"][0]
    relaxed = min(
        (result for result in evidence["results"][1:] if result.get("would_publish")),
        key=lambda result: result["fit_rms_residual_us"],
    )
    figure, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True, constrained_layout=True)
    styles = (
        (default, "published-default near miss", "black", "o"),
        (relaxed, f"exploratory {relaxed['label']}", "tab:orange", "s"),
    )
    for result, label, color, marker in styles:
        times_s = np.asarray(result["times_s"], dtype=float)
        phases_us = np.asarray(result["phase_us_modulo_frame"], dtype=float)
        unwrapped_us = np.asarray(result["unwrapped_phase_us"], dtype=float)
        fitted_us = np.asarray(result["fitted_unwrapped_phase_us"], dtype=float)
        residual_us = np.asarray(result["residual_us"], dtype=float)
        axes[0].scatter(times_s, phases_us, s=18, color=color, marker=marker, label=label)
        axes[1].scatter(
            times_s,
            unwrapped_us - unwrapped_us[0],
            s=14,
            color=color,
            marker=marker,
            alpha=0.75,
        )
        axes[1].plot(times_s, fitted_us - unwrapped_us[0], color=color, linewidth=1.2)
        axes[2].scatter(
            times_s,
            residual_us,
            s=18,
            color=color,
            marker=marker,
            label=(
                f"{label}: RMS {result['fit_rms_residual_us']:.3f} µs, "
                f"max {result['fit_maximum_absolute_residual_us']:.3f} µs"
            ),
        )
        radius_us = result["configuration"]["phase_inlier_radius_s"] * 1e6
        axes[2].axhline(radius_us, color=color, linestyle=":", linewidth=0.8, alpha=0.7)
        axes[2].axhline(-radius_us, color=color, linestyle=":", linewidth=0.8, alpha=0.7)
    axes[0].set_ylabel("Frame phase modulo 1/750 s (µs)")
    axes[0].set_title("Selected PSS modes")
    axes[0].legend()
    axes[1].set_ylabel("Relative unwrapped phase (µs)")
    axes[1].set_title("Ordinary quadratic refit")
    axes[2].set_ylabel("Circular fit residual (µs)")
    axes[2].set_xlabel("Seconds from native 25 MS/s first sample")
    axes[2].set_title("Post-refit publication gate (dotted lines)")
    axes[2].legend()
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.suptitle(
        f"{evidence['capture_id']} — post-hoc PSS association sensitivity\n"
        "exploratory only; primary predeclared result remains unchanged"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> None:
    args = arguments()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    modes = tuple(
        lightweight_mode(mode)
        for block in document["blocks"]
        for mode in block["modes"]
    )
    configurations = (
        ("published_default", 2.0, 150_000.0),
        ("phase_4us", 4.0, 150_000.0),
        ("phase_8us", 8.0, 150_000.0),
        ("cfo_300khz", 2.0, 300_000.0),
        ("phase_4us_cfo_300khz", 4.0, 300_000.0),
    )
    evidence = {
        "schema_version": 1,
        "analysis_kind": "post-hoc-pss-only-association-gate-sensitivity",
        "source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__).resolve()),
        },
        "capture_id": document["capture_id"],
        "input": {"path": str(args.input), "sha256": sha256(args.input)},
        "mode_count": len(modes),
        "published_track_count": len(document["tracks"]),
        "interpretation_guard": (
            "exploratory sensitivity only; does not replace the predeclared primary result"
        ),
        "results": [
            evaluate(
                modes,
                label=label,
                phase_radius_us=phase_radius_us,
                cfo_radius_hz=cfo_radius_hz,
            )
            for label, phase_radius_us, cfo_radius_hz in configurations
        ],
    }
    render(evidence, args.figure)
    evidence["figure"] = {"path": str(args.figure), "sha256": sha256(args.figure)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "capture_id": evidence["capture_id"],
                "output": str(args.output),
                "figure": evidence["figure"],
                "results": [
                    {
                        "label": result["label"],
                        "selected_mode_count": result["selected_mode_count"],
                        "would_publish": result.get("would_publish", False),
                        "fit_rms_residual_us": result.get("fit_rms_residual_us"),
                        "fit_maximum_absolute_residual_us": result.get(
                            "fit_maximum_absolute_residual_us"
                        ),
                    }
                    for result in evidence["results"]
                ],
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
