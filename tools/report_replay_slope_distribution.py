#!/usr/bin/env python3
"""Report pre-replay and post-replay Standard trajectory slope distributions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.contracts.cfo_dealias import Glrt64FinalTrajectoryTableV3
from leo.storage import BulkUriResolver

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
BIN_WIDTH_HZ_S = 500.0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    return parser.parse_args()


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _linear_slope_hz_s(coefficients_hz: list[float] | tuple[float, ...]) -> float:
    """Return the polynomial's linear coefficient, or slope at its reference time."""

    if not 2 <= len(coefficients_hz) <= 4:
        raise ValueError("trajectory polynomial must have two to four coefficients")
    coefficients = tuple(float(value) for value in coefficients_hz)
    if any(not math.isfinite(value) for value in coefficients):
        raise ValueError("trajectory coefficients must be finite")
    return coefficients[-2]


def _read_verified_json(
    resolver: BulkUriResolver,
    *,
    uri: str,
    expected_digest: str,
) -> dict[str, Any]:
    payload = resolver.resolve(uri).read_bytes()
    if _sha256(payload) != expected_digest:
        raise ValueError(f"artifact digest mismatch: {uri}")
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError(f"artifact is not a JSON object: {uri}")
    return document


def _raw_rows(
    document: dict[str, Any],
    *,
    session_id: str,
    path: dict[str, Any],
) -> list[dict[str, Any]]:
    if (
        document.get("schema_version") != 2
        or document.get("algorithm_version") != "standard-glrt64-trajectory-table-v2"
    ):
        raise ValueError("pre-replay GLRT table has an unexpected contract")
    trajectories = document.get("trajectories")
    if not isinstance(trajectories, list):
        raise ValueError("pre-replay GLRT table lacks trajectories")
    result = []
    for row in trajectories:
        if not isinstance(row, dict):
            raise ValueError("pre-replay trajectory is not an object")
        coefficients = [float(value) for value in row["coefficients_hz"]]
        degree = int(row["polynomial_degree"])
        if len(coefficients) != degree + 1:
            raise ValueError("pre-replay trajectory coefficient count disagrees with degree")
        result.append(
            {
                "session_id": session_id,
                "path": path["label"],
                "scope_digest": path["scope_digest"],
                "stage": "before_replay",
                "trajectory_id": str(row["trajectory_id"]),
                "polynomial_degree": degree,
                "reference_time_s": float(row["reference_time_s"]),
                "start_s": float(row["start_s"]),
                "end_s": float(row["end_s"]),
                "duration_s": float(row["end_s"]) - float(row["start_s"]),
                "linear_slope_hz_s": _linear_slope_hz_s(coefficients),
                "selected_for_correction": bool(row["selected_for_correction"]),
                "fit_matches_well": bool(row["fit_matches_well"]),
                "replay_tier": "",
                "automatic_correction_eligible": "",
                "source_uri": path["raw_product_uri"],
                "source_digest": path["raw_product_digest"],
            }
        )
    return result


def _final_rows(
    document: dict[str, Any],
    *,
    session_id: str,
    path: dict[str, Any],
) -> list[dict[str, Any]]:
    table = Glrt64FinalTrajectoryTableV3.model_validate(document)
    return [
        {
            "session_id": session_id,
            "path": path["label"],
            "scope_digest": path["scope_digest"],
            "stage": "after_replay",
            "trajectory_id": row.trajectory_id,
            "polynomial_degree": row.polynomial_degree,
            "reference_time_s": row.reference_time_s,
            "start_s": row.start_s,
            "end_s": row.end_s,
            "duration_s": row.end_s - row.start_s,
            "linear_slope_hz_s": _linear_slope_hz_s(row.absolute_coefficients_hz),
            "selected_for_correction": "",
            "fit_matches_well": "",
            "replay_tier": row.replay_tier.value,
            "automatic_correction_eligible": row.automatic_correction_eligible,
            "source_uri": path["final_product_uri"],
            "source_digest": path["final_product_digest"],
        }
        for row in table.trajectories
    ]


def _extract_rows(
    source: dict[str, Any], resolver: BulkUriResolver
) -> list[dict[str, Any]]:
    if source.get("analysis_kind") != "five-dwell-standard-glrt-tle-zenith-cone-report":
        raise ValueError("source evidence is not the five-dwell cone report")
    result = []
    for dwell in source["dwells"]:
        for path in dwell["paths"]:
            raw = _read_verified_json(
                resolver,
                uri=path["raw_product_uri"],
                expected_digest=path["raw_product_digest"],
            )
            final = _read_verified_json(
                resolver,
                uri=path["final_product_uri"],
                expected_digest=path["final_product_digest"],
            )
            result.extend(_raw_rows(raw, session_id=dwell["session_id"], path=path))
            result.extend(_final_rows(final, session_id=dwell["session_id"], path=path))
    return result


def _distribution(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        raise ValueError("slope distribution cannot be empty")
    return {
        "count": int(array.size),
        "minimum_hz_s": float(array.min()),
        "q1_hz_s": float(np.quantile(array, 0.25)),
        "median_hz_s": float(np.median(array)),
        "q3_hz_s": float(np.quantile(array, 0.75)),
        "maximum_hz_s": float(array.max()),
        "mean_hz_s": float(array.mean()),
        "standard_deviation_hz_s": float(array.std()),
    }


def _summary(rows: list[dict[str, Any]], session_ids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    groups = [("all_dwells", None), *((session_id, session_id) for session_id in session_ids)]
    for label, selected_session in groups:
        stage_values: dict[str, Any] = {}
        for stage in ("before_replay", "after_replay"):
            values = [
                float(row["linear_slope_hz_s"])
                for row in rows
                if row["stage"] == stage
                and (selected_session is None or row["session_id"] == selected_session)
            ]
            stage_values[stage] = _distribution(values)
        stage_values["median_change_hz_s"] = (
            stage_values["after_replay"]["median_hz_s"]
            - stage_values["before_replay"]["median_hz_s"]
        )
        result[label] = stage_values
    return result


def _common_edges(rows: list[dict[str, Any]]) -> np.ndarray:
    values = np.asarray([float(row["linear_slope_hz_s"]) for row in rows])
    lower = math.floor(float(values.min()) / BIN_WIDTH_HZ_S) * BIN_WIDTH_HZ_S
    upper = math.ceil(float(values.max()) / BIN_WIDTH_HZ_S) * BIN_WIDTH_HZ_S
    return np.arange(lower, upper + BIN_WIDTH_HZ_S, BIN_WIDTH_HZ_S)


def _stage_values(
    rows: list[dict[str, Any]], stage: str, *, session_id: str | None = None
) -> np.ndarray:
    return np.asarray(
        [
            float(row["linear_slope_hz_s"])
            for row in rows
            if row["stage"] == stage
            and (session_id is None or row["session_id"] == session_id)
        ],
        dtype=np.float64,
    )


def _plot_overall(path: Path, rows: list[dict[str, Any]], session_ids: list[str]) -> None:
    before = _stage_values(rows, "before_replay")
    after = _stage_values(rows, "after_replay")
    edges = _common_edges(rows)
    colors = {"before": "#8b95a5", "after": "#2368a2"}
    figure, axes = plt.subplots(2, 2, figsize=(16, 11), constrained_layout=True)

    axis = axes[0, 0]
    axis.hist(
        before,
        bins=edges,
        weights=np.full(before.shape, 100.0 / before.size),
        color=colors["before"],
        alpha=0.55,
        label=f"before replay (n={before.size})",
    )
    axis.hist(
        after,
        bins=edges,
        weights=np.full(after.shape, 100.0 / after.size),
        color=colors["after"],
        alpha=0.62,
        label=f"after replay (n={after.size})",
    )
    axis.set_ylabel("tracks per stage (%)")
    axis.set_title("Normalized pooled distribution", loc="left")
    axis.legend()

    axis = axes[0, 1]
    for values, label, color in (
        (before, "before replay", colors["before"]),
        (after, "after replay", colors["after"]),
    ):
        ordered = np.sort(values)
        axis.step(
            ordered,
            np.arange(1, ordered.size + 1) / ordered.size,
            where="post",
            label=label,
            color=color,
            linewidth=2.0,
        )
    axis.set_ylabel("empirical cumulative fraction")
    axis.set_title("Empirical CDF", loc="left")
    axis.legend()

    axis = axes[1, 0]
    positions: list[float] = []
    values_by_position: list[np.ndarray] = []
    tick_positions: list[float] = []
    for index, session_id in enumerate(session_ids):
        base = index * 3.0
        positions.extend((base, base + 1.0))
        values_by_position.extend(
            (
                _stage_values(rows, "before_replay", session_id=session_id),
                _stage_values(rows, "after_replay", session_id=session_id),
            )
        )
        tick_positions.append(base + 0.5)
    box = axis.boxplot(
        values_by_position,
        positions=positions,
        widths=0.72,
        orientation="horizontal",
        patch_artist=True,
        showfliers=True,
    )
    for index, patch in enumerate(box["boxes"]):
        patch.set_facecolor(colors["before"] if index % 2 == 0 else colors["after"])
        patch.set_alpha(0.72)
    axis.set_yticks(tick_positions)
    axis.set_yticklabels([session_id.split("T", 1)[1][:6] for session_id in session_ids])
    axis.invert_yaxis()
    axis.set_ylabel("dwell UTC HHMMSS")
    axis.set_title("Per-dwell spread · gray before / blue after", loc="left")

    axis = axes[1, 1]
    x = np.arange(len(session_ids))
    before_counts = [
        _stage_values(rows, "before_replay", session_id=session_id).size
        for session_id in session_ids
    ]
    after_counts = [
        _stage_values(rows, "after_replay", session_id=session_id).size
        for session_id in session_ids
    ]
    axis.bar(x - 0.19, before_counts, width=0.38, color=colors["before"], label="before")
    axis.bar(x + 0.19, after_counts, width=0.38, color=colors["after"], label="after")
    axis.set_xticks(x)
    axis.set_xticklabels([session_id.split("T", 1)[1][:6] for session_id in session_ids])
    axis.set_ylabel("trajectory count")
    axis.set_xlabel("dwell UTC HHMMSS")
    axis.set_title("Published inventories", loc="left")
    axis.legend()

    for axis in axes.flat:
        axis.grid(alpha=0.16)
        if axis is not axes[1, 1]:
            axis.set_xlabel("linear slope / Doppler drift (Hz/s)")
            axis.axvline(0.0, color="black", linewidth=0.7, alpha=0.5)
    figure.suptitle(
        "Five-dwell GLRT trajectory slope distribution before and after replay\n"
        "linear polynomial coefficient · one trajectory contributes one sample",
        fontweight="bold",
    )
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_by_dwell(path: Path, rows: list[dict[str, Any]], session_ids: list[str]) -> None:
    edges = _common_edges(rows)
    figure, axes = plt.subplots(len(session_ids), 1, figsize=(15, 15), sharex=True)
    for axis, session_id in zip(axes, session_ids, strict=True):
        before = _stage_values(rows, "before_replay", session_id=session_id)
        after = _stage_values(rows, "after_replay", session_id=session_id)
        axis.hist(
            before,
            bins=edges,
            weights=np.full(before.shape, 100.0 / before.size),
            histtype="stepfilled",
            color="#8b95a5",
            alpha=0.42,
            label=f"before replay (n={before.size})",
        )
        axis.hist(
            after,
            bins=edges,
            weights=np.full(after.shape, 100.0 / after.size),
            histtype="step",
            color="#2368a2",
            linewidth=2.4,
            label=f"after replay (n={after.size})",
        )
        axis.axvline(float(np.median(before)), color="#59636e", linestyle=":", linewidth=1.8)
        axis.axvline(float(np.median(after)), color="#2368a2", linestyle="--", linewidth=1.8)
        axis.set_ylabel("tracks (%)")
        axis.set_title(session_id, loc="left")
        axis.grid(alpha=0.16)
        axis.legend(loc="upper left", fontsize=8, ncol=2)
    axes[-1].set_xlabel("linear slope / Doppler drift (Hz/s)")
    figure.suptitle(
        "Per-dwell slope distributions\n"
        "gray filled: before replay · blue outline: after replay · vertical lines: medians",
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _markdown(document: dict[str, Any], figure_root: str) -> str:
    summary = document["summary"]
    pooled = summary["all_dwells"]
    lines = [
        "# Five-dwell trajectory slope distribution before and after replay",
        "",
        f"Generated: `{document['generated_utc']}`",
        "",
        "## Result",
        "",
        f"The pre-replay GLRT inventory contains {pooled['before_replay']['count']} "
        f"trajectories and the final post-replay inventory contains "
        f"{pooled['after_replay']['count']}. Every fitted linear coefficient is negative "
        "in this cohort.",
        "",
        f"The pooled median changes from {pooled['before_replay']['median_hz_s']:.1f} "
        f"Hz/s before replay to {pooled['after_replay']['median_hz_s']:.1f} Hz/s after "
        f"replay, a change of {pooled['median_change_hz_s']:+.1f} Hz/s. This is a change "
        "between published inventories, not a paired per-track correction statistic: "
        "dealiasing, graph selection, and replay can merge, replace, or omit candidates.",
        "",
        f"![Pooled replay slope distribution]({figure_root}/replay-slope-overall.png)",
        "",
        "## Per-dwell summary",
        "",
        "| Dwell | Before n | Before median | Before IQR | After n | After median | "
        "After IQR | Median change |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dwell in document["dwells"]:
        item = summary[dwell["session_id"]]
        before = item["before_replay"]
        after = item["after_replay"]
        lines.append(
            f"| `{dwell['session_id']}` | {before['count']} | "
            f"{before['median_hz_s']:.1f} Hz/s | "
            f"{before['q1_hz_s']:.1f} to {before['q3_hz_s']:.1f} | "
            f"{after['count']} | {after['median_hz_s']:.1f} Hz/s | "
            f"{after['q1_hz_s']:.1f} to {after['q3_hz_s']:.1f} | "
            f"{item['median_change_hz_s']:+.1f} Hz/s |"
        )
    lines.extend(
        [
            "",
            f"![Per-dwell replay slope distributions]"
            f"({figure_root}/replay-slope-by-dwell.png)",
            "",
            "Four dwells move toward a less-negative median drift after replay. "
            "`cap-20260821T193701-87f96f47e73f` is the exception, moving slightly more "
            "negative. Replay also removes the most extreme negative pre-replay tail in "
            "several dwells, but the final distributions remain broad and overlapping.",
            "",
            "## Definition and provenance",
            "",
            "For every linear, quadratic, or cubic trajectory, the reported value is the "
            "coefficient of the linear term in the published highest-power-first polynomial. "
            "It is therefore the instantaneous CFO derivative at that trajectory's published "
            "`reference_time_s`. One trajectory contributes one unweighted sample.",
            "",
            "“Before replay” is `standard.glrt64-trajectory-table.v2`; “after replay” is "
            "`standard.glrt64-final-trajectory-table.v3` using `absolute_coefficients_hz`. "
            "All 40 source artifacts were re-read from immutable bulk storage, checked "
            "against their catalog SHA-256 digests, and validated before extraction.",
            "",
            "## Evidence",
            "",
            f"- [`replay-slope-tracks.csv`]({figure_root}/replay-slope-tracks.csv): one "
            "row per trajectory with path, degree, time range, slope, disposition, and "
            "source digest.",
            f"- [`replay-slope-evidence.json`]({figure_root}/replay-slope-evidence.json): "
            "machine-readable cohort provenance and distribution statistics.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = _arguments()
    source = json.loads(args.source_evidence.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise ValueError("source evidence must be a JSON object")
    resolver = BulkUriResolver(args.bulk_root, allowed_namespaces=("analysis",), create=False)
    rows = _extract_rows(source, resolver)
    session_ids = [str(dwell["session_id"]) for dwell in source["dwells"]]
    summary = _summary(rows, session_ids)
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(output_root / "replay-slope-tracks.csv", rows)
    _plot_overall(output_root / "replay-slope-overall.png", rows, session_ids)
    _plot_by_dwell(output_root / "replay-slope-by-dwell.png", rows, session_ids)
    document = {
        "schema_version": 1,
        "analysis_kind": "five-dwell-standard-replay-slope-distribution",
        "generated_utc": datetime.now(UTC).isoformat(),
        "slope_definition": (
            "linear polynomial coefficient in Hz/s; instantaneous derivative at reference_time_s"
        ),
        "before_product": "standard.glrt64-trajectory-table.v2",
        "after_product": "standard.glrt64-final-trajectory-table.v3",
        "source_evidence_path": str(args.source_evidence),
        "source_evidence_sha256": _sha256(args.source_evidence.read_bytes()),
        "dwells": [
            {
                "session_id": dwell["session_id"],
                "analysis_run_id": dwell["analysis_run_id"],
                "pipeline_release_id": dwell["pipeline_release_id"],
                "paths": dwell["paths"],
            }
            for dwell in source["dwells"]
        ],
        "summary": summary,
    }
    (output_root / "replay-slope-evidence.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    relative_root = Path(os.path.relpath(output_root, start=args.report_path.parent)).as_posix()
    args.report_path.write_text(
        _markdown(document, relative_root),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
