#!/usr/bin/env python3
"""Compare production point-first de-aliasing with seeded alias-aware EM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from leo.analysis.research.seeded_alias_em import (
    SeededAliasObservation,
    SeedTrajectory,
    fit_seeded_alias_em,
)
from leo.contracts.digests import canonical_digest

_ALIAS_SPACING_HZ = 2_500_000 / 11
_COLORS = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--path",
        action="append",
        nargs=4,
        metavar=("LABEL", "PILOT_SCAN_JSON", "TRAJECTORY_BANK_JSON", "DEALIASED_JSON"),
        required=True,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-margin", type=float, default=0.05)
    parser.add_argument("--y-limit-khz", type=float, default=550.0)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    path_results = []
    for label, pilot_path, bank_path, dealiased_path in args.path:
        result = evaluate_path(
            label,
            Path(pilot_path),
            Path(bank_path),
            Path(dealiased_path),
            minimum_margin=args.minimum_margin,
        )
        path_results.append(result)
        _render_path_comparison(
            args.session_id,
            result,
            args.output_dir / f"{_slug(label)}-before-vs-after.png",
            y_limit_khz=args.y_limit_khz,
        )
        _render_after(
            args.session_id,
            result,
            args.output_dir / f"{_slug(label)}-seeded-alias-em.png",
            y_limit_khz=args.y_limit_khz,
        )
    _render_all_paths(
        args.session_id,
        path_results,
        args.output_dir / "all-paths-before-vs-seeded-alias-em.png",
        y_limit_khz=args.y_limit_khz,
    )
    metrics = {
        "schema_version": 1,
        "algorithm": "seed-preserving-alias-hard-em-prototype-v1",
        "session_id": args.session_id,
        "alias_spacing_hz": _ALIAS_SPACING_HZ,
        "paths": [_metrics(item) for item in path_results],
        "limitations": [
            "offline research prototype; no production/catalog products were changed",
            "trajectory membership is inherited from the first hard-EM bank",
            "one member candidate per probe and its integer alias are re-estimated",
            "seed identities are preserved; cross-seed merge, split, and birth are not attempted",
            "candidate-only evidence; no payload or satellite specificity is claimed",
        ],
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, sort_keys=True))


def evaluate_path(
    label: str,
    pilot_path: Path,
    bank_path: Path,
    dealiased_path: Path,
    *,
    minimum_margin: float,
) -> dict[str, Any]:
    pilot = _read_json(pilot_path)
    bank = _read_json(bank_path)
    dealiased = _read_json(dealiased_path)
    if pilot.get("schema_version") != 3 or bank.get("schema_version") != 2:
        raise ValueError("prototype requires pilot scan v3 and trajectory bank v2")
    if dealiased.get("schema_version") != 2:
        raise ValueError("prototype requires the production de-aliased bank v2 comparison")
    observations, display_points = _pilot_observations(pilot, minimum_margin=minimum_margin)
    seeds = tuple(_seed(item) for item in bank["replayed_representatives"])
    fits = tuple(
        fit_seeded_alias_em(
            observations,
            seed,
            alias_spacing_hz=_ALIAS_SPACING_HZ,
        )
        for seed in seeds
    )
    return {
        "label": label,
        "display_points": display_points,
        "seeds": seeds,
        "fits": fits,
        "dealiased": dealiased,
    }


def _pilot_observations(
    document: dict[str, Any], *, minimum_margin: float
) -> tuple[tuple[SeededAliasObservation, ...], tuple[tuple[float, float, float], ...]]:
    observations = []
    display = []
    for detection in document["detections"]:
        sample_start = int(detection["sample_start"])
        time_s = float(detection["time_s"])
        for candidate in detection["candidates"]:
            rank = int(candidate["rank"])
            score = next(
                (item for item in candidate["scores"] if item["method"] == "glrt64"),
                None,
            )
            if score is None:
                continue
            margin = float(score["margin"])
            cfo_hz = float(score["tracking_cfo_hz"])
            observation_id = canonical_digest(
                {
                    "sample_start": sample_start,
                    "candidate_rank": rank,
                    "method": "glrt64",
                }
            )
            observations.append(
                SeededAliasObservation(
                    observation_id=observation_id,
                    sample_start=sample_start,
                    time_s=time_s,
                    raw_cfo_hz=cfo_hz,
                    weight=max(margin, 0.0) + 1e-3,
                )
            )
            if margin >= minimum_margin:
                display.append((time_s, cfo_hz, margin))
    return tuple(observations), tuple(display)


def _seed(row: dict[str, Any]) -> SeedTrajectory:
    return SeedTrajectory(
        trajectory_id=str(row["trajectory_id"]),
        polynomial_degree=int(row["polynomial_degree"]),
        reference_time_s=float(row["reference_time_s"]),
        coefficients_hz=tuple(float(value) for value in row["coefficients_hz"]),
        start_s=float(row["start_s"]),
        end_s=float(row["end_s"]),
        observation_ids=tuple(str(value) for value in row["observation_ids"]),
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _render_path_comparison(
    session_id: str,
    result: dict[str, Any],
    output: Path,
    *,
    y_limit_khz: float,
) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(18, 14), sharex=True, sharey=True)
    _raw_panel(axes[0], result)
    _production_dealiased_panel(axes[1], result)
    _seeded_panel(axes[2], result)
    axes[0].set_title("Before: first hard-EM polynomial seeds (memberships established)")
    axes[1].set_title("Current production: point-first de-alias/path-cover reconstruction")
    axes[2].set_title("Prototype after: seed-preserving alias hard EM")
    _finish_axes(axes, y_limit_khz)
    fig.suptitle(
        f"{session_id} · {result['label']} · de-alias strategy comparison\n"
        "fixed seed identity · one candidate/alias per probe · candidate-only",
        fontsize=16,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(output, dpi=160)
    plt.close(fig)


def _render_after(
    session_id: str,
    result: dict[str, Any],
    output: Path,
    *,
    y_limit_khz: float,
) -> None:
    fig, axis = plt.subplots(figsize=(18, 7))
    _seeded_panel(axis, result)
    _finish_axes((axis,), y_limit_khz)
    axis.set_title(
        f"{session_id} · {result['label']} · seed-preserving alias hard EM\n"
        "thick curves retain first-EM trajectory identity; points are one selected candidate/probe"
    )
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def _render_all_paths(
    session_id: str,
    results: list[dict[str, Any]],
    output: Path,
    *,
    y_limit_khz: float,
) -> None:
    fig, axes = plt.subplots(
        len(results),
        2,
        figsize=(20, 5 * len(results)),
        sharex=True,
        sharey=True,
    )
    axes = np.atleast_2d(axes)
    for row, result in enumerate(results):
        _raw_panel(axes[row, 0], result)
        _seeded_panel(axes[row, 1], result)
        axes[row, 0].set_title(f"{result['label']} · before hard-EM seeds")
        axes[row, 1].set_title(f"{result['label']} · after seeded alias EM")
    _finish_axes(tuple(axes.flat), y_limit_khz)
    fig.suptitle(
        f"{session_id} · all receiver paths · before versus seeded alias-aware EM",
        fontsize=17,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output, dpi=160)
    plt.close(fig)


def _raw_panel(axis: Any, result: dict[str, Any]) -> None:
    display = result["display_points"]
    if display:
        axis.scatter(
            [item[0] for item in display],
            [item[1] / 1000.0 for item in display],
            s=4,
            color="#a8b6c7",
            alpha=0.28,
            linewidths=0,
            label="GLRT64 candidates margin ≥ 0.05",
        )
    for index, seed in enumerate(result["seeds"]):
        times = np.linspace(seed.start_s, seed.end_s, 256)
        axis.plot(
            times,
            seed.frequency_hz(times) / 1000.0,
            color=_COLORS[index % len(_COLORS)],
            linewidth=2.6,
            label=f"{seed.trajectory_id[7:15]} d{seed.polynomial_degree}",
        )
    axis.legend(loc="upper right", ncol=3, fontsize=7)


def _production_dealiased_panel(axis: Any, result: dict[str, Any]) -> None:
    document = result["dealiased"]
    observations = document["observations"]
    if observations:
        axis.scatter(
            [float(item["time_s"]) for item in observations],
            [float(item["component_cfo_hz"]) / 1000.0 for item in observations],
            s=3,
            color="#a8b6c7",
            alpha=0.22,
            linewidths=0,
        )
    for index, branch in enumerate(document["branches"]):
        model = next(
            item for item in branch["models"] if item["model_id"] == branch["selected_model_id"]
        )
        times = np.linspace(float(branch["start_s"]), float(branch["end_s"]), 64)
        values = np.polyval(model["coefficients_hz"], times - float(model["reference_time_s"]))
        axis.plot(
            times,
            values / 1000.0,
            color=_COLORS[index % len(_COLORS)],
            linewidth=1.5,
            alpha=0.9,
        )
    axis.text(
        0.01,
        0.02,
        (
            f"{document['returned_branch_count']} returned / "
            f"{document['source_branch_count']} source branches"
        ),
        transform=axis.transAxes,
        fontsize=9,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
    )


def _seeded_panel(axis: Any, result: dict[str, Any]) -> None:
    for index, fit in enumerate(result["fits"]):
        color = _COLORS[index % len(_COLORS)]
        axis.scatter(
            [item.time_s for item in fit.points],
            [item.canonical_cfo_hz / 1000.0 for item in fit.points],
            s=5,
            color=color,
            alpha=0.32,
            linewidths=0,
        )
        times = np.linspace(fit.start_s, fit.end_s, 256)
        axis.plot(
            times,
            fit.frequency_hz(times) / 1000.0,
            color=color,
            linewidth=3.0,
            label=(
                f"{fit.seed_trajectory_id[7:15]} d{fit.polynomial_degree} "
                f"n={fit.selected_probe_count} rms={fit.residual_rms_hz:.0f}Hz"
            ),
        )
    axis.legend(loc="upper right", ncol=2, fontsize=7)


def _finish_axes(axes: tuple[Any, ...], y_limit_khz: float) -> None:
    for axis in axes:
        axis.set_xlim(0.0, 60.0)
        axis.set_ylim(-y_limit_khz, y_limit_khz)
        axis.grid(True, alpha=0.2)
        axis.set_ylabel("Baseband CFO (kHz)")
    axes[-1].set_xlabel("Recording time (s)")


def _metrics(result: dict[str, Any]) -> dict[str, Any]:
    document = result["dealiased"]
    return {
        "label": result["label"],
        "input_seed_count": len(result["seeds"]),
        "production_dealiased_source_branch_count": int(document["source_branch_count"]),
        "production_dealiased_returned_branch_count": int(document["returned_branch_count"]),
        "prototype_returned_track_count": len(result["fits"]),
        "prototype_tracks": [
            {
                "seed_trajectory_id": fit.seed_trajectory_id,
                "degree": fit.polynomial_degree,
                "start_s": fit.start_s,
                "end_s": fit.end_s,
                "source_observation_count": fit.source_observation_count,
                "selected_probe_count": fit.selected_probe_count,
                "alias_histogram": {
                    str(alias): sum(point.alias_index == alias for point in fit.points)
                    for alias in sorted({point.alias_index for point in fit.points})
                },
                "residual_rms_hz": fit.residual_rms_hz,
                "maximum_absolute_residual_hz": fit.maximum_absolute_residual_hz,
                "iterations": fit.iterations,
                "converged": fit.converged,
            }
            for fit in result["fits"]
        ],
    }


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip(
        "-"
    )


if __name__ == "__main__":
    main()
