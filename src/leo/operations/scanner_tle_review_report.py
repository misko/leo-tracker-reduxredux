#!/usr/bin/env python3
"""Plot fit/randomized-evaluation TLE residual RMS for every scanner track."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.nearest_neighbour_association import (
    deterministic_randomized_observation_partition,
)
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.research.scanner_tle_screen import rank_curves, sample_grid
from leo.application.scanner_trajectory import (
    project_scanner_candidates,
    timing_is_qualified_for_tle,
)
from leo.contracts.catalogue_association import CataloguePredictionSupportV1
from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def _qualified_start_utc_ns(source) -> int:
    """Use the same current UTC qualification policy as catalogue matching."""

    if not timing_is_qualified_for_tle(source.timing):
        raise ValueError("qualified UTC is required")
    return source.timing.first_sample_estimate_utc_ns


def _apply_common_limits(left, right) -> None:
    """Apply an explicit union of both panels' linear X and Y limits."""

    x_min = min(left.dataLim.xmin, right.dataLim.xmin)
    x_max = max(left.dataLim.xmax, right.dataLim.xmax)
    y_min = min(left.dataLim.ymin, right.dataLim.ymin)
    y_max = max(left.dataLim.ymax, right.dataLim.ymax)
    x_pad = max((x_max - x_min) * 0.03, 0.1)
    y_pad = max((y_max - y_min) * 0.05, 1.0)
    for axis in (left, right):
        axis.set_xlim(x_min - x_pad, x_max + x_pad)
        axis.set_ylim(y_min - y_pad, y_max + y_pad)


def _render_track_plots(session_id: str, tracks: list[dict], output: Path) -> list[str]:
    """Render raw TLE evidence and limited diagnostic fits for each track."""

    colours = {1: "#2166ac", 2: "#1b9e77", 3: "#7b3294"}
    figures = []
    for number, track in enumerate(tracks, start=1):
        candidates = track["candidates"]
        leaders = candidates[:2]
        x = np.arange(1, len(candidates) + 1)
        labels = [f"#{row['standard_rank']}\n{row['catalog_number']}" for row in candidates]
        fig, axes = plt.subplots(3, 2, figsize=(15, 14))
        for axis, metric, title in (
            (axes[0, 0], "offset_only_training_rms_hz", "Fit RMS"),
            (axes[0, 1], "offset_only_heldout_rms_hz", "Randomized-evaluation RMS"),
        ):
            axis.plot(
                x,
                [row[metric] for row in candidates],
                "o-",
                color="#2166ac",
                linewidth=1.8,
                label="TLE residual",
            )
            axis.set_xticks(x, labels)
            axis.set_xlabel("Fit rank and NORAD")
            axis.set_title(title)
            axis.set_ylim(bottom=0)
            axis.grid(axis="y", alpha=0.25)
            axis.spines[["top", "right"]].set_visible(False)
            axis.legend()
        axes[0, 0].set_ylabel("Measured − TLE RMS (Hz; linear scale)")

        fit_axis = axes[1, 0]
        fit_candidate = leaders[0]
        fit_plot = fit_candidate["plot_evidence"]
        time_s = np.asarray(fit_plot["time_s"])
        measured = np.asarray(fit_plot["measured_cfo_hz"])
        training_mask = np.asarray(fit_plot["training_mask"], dtype=bool)
        for axis in (axes[1, 0], axes[1, 1]):
            axis.plot(
                time_s[training_mask],
                measured[training_mask],
                "o",
                color="black",
                ms=3,
                label="GLRT fit",
            )
            axis.plot(
                time_s[~training_mask],
                measured[~training_mask],
                "x",
                color="#666666",
                ms=4,
                label="GLRT evaluation",
            )

        for candidate, colour in zip(leaders, ("#2166ac", "#d95f02"), strict=True):
            fit_axis.plot(
                time_s,
                candidate["plot_evidence"]["tle_cfo_hz"],
                color=colour,
                linewidth=1.5,
                label=f"TLE #{candidate['standard_rank']} · {candidate['catalog_number']}",
            )
        fit_axis.set_title("GLRT versus top two TLE predictions")

        diagnostic_axis = axes[1, 1]
        for degree in (1, 2, 3):
            diagnostic_axis.plot(
                time_s,
                fit_plot["fitted_cfo_hz"][str(degree)],
                color=colours[degree],
                linewidth=1.4,
                label=f"TLE #1 + degree {degree}",
            )
        diagnostic_axis.set_title(
            f"GLRT versus degree 1/2/3 fits for TLE #1 · {fit_candidate['catalog_number']}"
        )

        for column, candidate in enumerate(leaders):
            plot = candidate["plot_evidence"]
            residual_axis = axes[2, column]
            raw_residual = np.asarray(plot["raw_tle_residual_hz"])
            residual_axis.plot(
                time_s[training_mask],
                raw_residual[training_mask],
                "o",
                color="black",
                ms=3,
                label="GLRT fit",
            )
            residual_axis.plot(
                time_s[~training_mask],
                raw_residual[~training_mask],
                "x",
                color="#666666",
                ms=4,
                label="GLRT evaluation",
            )
            residual_axis.axhline(0, color="black", linewidth=0.7)
            residual_axis.set_title(
                f"GLRT residual versus TLE #{candidate['standard_rank']} · "
                f"{candidate['catalog_number']}"
            )
            residual_axis.set_xlabel("Seconds since capture start")
            residual_axis.set_ylabel("Measured − TLE CFO (Hz)")
            residual_axis.legend(fontsize=8)

        for row in (1, 2):
            for axis in axes[row]:
                axis.grid(alpha=0.25)
                axis.spines[["top", "right"]].set_visible(False)
            _apply_common_limits(axes[row, 0], axes[row, 1])
            axes[row, 1].set_ylabel("")
            axes[row, 1].tick_params(axis="y", labelleft=False)

        fig.suptitle(
            f"{session_id} · CH{track['channel']} {track['edge']} · "
            f"{track['start_s']:.1f}–{track['end_s']:.1f} s\n"
            f"{track['observation_count']} observations: "
            f"{track['training_count']} fit / {track['heldout_count']} randomized evaluation",
            fontsize=13,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        name = (
            f"{session_id}-track-{number:02d}-ch{track['channel']}-"
            f"{track['edge']}-top5-tle-review.png"
        )
        fig.savefig(output / name, dpi=150)
        plt.close(fig)
        figures.append(name)
    return figures


def build_report(
    session_id: str,
    output: Path,
    *,
    bulk_root: Path = Path("/srv/bulk/leo"),
    tle_root: Path = Path("/var/lib/leo/tle"),
    site_name: str = "spinnaker-sausalito",
) -> dict:
    sources = ScannerTrackingInputStore(bulk_root)
    try:
        source = sources.load(session_id)
    finally:
        sources.close()
    start = _qualified_start_utc_ns(source)
    site = resolve_preset(site_name)
    trajectory_config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(
        project_scanner_candidates(source), config=trajectory_config
    )
    selection_protocol_digest = canonical_digest(
        {
            "algorithm": "scanner-shared-tracking-v12",
            "position": "scanner-conditional-position-v1",
            "utc_qualification_limit_ns": 2_000_000_000,
            "trajectory": trajectory_config.digest,
            "group_limit": 4,
            "selection": "eligible-first-longest-support-v1",
            "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
            "observer": site.model_dump(mode="json"),
        }
    )

    archive = TleArchiveReader(tle_root)
    snapshot = archive.select_latest_before(start - 505_000_000_000)
    catalogue = parse_element_sets(archive.read(snapshot))
    starlink = [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    grid = SamplingGrid(tuple(start + k * 1_000_000_000 for k in range(-507, 809)), 507, 1.0)
    propagated = propagate_grid(catalogue, grid, starlink)
    observed = observe_grid(propagated, site, grid)
    usable = observed.usable & (np.min(observed.altitude_km, axis=1) > 120)
    for local, index in enumerate(starlink):
        if catalogue.names[index].upper().endswith(" DEB"):
            usable[local] = False
    visible = usable & (np.max(observed.elevation_deg, axis=1) >= -1)
    population = np.flatnonzero(visible)
    catalog_indices = np.asarray([starlink[i] for i in population], dtype=int)
    numbers = np.asarray([catalogue.satellite_numbers[i] for i in catalog_indices], dtype=int)
    names = [catalogue.names[i] for i in catalog_indices]
    elevations = observed.elevation_deg[population]
    taus = np.arange(-5.0, 6.0)

    by_id = {item.tracklet_id: item for item in trajectory.tracklets}
    seen: set[str] = set()
    tracks: list[dict[str, Any]] = []
    for hypothesis in trajectory.hypotheses:
        for tracklet_id in hypothesis.tracklet_ids:
            if tracklet_id in seen:
                continue
            seen.add(tracklet_id)
            graph = persistent_hop_tracklet_graph(hypothesis, tracklet_id)
            rows = sorted(graph.observations, key=lambda item: item.support_center_utc_ns)
            t = np.asarray([(row.support_center_utc_ns - start) / 1e9 for row in rows])
            if len(t) < 14 or t[-1] - t[0] < 7:
                continue
            y = np.asarray([row.measured_cfo_hz for row in rows])
            support = CataloguePredictionSupportV1.from_graph(graph)
            split_seed = canonical_digest(
                {
                    "policy": "persistent-hop-fixed-orbit-randomized-residual-v1",
                    "response_free_support_digest": support.content_digest,
                    "selection_protocol_digest": selection_protocol_digest,
                }
            )
            training_ids, _evaluation_ids = deterministic_randomized_observation_partition(
                tuple(row.observation_id for row in rows),
                training_fraction=0.6,
                split_seed=split_seed,
            )
            training_id_set = set(training_ids)
            training_mask = np.asarray(
                [row.observation_id in training_id_set for row in rows], dtype=bool
            )
            times = t[None, :] + taus[:, None]
            coarse_elevation = sample_grid(elevations, -507, 1, times)
            eligible = np.flatnonzero(np.max(coarse_elevation, axis=(1, 2)) >= -0.1)
            exact_times = tuple(start + round(float(value) * 1e9) for value in times.ravel())
            exact_grid = SamplingGrid(exact_times, len(exact_times) // 2, 1.0)
            exact = observe_grid(
                propagate_grid(catalogue, exact_grid, catalog_indices[eligible].tolist()),
                site,
                exact_grid,
            )
            bank = doppler_shift_hz(11_200_000_000.0, exact.range_rate_km_s).reshape(
                len(eligible), len(taus), len(t)
            )
            exact_elevation = exact.elevation_deg.reshape(bank.shape)
            exact_visible = exact.usable & (np.max(exact_elevation, axis=(1, 2)) >= 0)
            eligible = eligible[exact_visible]
            bank = bank[exact_visible]
            ranking = rank_curves(y, bank, training_mask=training_mask)
            candidates: list[dict[str, Any]] = []
            for index in ranking["order"][:5]:
                tau_index = int(ranking["tau_indices"][index])
                offset_hz = float(ranking["offsets"][index])
                tle_cfo = bank[index, tau_index] + offset_hz
                base_residual = y - tle_cfo
                centered = (t - t[0]) / max(t[-1] - t[0], 1.0)
                fits = {}
                fitted_cfo = {}
                postfit_residual = {}
                for degree in (1, 2, 3):
                    coefficient = np.polyfit(
                        centered[training_mask], base_residual[training_mask], degree
                    )
                    nuisance = np.polyval(coefficient, centered)
                    residual = base_residual - nuisance
                    fits[str(degree)] = {
                        "training_rms_hz": _rms(residual[training_mask]),
                        "heldout_rms_hz": _rms(residual[~training_mask]),
                    }
                    fitted_cfo[str(degree)] = (tle_cfo + nuisance).tolist()
                    postfit_residual[str(degree)] = residual.tolist()
                candidate = {
                    "catalog_number": int(numbers[eligible[index]]),
                    "name": names[eligible[index]],
                    "standard_rank": len(candidates) + 1,
                    "selected_tau_s": float(taus[tau_index]),
                    "offset_hz": offset_hz,
                    "offset_only_training_rms_hz": float(ranking["training_rms"][index]),
                    "offset_only_heldout_rms_hz": float(ranking["heldout_rms"][index]),
                    "polynomial_residual_fits": fits,
                }
                if len(candidates) < 2:
                    candidate["plot_evidence"] = {
                        "time_s": t.tolist(),
                        "training_mask": training_mask.tolist(),
                        "measured_cfo_hz": y.tolist(),
                        "tle_cfo_hz": tle_cfo.tolist(),
                        "raw_tle_residual_hz": base_residual.tolist(),
                        "fitted_cfo_hz": fitted_cfo,
                        "postfit_residual_hz": postfit_residual,
                    }
                candidates.append(candidate)
            tracklet = by_id[tracklet_id]
            tracks.append(
                {
                    "tracklet_id": tracklet_id,
                    "channel": tracklet.lane_key[0],
                    "edge": tracklet.lane_key[1].value,
                    "start_s": float(t[0]),
                    "end_s": float(t[-1]),
                    "span_s": float(t[-1] - t[0]),
                    "observation_count": len(t),
                    "training_count": int(training_mask.sum()),
                    "heldout_count": int((~training_mask).sum()),
                    "candidates": candidates,
                }
            )

    tracks.sort(key=lambda item: item["start_s"])
    fig, axes = plt.subplots(len(tracks), 1, figsize=(14, 3.4 * len(tracks)), squeeze=False)
    colours = {1: "#2166ac", 2: "#1b9e77", 3: "#7b3294"}
    for axis, track in zip(axes[:, 0], tracks, strict=True):
        x = np.arange(1, 6)
        labels = [
            f"#{row['standard_rank']}\n{row['catalog_number']}" for row in track["candidates"]
        ]
        for degree in (1, 2, 3):
            train = [
                row["polynomial_residual_fits"][str(degree)]["training_rms_hz"]
                for row in track["candidates"]
            ]
            held = [
                row["polynomial_residual_fits"][str(degree)]["heldout_rms_hz"]
                for row in track["candidates"]
            ]
            axis.plot(x, train, "o-", color=colours[degree], label=f"degree {degree} train")
            axis.plot(
                x,
                held,
                "s--",
                color=colours[degree],
                alpha=0.82,
                label=f"degree {degree} held-out",
            )
        axis.set_xticks(x, labels)
        axis.set_ylabel("Measured − TLE RMS (Hz)")
        axis.set_yscale("symlog", linthresh=1)
        axis.grid(axis="y", alpha=0.25)
        axis.set_title(
            f"CH{track['channel']} {track['edge']} · "
            f"{track['start_s']:.1f}–{track['end_s']:.1f} s · "
            f"{track['observation_count']} observations "
            f"({track['training_count']} train / {track['heldout_count']} held-out)",
            loc="left",
        )
        axis.legend(ncol=3, fontsize=8)
    axes[-1, 0].set_xlabel("Offset/tau training rank and NORAD catalogue number")
    fig.suptitle(
        f"{session_id} · top-five Starlink candidates per eligible track\n"
        "Polynomial fitted to measured-minus-TLE residual on training rows only; "
        "lower RMS is better",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    output.mkdir(parents=True, exist_ok=True)
    figure = output / f"{session_id}-top5-polynomial-rms.png"
    fig.savefig(figure, dpi=150)
    plt.close(fig)
    track_figures = _render_track_plots(session_id, tracks, output)
    result = {
        "session_id": session_id,
        "protocol": "scanner-top5-tle-polynomial-residual-rms-v1",
        "candidate_ranking": "constant-offset and integer tau [-5,+5] seconds, training rows only",
        "polynomial_fit": (
            "degree 1/2/3 additive residual polynomial, training rows only, frozen on held-out rows"
        ),
        "minimum_observations": 14,
        "minimum_span_s": 7,
        "snapshot_digest": snapshot.digest,
        "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
        "figure": figure.name,
        "track_figures": track_figures,
        "tracks": tracks,
        "candidate_only": True,
        "identity_claimed": False,
    }
    (output / f"{session_id}-top5-polynomial-rms.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--site", default="spinnaker-sausalito")
    args = parser.parse_args()
    result = build_report(
        args.session_id,
        args.output,
        bulk_root=args.bulk_root,
        tle_root=args.tle_root,
        site_name=args.site,
    )
    print(
        json.dumps(
            {
                "session_id": result["session_id"],
                "tracks": len(result["tracks"]),
                "figure": result["figure"],
            }
        )
    )


if __name__ == "__main__":
    main()
