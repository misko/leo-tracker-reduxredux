#!/usr/bin/env python3
"""Report random-held dual-RX phase stability on five frozen September 24 tracks."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.sky.frames import (  # noqa: E402
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import (  # noqa: E402
    find_element_set_record,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid  # noqa: E402
from tools.report_recent_dual_rx_single_track_phase import _track_points  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION = ROOT / "reports/figures/2026_09_24_late_dual_rx_track_phase/selection.json"
DEFAULT_PHASE_ROOT = ROOT / "reports/figures/2026_09_24_dual_capture_phase_random/rows"
DEFAULT_OUTPUT = ROOT / "reports/figures/2026_09_24_late_dual_rx_track_phase"
SPEED_OF_LIGHT_M_S = 299_792_458.0
MECHANICAL_BASELINE_M = 0.08


def circular_standard_deviation_deg(resultant: float) -> float:
    if not 0.0 < resultant <= 1.0:
        raise ValueError("resultant must lie in (0, 1]")
    return math.degrees(math.sqrt(-2.0 * math.log(resultant)))


def residual_phase_change_deg(
    rows: list[dict[str, Any]], sample_rate_hz: float
) -> dict[str, float]:
    """Return a descriptive held-response slope; it is never used to select a track."""
    if len(rows) < 2:
        raise ValueError("at least two held phase blocks are required")
    ordered = sorted(rows, key=lambda row: float(row["center_sample"]))
    time_s = np.asarray([float(row["center_sample"]) / sample_rate_hz for row in ordered])
    phase_rad = np.unwrap(np.asarray([float(row["residual_phase_rad"]) for row in ordered]))
    centred = time_s - float(np.mean(time_s))
    slope, intercept = np.polyfit(centred, phase_rad, 1)
    fitted = intercept + slope * centred
    duration = float(time_s[-1] - time_s[0])
    return {
        "held_span_s": duration,
        "linear_change_deg": math.degrees(float(slope) * duration),
        "linear_rate_deg_s": math.degrees(float(slope)),
        "post_linear_rms_deg": math.degrees(float(np.sqrt(np.mean((phase_rad - fitted) ** 2)))),
    }


def geometric_phase_bound_deg(
    catalogue,
    center_utc_ns: int,
    duration_s: float,
    rf_hz: float,
    observer: dict[str, Any],
    *,
    baseline_m: float = MECHANICAL_BASELINE_M,
) -> dict[str, float]:
    """Maximum differential geometric phase over an unknown baseline orientation."""
    half_ns = round(duration_s * 1e9 / 2.0)
    times = (center_utc_ns - half_ns, center_utc_ns, center_utc_ns + half_ns)
    grid = SamplingGrid(times, 1, duration_s / 2.0)
    propagated = propagate_grid(catalogue, grid)
    if not bool(propagated.usable[0]):
        raise ValueError("candidate TLE propagation failed")
    jd, fraction = julian_day_from_utc_ns(np.asarray(times, dtype=np.int64))
    gmst = greenwich_mean_sidereal_time_rad(jd, fraction)
    position, _velocity = teme_to_ecef(
        propagated.position_teme_km[0], propagated.velocity_teme_km_s[0], gmst
    )
    receiver = geodetic_to_ecef_km(
        float(observer["latitude_deg"]),
        float(observer["longitude_deg"]),
        float(observer["altitude_m"]),
    )
    line = position - receiver
    unit = line / np.linalg.norm(line, axis=1)[:, None]
    delta_unit = float(np.linalg.norm(unit[2] - unit[0]))
    phase_rad = 2.0 * math.pi * rf_hz / SPEED_OF_LIGHT_M_S * baseline_m * delta_unit
    return {
        "mechanical_baseline_m": baseline_m,
        "unit_direction_change": delta_unit,
        "maximum_geometric_change_deg": math.degrees(phase_rad),
    }


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _phase_row(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        return json.load(source)


def _tle_path(tle_root: Path, digest: str, collected_utc_ns: int) -> Path:
    name = f"{collected_utc_ns}-{digest.removeprefix('sha256:')}.tle"
    matches = list((tle_root / "archive").rglob(name))
    if len(matches) != 1:
        raise ValueError(f"expected one archived TLE snapshot for {digest}, found {len(matches)}")
    return matches[0]


def analyze(
    selection_path: Path,
    phase_root: Path,
    bulk_root: Path,
    tle_root: Path,
) -> dict[str, Any]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    tracks = []
    all_dwells: list[dict[str, Any]] = []
    for chosen in selection["tracks"]:
        session_id = str(chosen["session_id"])
        manifest_path = bulk_root / "scanner-shared-tracking-v14" / session_id / "manifest.json"
        manifest_envelope = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = manifest_envelope["document"]
        if manifest["identity_claimed"] or not manifest["candidate_only"]:
            raise ValueError("source association semantics changed")
        if (
            manifest["analysis_manifest_sha256"]
            != chosen["evidence"]["tracking_manifest_sha256"]
            or manifest_envelope["sha256"] != chosen["evidence"]["tracking_file_sha256"]
        ):
            raise ValueError("frozen tracking manifest changed")
        if manifest["eligible_tle_snapshot"]["digest"] != chosen["evidence"]["tle_snapshot_sha256"]:
            raise ValueError("frozen eligible TLE snapshot changed")
        tracklets = {row["tracklet_id"]: row for row in manifest["tracklets"]}
        for receiver_id, key, count_key in (
            (0, "rx0_tracklet_id", "rx0_observation_count"),
            (1, "rx1_tracklet_id", "rx1_observation_count"),
        ):
            persisted = tracklets[str(chosen[key])]
            expected = (
                receiver_id,
                int(chosen["channel"]),
                str(chosen["edge"]),
                int(chosen[count_key]),
            )
            actual = (
                persisted["receiver_id"],
                persisted["channel"],
                persisted["edge"],
                persisted["observation_count"],
            )
            if actual != expected:
                raise ValueError("frozen tracklet metadata changed")
        leading = int(chosen["candidate_association"]["leading_norad_catalog_number"])
        pair = {str(chosen["rx0_tracklet_id"]), str(chosen["rx1_tracklet_id"])}
        groups = [
            row
            for row in manifest["tle_candidates"]
            if pair.issubset(set(row["tracklet_ids"]))
            and row["leading_catalog_number"] == leading
        ]
        if len(groups) != 1:
            raise ValueError("frozen dual-track candidate group changed")
        reviews = {row["tracklet_id"]: row for row in manifest["track_reviews"]}
        review_leaders = {
            int(reviews[tracklet]["candidates"][0]["catalog_number"])
            for tracklet in pair
        }
        if review_leaders != {leading}:
            raise ValueError("individual receiver TLE leader no longer agrees with physical group")
        rx0, rx1, trajectory_authority = _track_points(
            bulk_root,
            session_id,
            (str(chosen["rx0_tracklet_id"]), str(chosen["rx1_tracklet_id"])),
        )
        snapshot = manifest["original_tle_snapshot"]
        snapshot_path = _tle_path(
            tle_root, snapshot["digest"], int(snapshot["collected_utc_ns"])
        )
        record = find_element_set_record(
            snapshot_path.read_text(encoding="ascii"),
            leading,
        )
        if record is None:
            raise ValueError("candidate is absent from its source TLE snapshot")
        catalogue = parse_element_sets(record.text)
        dwell_rows = []
        for visit_index in chosen["phase_selected_visit_indices"]:
            path = phase_root / f"{session_id}-visit-{int(visit_index):06d}.json.gz"
            row = _phase_row(path)
            phase = row["random_phase"]
            if row["state"] != "replayed" or not phase["supported"]:
                raise ValueError(
                    f"frozen phase visit is no longer supported: {session_id}/{visit_index}"
                )
            if int(visit_index) not in rx0 or int(visit_index) not in rx1:
                raise ValueError("frozen visit is outside exact dual-track support")
            if row["channel"] != chosen["channel"] or row["edge"] != chosen["edge"]:
                raise ValueError("frozen phase visit lane changed")
            change = residual_phase_change_deg(phase["held_rows"], 2_500_000.0)
            center_ns = rx0[int(visit_index)].support_center_utc_ns + round(
                (
                    rx1[int(visit_index)].support_center_utc_ns
                    - rx0[int(visit_index)].support_center_utc_ns
                )
                / 2
            )
            bound = geometric_phase_bound_deg(
                catalogue,
                center_ns,
                change["held_span_s"],
                float(chosen["actual_rf_hz"]),
                manifest["observer_site"],
            )
            resultant = float(phase["band_phase_resultant"])
            item = {
                "track_rank": int(chosen["rank"]),
                "session_id": session_id,
                "visit_index": int(visit_index),
                "support_center_utc_ns": center_ns,
                "phase_blind_priority": float(row["phase_blind_priority"]),
                "circular_r": resultant,
                "circular_standard_deviation_deg": circular_standard_deviation_deg(resultant),
                "tracked_coherence": float(phase["tracked_coherence"]),
                "wrong_pair_coherence": float(phase["wrong_pair_coherence"]),
                "held_group_count": len(phase["group_summaries"]),
                **change,
                **bound,
                "held_rows": phase["held_rows"],
            }
            dwell_rows.append(item)
            all_dwells.append(item)
        track_summary = {
            **chosen,
            "phase": {
                "dwell_count": len(dwell_rows),
                "median_circular_r": float(np.median([row["circular_r"] for row in dwell_rows])),
                "minimum_circular_r": min(row["circular_r"] for row in dwell_rows),
                "median_circular_standard_deviation_deg": float(
                    np.median([row["circular_standard_deviation_deg"] for row in dwell_rows])
                ),
                "median_tracked_coherence": float(
                    np.median([row["tracked_coherence"] for row in dwell_rows])
                ),
                "median_wrong_pair_coherence": float(
                    np.median([row["wrong_pair_coherence"] for row in dwell_rows])
                ),
                "median_absolute_residual_change_deg": float(
                    np.median([abs(row["linear_change_deg"]) for row in dwell_rows])
                ),
                "median_candidate_geometric_upper_bound_deg": float(
                    np.median([row["maximum_geometric_change_deg"] for row in dwell_rows])
                ),
            },
            "trajectory_authority": trajectory_authority,
            "tle_source": {
                "path": str(snapshot_path),
                "sha256": _sha256(snapshot_path),
                "catalog_name": record.name,
            },
            "dwells": dwell_rows,
        }
        tracks.append(track_summary)
    expected = np.asarray([row["maximum_geometric_change_deg"] for row in all_dwells])
    measured = np.asarray([abs(row["linear_change_deg"]) for row in all_dwells])
    ratio = measured / expected
    pearson = float(np.corrcoef(expected, measured)[0, 1]) if len(all_dwells) > 1 else math.nan
    return {
        "schema": "org.leo.research.late-dual-rx-track-phase-report/v1",
        "selection_id": selection["selection_id"],
        "selection_sha256": _sha256(selection_path),
        "scope": "descriptive saved-IQ report; random held frequency groups only",
        "identity_claimed": False,
        "geometric_phase_claimed": False,
        "phase_observable": (
            "RX1 times conjugate RX0 after train-only relative carrier/response removal"
        ),
        "association_semantics": "candidate-only leading TLE hypothesis",
        "mechanical_baseline_assumption_m": MECHANICAL_BASELINE_M,
        "comparison_semantics": (
            "measured held residual phase change versus maximum candidate-driven "
            "differential geometric change over an 8 cm baseline of unknown orientation; "
            "the bound is not a calibrated prediction"
        ),
        "track_count": len(tracks),
        "dwell_count": len(all_dwells),
        "aggregate": {
            "median_circular_r": float(np.median([row["circular_r"] for row in all_dwells])),
            "minimum_circular_r": min(row["circular_r"] for row in all_dwells),
            "median_circular_standard_deviation_deg": float(
                np.median([row["circular_standard_deviation_deg"] for row in all_dwells])
            ),
            "median_tracked_coherence": float(
                np.median([row["tracked_coherence"] for row in all_dwells])
            ),
            "median_wrong_pair_coherence": float(
                np.median([row["wrong_pair_coherence"] for row in all_dwells])
            ),
            "median_absolute_residual_change_deg": float(np.median(measured)),
            "median_candidate_geometric_upper_bound_deg": float(np.median(expected)),
            "measured_within_candidate_upper_bound_count": int(np.sum(measured <= expected)),
            "median_measured_to_candidate_bound_ratio": float(np.median(ratio)),
            "measured_to_candidate_bound_ratio_10_90_percentile": np.quantile(
                ratio, [0.1, 0.9]
            ).tolist(),
            "absolute_change_vs_candidate_bound_pearson_r": pearson,
        },
        "tracks": tracks,
    }


def render(summary: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    colours = plt.cm.tab10(np.arange(5))
    labels = [f"T{track['rank']}\n{track['session_id'][-6:]}" for track in summary["tracks"]]

    fig, axes = plt.subplots(3, 1, figsize=(12, 11), constrained_layout=True)
    x = np.arange(5)
    mins = [
        min(track["rx0_observation_count"], track["rx1_observation_count"])
        for track in summary["tracks"]
    ]
    phase_counts = [track["phase"]["dwell_count"] for track in summary["tracks"]]
    axes[0].bar(x - 0.18, mins, 0.36, label="minimum RX0/RX1 track observations", color="#4c78a8")
    axes[0].bar(
        x + 0.18,
        phase_counts,
        0.36,
        label="phase-assessed overlapping dwells",
        color="#f58518",
    )
    axes[0].set_ylabel("Count")
    axes[0].set_title("Phase-blind dual-receiver track coverage")
    axes[0].legend()
    for index, track in enumerate(summary["tracks"]):
        values = [row["circular_r"] for row in track["dwells"]]
        axes[1].scatter(np.full(len(values), index), values, color=colours[index], alpha=0.75)
        axes[1].plot(index, np.median(values), marker="_", ms=18, mew=3, color="black")
    axes[1].set_ylim(0.75, 1.005)
    axes[1].set_ylabel("Held circular R")
    axes[1].set_title("Random-held residual phase stability; black bar is median")
    for index, track in enumerate(summary["tracks"]):
        tracked = [row["tracked_coherence"] for row in track["dwells"]]
        wrong = [row["wrong_pair_coherence"] for row in track["dwells"]]
        axes[2].scatter(
            np.full(len(tracked), index - 0.08),
            tracked,
            color=colours[index],
            alpha=0.7,
        )
        axes[2].scatter(
            np.full(len(wrong), index + 0.08),
            wrong,
            facecolors="none",
            edgecolors=colours[index],
            alpha=0.8,
        )
    axes[2].set_yscale("log")
    axes[2].set_ylabel("Coherence")
    axes[2].set_title("Tracked held coherence (filled) versus wrong-pair control (open)")
    for axis in axes:
        axis.set_xticks(x, labels)
        axis.grid(axis="y", alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    fig.savefig(output / "coverage-and-stability.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(5, 1, figsize=(13, 14), sharex=True, constrained_layout=True)
    for axis, colour, track in zip(axes, colours, summary["tracks"], strict=True):
        for dwell in track["dwells"]:
            rows = sorted(dwell["held_rows"], key=lambda row: float(row["center_sample"]))
            time_ms = np.asarray([float(row["center_sample"]) / 2500.0 for row in rows])
            phase = np.unwrap(np.asarray([float(row["residual_phase_rad"]) for row in rows]))
            phase_deg = np.degrees(phase - np.mean(phase))
            axis.plot(time_ms, phase_deg, ".-", color=colour, alpha=0.38, lw=0.8, ms=2.5)
        phase = track["phase"]
        axis.set_ylabel("Residual °")
        axis.set_title(
            f"T{track['rank']} · {track['session_id']} · CH{track['channel']} {track['edge']} · "
            f"candidate NORAD {track['candidate_association']['leading_norad_catalog_number']} · "
            f"median R={phase['median_circular_r']:.3f}",
            loc="left",
            fontsize=10,
        )
        axis.grid(alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
    axes[-1].set_xlabel("Time within 120 ms dwell (ms); each line is one random-held response")
    fig.savefig(output / "held-phase-traces.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    for colour, track in zip(colours, summary["tracks"], strict=True):
        expected = [row["maximum_geometric_change_deg"] for row in track["dwells"]]
        measured = [abs(row["linear_change_deg"]) for row in track["dwells"]]
        axes[0].scatter(expected, measured, color=colour, label=f"T{track['rank']}", alpha=0.8)
        ratio = np.asarray(measured) / np.asarray(expected)
        axes[1].scatter(np.full(len(ratio), track["rank"]), ratio, color=colour, alpha=0.75)
    limits = [0.05, 300.0]
    axes[0].plot(limits, limits, "--", color="black", lw=1, label="equal magnitude")
    axes[0].set(xscale="log", yscale="log", xlim=limits, ylim=limits)
    axes[0].set_xlabel("Candidate geometry upper bound (degrees)")
    axes[0].set_ylabel("|Measured held residual linear change| (degrees)")
    r = summary["aggregate"]["absolute_change_vs_candidate_bound_pearson_r"]
    axes[0].set_title(f"Different observables; descriptive |change| correlation r={r:.2f}")
    axes[0].legend(ncol=2)
    axes[1].axhline(1, ls="--", color="black", lw=1)
    axes[1].set_yscale("log")
    axes[1].set_xlabel("Frozen track rank")
    axes[1].set_ylabel("Measured |change| / geometry upper bound")
    axes[1].set_title("Excess over an 8 cm mechanical-baseline envelope")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    fig.savefig(output / "candidate-phase-change-comparison.png", dpi=170)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--phase-root", type=Path, default=DEFAULT_PHASE_ROOT)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = analyze(args.selection, args.phase_root, args.bulk_root, args.tle_root)
    render(summary, args.output)
    serializable = json.loads(json.dumps(summary))
    for track in serializable["tracks"]:
        for dwell in track["dwells"]:
            dwell.pop("held_rows", None)
    (args.output / "summary.json").write_text(json.dumps(serializable, indent=2) + "\n")
    print(
        json.dumps(
            {
                "tracks": summary["track_count"],
                "dwells": summary["dwell_count"],
                **summary["aggregate"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
