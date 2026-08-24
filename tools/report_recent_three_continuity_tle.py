#!/usr/bin/env python3
"""Audit three sealed continuity-v2 dwells against causal Starlink TLEs.

This report-only tool deliberately keeps scalar Doppler-rate compatibility
separate from held-out orbital-shape discrimination.  It reuses the reviewed
strict-linear and train/holdout implementations, but permits the explicitly
small three-dwell deployment cohort and applies a family-wise correction to
the scalar wrong-time tests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from sqlalchemy.orm import Session

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.catalog.database import create_catalog_engine
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.storage import BulkUriResolver

try:
    from tools import report_five_dwell_degree1_only as degree1
    from tools import report_five_dwell_tle_cone as base
    from tools import report_multi_dwell_starlink_association as association
except ModuleNotFoundError:  # Direct ``python tools/...`` invocation.
    import report_five_dwell_degree1_only as degree1
    import report_five_dwell_tle_cone as base
    import report_multi_dwell_starlink_association as association


DEFAULT_SESSION_IDS = (
    "cap-20260824T192019-9023840c8e9f",
    "cap-20260824T192252-9981b9c27853",
    "cap-20260824T192531-491832825b97",
)
HISTORICAL_TRACK_WINS = (1, 37)
HISTORICAL_DWELL_WINS = (0, 13)
HISTORICAL_SCALAR_PASSES = (3, 37)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEO_DATABASE_URL", base.DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--bulk-root", type=Path, default=base.DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=base.DEFAULT_TLE_ROOT)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--session-id", action="append", dest="session_ids", default=[])
    parser.add_argument("--provider", default=base.REQUIRED_TLE_PROVIDER)
    parser.add_argument("--horizon-deg", type=float, default=base.DEFAULT_HORIZON_DEG)
    parser.add_argument("--maximum-selected-per-path", type=int, default=16)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision(ref: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd()}", "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def holm_adjusted_pvalues(values: list[float]) -> list[float]:
    """Return Holm family-wise adjusted p-values in the input order."""

    if not values:
        return []
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("p-values must be finite and between zero and one")
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    adjusted = [0.0] * len(values)
    previous = 0.0
    count = len(values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * values[index])
        previous = max(previous, candidate)
        adjusted[index] = previous
    return adjusted


def fisher_exact_greater(a: int, b: int, c: int, d: int) -> float:
    """One-sided Fisher exact p for a larger first-row success fraction."""

    if any(value < 0 for value in (a, b, c, d)):
        raise ValueError("contingency counts cannot be negative")
    first_total = a + b
    successes = a + c
    total = first_total + c + d
    if total == 0:
        raise ValueError("contingency table cannot be empty")
    denominator = math.comb(total, first_total)

    def probability(success_count: int) -> float:
        return (
            math.comb(successes, success_count)
            * math.comb(total - successes, first_total - success_count)
            / denominator
        )

    upper = min(first_total, successes)
    return float(sum(probability(value) for value in range(a, upper + 1)))


def aggregate_scalar_time_null(source: dict[str, Any]) -> dict[str, Any]:
    """Summarize the common wrong-time field without treating tracks as independent."""

    dwells = source["dwells"]
    if len(dwells) != 3 or any(len(dwell["top_tracks"]) != 3 for dwell in dwells):
        raise ValueError("aggregate time null requires exactly three dwells and three tracks each")
    first_controls = dwells[0]["top_tracks"][0]["match"]["null_controls"]
    shifts = [float(control["time_shift_s"]) for control in first_controls]
    if not shifts:
        raise ValueError("aggregate time null requires wrong-time controls")
    true_by_dwell: list[list[float]] = []
    null_by_shift: list[list[list[float]]] = [[[] for _ in dwells] for _ in shifts]
    for dwell_index, dwell in enumerate(dwells):
        true_errors: list[float] = []
        for track in dwell["top_tracks"]:
            match = track["match"]
            true_errors.append(float(match["best_absolute_rate_error_hz_s"]))
            controls = match["null_controls"]
            if len(controls) != len(shifts):
                raise ValueError("wrong-time control counts differ across tracks")
            for shift_index, (expected_shift, control) in enumerate(
                zip(shifts, controls, strict=True)
            ):
                if not math.isclose(float(control["time_shift_s"]), expected_shift, abs_tol=1e-12):
                    raise ValueError("wrong-time shifts differ across tracks")
                null_by_shift[shift_index][dwell_index].append(
                    float(control["best_absolute_rate_error_hz_s"])
                )
        true_by_dwell.append(true_errors)
    true_flat = [value for dwell in true_by_dwell for value in dwell]
    null_flat = [[value for dwell in by_dwell for value in dwell] for by_dwell in null_by_shift]
    statistics = {
        "track_median_error_hz_s": (
            float(np.median(true_flat)),
            [float(np.median(values)) for values in null_flat],
        ),
        "track_mean_error_hz_s": (
            float(np.mean(true_flat)),
            [float(np.mean(values)) for values in null_flat],
        ),
        "dwell_clustered_median_then_mean_error_hz_s": (
            float(np.mean([np.median(values) for values in true_by_dwell])),
            [
                float(np.mean([np.median(values) for values in by_dwell]))
                for by_dwell in null_by_shift
            ],
        ),
    }
    return {
        "exploratory_post_hoc": True,
        "control_count": len(shifts),
        "time_shifts_s": shifts,
        "statistics": {
            name: {
                "true_time_value_hz_s": true_value,
                "null_median_hz_s": float(np.median(null_values)),
                "best_null_hz_s": float(min(null_values)),
                "true_time_rank_among_true_and_null": 1
                + sum(value <= true_value for value in null_values),
            }
            for name, (true_value, null_values) in statistics.items()
        },
        "interpretation": (
            "Population-level time-specific compatibility only; statistic was examined post hoc, "
            "time shifts are correlated, and the three dwells span only about five minutes."
        ),
    }


def _scalar_rows(source: dict[str, Any], dwells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (dwell["session_id"], track["trajectory_id"]): track
        for dwell in source["dwells"]
        for track in dwell["top_tracks"]
    }
    rows: list[dict[str, Any]] = []
    for dwell in dwells:
        for track in dwell["tracks"]:
            scalar = lookup[(dwell["session_id"], track["trajectory_id"])]
            candidate = scalar["match"]["top_candidates"][0]
            rows.append(
                {
                    "session_id": dwell["session_id"],
                    "track": track["label"],
                    "path": track["path"],
                    "trajectory_id": track["trajectory_id"],
                    "duration_s": track["duration_s"],
                    "observation_count": track["observation_count"],
                    "measured_rate_hz_s": track["radio_rate_hz_s"],
                    "radio_residual_rms_hz": track["radio_residual_rms_hz"],
                    "candidate_name": candidate["object_name"],
                    "catalog_number": candidate["catalog_number"],
                    "predicted_rate_hz_s": candidate["predicted_rate_hz_s"],
                    "absolute_rate_error_hz_s": scalar["match"]["best_absolute_rate_error_hz_s"],
                    "candidate_count_within_500_hz_s": scalar["match"]["matches_within_500_hz_s"],
                    "visible_satellite_count": scalar["match"]["visible_satellite_count"],
                    "wrong_time_empirical_p": scalar["match"]["true_time_empirical_p"],
                    "elevation_deg": candidate["elevation_deg"],
                    "azimuth_deg": candidate["azimuth_deg"],
                    "slant_range_km": candidate["slant_range_km"],
                    "range_rate_km_s": candidate["range_rate_km_s"],
                    "element_age_s": candidate["element_age_s"],
                }
            )
    adjusted = holm_adjusted_pvalues([row["wrong_time_empirical_p"] for row in rows])
    for row, value in zip(rows, adjusted, strict=True):
        row["wrong_time_holm_p"] = value
    return rows


def _shape_rows(dwells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dwell in dwells:
        for track in dwell["tracks"]:
            primary = track["models"]["bounded_200"]
            best = primary["best"]
            free = track["models"]["free_affine"]["best"]
            sensitivity = track["error_budget"]["adjacent_causal_tle_sensitivity"]
            rows.append(
                {
                    "session_id": dwell["session_id"],
                    "track": track["label"],
                    "path": track["path"],
                    "candidate_name": best["object_name"],
                    "catalog_number": best["catalog_number"],
                    "train_rms_hz": best["train_residual_rms_hz"],
                    "holdout_rms_hz": best["holdout_residual_rms_hz"],
                    "linear_holdout_rms_hz": track["linear_null"]["holdout_residual_rms_hz"],
                    "holdout_advantage_hz": track["primary_holdout_advantage_over_linear_hz"],
                    "runner_up_margin_hz": primary["runner_up_training_margin_hz"],
                    "epoch_adjustment_s": best["epoch_adjustment_s"],
                    "nuisance_drift_hz_s": best["nuisance_drift_hz_s"],
                    "free_affine_catalog_number": free["catalog_number"],
                    "free_affine_holdout_rms_hz": free["holdout_residual_rms_hz"],
                    "adjacent_tle_shape_rms_hz": (
                        sensitivity["affine_removed_shape_rms_hz"]
                        if sensitivity["available"]
                        else None
                    ),
                    "failed_secure_checks": [
                        name for name, passed in track["secure_checks"].items() if not passed
                    ],
                    "secure_association": track["secure_association"],
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty result table")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _plot_scalar(path: Path, rows: list[dict[str, Any]]) -> None:
    session_order = list(dict.fromkeys(row["session_id"] for row in rows))
    labels = [
        f"D{1 + session_order.index(row['session_id'])} {row['track']}\n{row['path']}"
        for row in rows
    ]
    errors = np.asarray([row["absolute_rate_error_hz_s"] for row in rows], dtype=float)
    counts = np.asarray([row["candidate_count_within_500_hz_s"] for row in rows], dtype=float)
    pvalues = np.asarray([row["wrong_time_empirical_p"] for row in rows], dtype=float)
    figure, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    x = np.arange(len(rows))
    axes[0].bar(x, errors, color="#277da1", alpha=0.82)
    axes[0].set_ylabel("nearest true-time rate error (Hz/s)")
    axes[0].set_title("Scalar TLE-rate compatibility is close but crowded", loc="left")
    axes[0].grid(axis="y", alpha=0.18)
    secondary = axes[0].twinx()
    secondary.plot(x, counts, color="#d1495b", marker="o", linewidth=1.2)
    secondary.set_ylabel("visible candidates within ±500 Hz/s")
    axes[1].scatter(x, pvalues, color="#277da1", marker="o", label="raw wrong-time p")
    axes[1].scatter(
        x,
        [row["wrong_time_holm_p"] for row in rows],
        color="#d1495b",
        marker="x",
        label="Holm family-wise p",
    )
    axes[1].axhline(0.05, color="#687381", linestyle="--", linewidth=1)
    axes[1].set_ylabel("empirical p")
    axes[1].set_xticks(x, labels, rotation=25, ha="right")
    axes[1].set_ylim(-0.02, 1.02)
    axes[1].set_title("Wrong-time null removes apparent scalar specificity", loc="left")
    axes[1].grid(axis="y", alpha=0.18)
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_holdout(path: Path, dwells: list[dict[str, Any]]) -> None:
    tracks = [track for dwell in dwells for track in dwell["tracks"]]
    null = np.asarray([item["linear_null"]["holdout_residual_rms_hz"] for item in tracks])
    orbital = np.asarray(
        [item["models"]["bounded_200"]["best"]["holdout_residual_rms_hz"] for item in tracks]
    )
    limit = max(float(null.max()), float(orbital.max())) * 1.08
    figure, axis = plt.subplots(figsize=(10, 8))
    axis.plot([0, limit], [0, limit], color="#687381", linestyle="--", linewidth=1)
    colors = ("#277da1", "#d1495b", "#2a9d8f")
    offset = 0
    for dwell_index, dwell in enumerate(dwells, start=1):
        count = len(dwell["tracks"])
        axis.scatter(
            null[offset : offset + count],
            orbital[offset : offset + count],
            color=colors[(dwell_index - 1) % len(colors)],
            s=54,
            label=f"D{dwell_index}",
        )
        for track_index, track in enumerate(dwell["tracks"]):
            index = offset + track_index
            axis.annotate(
                f"D{dwell_index} {track['label']}",
                (null[index], orbital[index]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
            )
        offset += count
    axis.set_xlim(0, limit)
    axis.set_ylim(0, limit)
    axis.set_xlabel("radio-only linear holdout RMS (Hz)")
    axis.set_ylabel("best bounded-orbit holdout RMS (Hz)")
    axis.set_title("Held-out orbital shape: seven of nine points fall below the line", loc="left")
    axis.grid(alpha=0.18)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _summary(dwells: list[dict[str, Any]], scalar_rows: list[dict[str, Any]]) -> dict[str, Any]:
    tracks = [track for dwell in dwells for track in dwell["tracks"]]
    primary = [track["models"]["bounded_200"]["best"] for track in tracks]
    linear = [track["linear_null"]["holdout_residual_rms_hz"] for track in tracks]
    orbit = [item["holdout_residual_rms_hz"] for item in primary]
    free = [track["models"]["free_affine"]["best"]["holdout_residual_rms_hz"] for track in tracks]
    track_wins = sum(o < n for o, n in zip(orbit, linear, strict=True))
    dwell_wins = sum(
        dwell["hypotheses"]["independent_satellites"]["holdout_rms_hz"]
        < dwell["hypotheses"]["radio_only_linear_holdout_rms_hz"]
        for dwell in dwells
    )
    scalar_passes = sum(row["wrong_time_empirical_p"] <= 0.05 for row in scalar_rows)
    return {
        "eligible_track_count": len(tracks),
        "secure_association_count": sum(track["secure_association"] for track in tracks),
        "raw_scalar_p_le_0_05_count": scalar_passes,
        "holm_scalar_p_le_0_05_count": sum(row["wrong_time_holm_p"] <= 0.05 for row in scalar_rows),
        "median_nearest_scalar_error_hz_s": float(
            np.median([row["absolute_rate_error_hz_s"] for row in scalar_rows])
        ),
        "median_candidates_within_500_hz_s": float(
            np.median([row["candidate_count_within_500_hz_s"] for row in scalar_rows])
        ),
        "primary_orbit_track_win_count": track_wins,
        "free_affine_orbit_track_win_count": sum(o < n for o, n in zip(free, linear, strict=True)),
        "primary_orbit_dwell_win_count": dwell_wins,
        "median_linear_holdout_rms_hz": float(np.median(linear)),
        "median_primary_orbit_holdout_rms_hz": float(np.median(orbit)),
        "median_free_affine_orbit_holdout_rms_hz": float(np.median(free)),
        "historical_comparison": {
            "track_orbit_wins": {
                "recent": [track_wins, len(tracks)],
                "historical": list(HISTORICAL_TRACK_WINS),
                "fisher_greater_p": fisher_exact_greater(
                    track_wins,
                    len(tracks) - track_wins,
                    HISTORICAL_TRACK_WINS[0],
                    HISTORICAL_TRACK_WINS[1] - HISTORICAL_TRACK_WINS[0],
                ),
            },
            "dwell_orbit_wins": {
                "recent": [dwell_wins, len(dwells)],
                "historical": list(HISTORICAL_DWELL_WINS),
                "fisher_greater_p": fisher_exact_greater(
                    dwell_wins,
                    len(dwells) - dwell_wins,
                    HISTORICAL_DWELL_WINS[0],
                    HISTORICAL_DWELL_WINS[1] - HISTORICAL_DWELL_WINS[0],
                ),
            },
            "scalar_wrong_time_passes": {
                "recent": [scalar_passes, len(scalar_rows)],
                "historical": list(HISTORICAL_SCALAR_PASSES),
                "fisher_greater_p": fisher_exact_greater(
                    scalar_passes,
                    len(scalar_rows) - scalar_passes,
                    HISTORICAL_SCALAR_PASSES[0],
                    HISTORICAL_SCALAR_PASSES[1] - HISTORICAL_SCALAR_PASSES[0],
                ),
            },
            "warning": (
                "Descriptive only: tracks are clustered and cohorts differ in capture "
                "timing integrity."
            ),
        },
    }


def main() -> None:
    args = _arguments()
    session_ids = tuple(args.session_ids) or DEFAULT_SESSION_IDS
    if len(session_ids) != 3 or len(set(session_ids)) != 3:
        raise ValueError("this bounded deployment audit requires exactly three unique dwells")
    source = json.loads(args.source_evidence.read_text(encoding="utf-8"))
    association._validate_source_cohort(source, session_ids)
    scalar_lookup = association._scalar_lookup(source)
    args.output_root.mkdir(parents=True, exist_ok=True)
    engine = create_catalog_engine(args.database_url)
    resolver = BulkUriResolver(args.bulk_root, allowed_namespaces=("analysis",), create=False)
    archive = TleArchiveReader(args.tle_root)
    observer = ObserverSiteV1(
        latitude_deg=base.DEFAULT_LATITUDE_DEG,
        longitude_deg=base.DEFAULT_LONGITUDE_DEG,
        altitude_m=base.DEFAULT_ALTITUDE_M,
        label="reviewed-spinnaker-sausalito-not-capture-bound",
    )
    with Session(engine) as database:
        cohort = base._cohort(database, session_ids)
        dwells = [
            association._analyze_dwell(
                run,
                degree1._path_evidence(database, resolver, run),
                archive,
                observer,
                scalar_lookup,
                provider=args.provider,
                horizon_deg=args.horizon_deg,
                maximum_selected=args.maximum_selected_per_path,
            )
            for run in cohort
        ]
    scalar_rows = _scalar_rows(source, dwells)
    shape_rows = _shape_rows(dwells)
    evidence = {
        "schema_version": 1,
        "analysis_kind": "recent_three_continuity_tle_candidate_and_null_audit",
        "generated_utc": datetime.now(UTC).isoformat(),
        "analysis_commit": _git_revision("HEAD"),
        "origin_main_commit": _git_revision("origin/main"),
        "tool_sha256": _sha256(Path(__file__)),
        "source_evidence_sha256": _sha256(args.source_evidence),
        "small_cohort_descriptive_only": True,
        "session_ids": list(session_ids),
        "observer": observer.model_dump(mode="json"),
        "method": {
            "scalar_rate": "nearest causal-TLE two-second midpoint Doppler secant",
            "scalar_null": "forty wrong-time fields at ±30..600 seconds",
            "multiple_testing": "Holm family-wise correction across nine displayed tracks",
            "shape_model": "first 60% selects identity/offset/epoch/drift; final 40% held out",
            "shape_search_null": (
                "not computed; held-out orbit-versus-line comparisons are descriptive and the "
                "40 wrong-time controls calibrate only the scalar visible-sky minimum"
            ),
            "primary_nuisance_drift_bound_hz_s": 200.0,
            "primary_epoch_bound_s": 0.30,
            "horizon_deg": args.horizon_deg,
        },
        "summary": _summary(dwells, scalar_rows),
        "aggregate_scalar_time_null": aggregate_scalar_time_null(source),
        "scalar_candidates": scalar_rows,
        "shape_matches": shape_rows,
        "dwells": dwells,
    }
    evidence_path = args.output_root / "recent-three-tle-null-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    _write_csv(args.output_root / "scalar-candidates.csv", scalar_rows)
    _write_csv(args.output_root / "shape-matches.csv", shape_rows)
    _plot_scalar(args.output_root / "scalar-candidates-and-null.png", scalar_rows)
    _plot_holdout(args.output_root / "heldout-orbit-vs-linear.png", dwells)
    association._plot_hypotheses(args.output_root / "dwell-hypothesis-comparison.png", dwells)
    association._plot_null_and_advantage(
        args.output_root / "time-null-versus-curve-advantage.png", dwells
    )
    print(
        json.dumps(
            {
                "evidence_path": str(evidence_path),
                **evidence["summary"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
