#!/usr/bin/env python3
"""Map per-cell randomized-evaluation TLE coverage for longest scanner tracks."""

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.nearest_neighbour_association import (
    deterministic_randomized_observation_partition,
)
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Grid, Region
from leo.analysis.research.scanner_tle_screen import sample_grid
from leo.application.scanner_trajectory import (
    project_scanner_candidates,
    timing_is_qualified_for_tle,
)
from leo.contracts.catalogue_association import CataloguePredictionSupportV1
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1
from leo.operations.scanner_tle_review_report import _select_review_tracks
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns, teme_to_ecef
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

EXPECTED_TRACKS = (
    "532de33a", "c4f13e60", "29e0467c", "c9477a32", "30d22bbb",
    "7e97bba1", "9f7c7f09", "bd9a5e45", "d988265e", "3b8c416c",
)


def _digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tracks(session, bulk_root, limit):
    store = ScannerTrackingInputStore(bulk_root)
    try:
        source = store.load(session)
    finally:
        store.close()
    if not timing_is_qualified_for_tle(source.timing):
        raise ValueError("qualified UTC required")
    start = source.timing.first_sample_estimate_utc_ns
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(
        project_scanner_candidates(source), config=config
    )
    selected, seen = [], set()
    for hypothesis in trajectory.hypotheses:
        for tracklet_id in hypothesis.tracklet_ids:
            if tracklet_id in seen:
                continue
            seen.add(tracklet_id)
            graph = persistent_hop_tracklet_graph(hypothesis, tracklet_id)
            rows = sorted(graph.observations, key=lambda row: row.support_center_utc_ns)
            t = np.asarray([(row.support_center_utc_ns - start) / 1e9 for row in rows])
            if len(t) >= 14 and t[-1] - t[0] >= 7:
                selected.append((tracklet_id, graph, rows, t, float(t[-1] - t[0])))
    return (
        start, config, _select_review_tracks(selected, limit), len(selected),
        len(trajectory.tracklets),
    )


def _partition(rows, support_digest, trajectory_digest, site):
    protocol = canonical_digest({
        "algorithm": "scanner-shared-tracking-v12",
        "utc_qualification_limit_ns": 2_000_000_000,
        "trajectory": trajectory_digest,
        "group_limit": 4,
        "selection": "eligible-first-longest-support-v1",
        "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
        "observer": site.model_dump(mode="json"),
    })
    seed = canonical_digest({
        "policy": "persistent-hop-fixed-orbit-randomized-residual-v1",
        "response_free_support_digest": support_digest,
        "selection_protocol_digest": protocol,
    })
    training, _ = deterministic_randomized_observation_partition(
        tuple(row.observation_id for row in rows), training_fraction=.6, split_seed=seed
    )
    selected = set(training)
    return np.asarray([row.observation_id in selected for row in rows]), seed


def _states(catalogue, indices, start, t, taus):
    orbit = np.asarray([
        start + round(float(value + tau) * 1e9) for tau in taus for value in t
    ], dtype=np.int64)
    grid = SamplingGrid(tuple(int(value) for value in orbit), 0, 1.0)
    state = propagate_grid(catalogue, grid, indices)
    jd, fraction = julian_day_from_utc_ns(orbit)
    p, v = teme_to_ecef(
        state.position_teme_km, state.velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(jd, fraction),
    )
    shape = (len(indices), len(taus), len(t), 3)
    p, v = p.reshape(shape), v.reshape(shape)
    valid = np.all(state.error_code == 0, axis=1)
    valid &= np.all(np.isfinite(p), axis=(1, 2, 3)) & np.all(np.isfinite(v), axis=(1, 2, 3))
    valid &= np.min(np.linalg.norm(p, axis=-1), axis=(1, 2)) > 6498.137
    return p[valid], v[valid], np.asarray(indices)[valid]


def _score_track_cells(
    y, p, v, norads, sites, masks, taus, threshold, broad_visible=None, candidate_block=512
):
    cells, observations = masks.shape
    best = np.full(cells, np.inf)
    rows = [[] for _ in range(cells)]
    tau_boundary = np.zeros(cells, dtype=bool)
    for begin in range(0, len(norads), candidate_block):
        stop = min(begin + candidate_block, len(norads))
        block_indices = np.arange(begin, stop)
        if broad_visible is not None:
            active = np.any(broad_visible[:, begin:stop], axis=0)
            if not np.any(active):
                continue
            block_indices = block_indices[active]
        position, velocity = p[block_indices], v[block_indices]
        delta = position[None] - sites.ecef_km[:, None, None, None]
        distance = np.linalg.norm(delta, axis=-1)
        prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(
            delta * velocity[None], axis=-1
        ) / distance
        sine = np.sum(delta * sites.up[:, None, None, None], axis=-1) / distance
        visible = np.max(sine, axis=(2, 3)) >= 0
        if broad_visible is not None:
            visible &= broad_visible[:, block_indices]
        residual = y[None, None, None, :] - prediction
        training_count = np.sum(masks, axis=1)
        offset = np.einsum("bcto,bo->bct", residual, masks) / training_count[:, None, None]
        centered = residual - offset[..., None]
        train_mse = np.einsum("bcto,bo->bct", centered**2, masks) / training_count[:, None, None]
        tau_index = np.argmin(train_mse, axis=2)
        held_mask = ~masks
        held_mse = np.einsum("bcto,bo->bct", centered**2, held_mask) / np.sum(
            held_mask, axis=1
        )[:, None, None]
        selected = np.take_along_axis(held_mse, tau_index[..., None], axis=2)[..., 0]
        selected_train = np.take_along_axis(train_mse, tau_index[..., None], axis=2)[..., 0]
        held_rms, train_rms = np.sqrt(selected), np.sqrt(selected_train)
        qualified = visible & (held_rms < threshold)
        for cell in range(cells):
            local = np.flatnonzero(qualified[cell])
            if len(local):
                best[cell] = min(best[cell], float(np.min(held_rms[cell, local])))
            for index in local:
                ti = int(tau_index[cell, index])
                rows[cell].append({
                    "norad": int(norads[block_indices[index]]), "tau_s": float(taus[ti]),
                    "training_rms_hz": float(train_rms[cell, index]),
                    "heldout_rms_hz": float(held_rms[cell, index]),
                })
                tau_boundary[cell] |= ti in (0, len(taus) - 1)
        del delta, distance, prediction, residual, centered
    for values in rows:
        values.sort(key=lambda row: (
            row["heldout_rms_hz"], row["training_rms_hz"], row["norad"], row["tau_s"]
        ))
    return best, rows, tau_boundary


def _score_track(
    y, p, v, norads, sites, masks, taus, threshold, broad_visible=None,
    candidate_block=512, cell_block=8,
):
    best_parts, row_parts, boundary_parts = [], [], []
    for start in range(0, len(sites), cell_block):
        stop = min(start + cell_block, len(sites))
        block = Grid(*(getattr(sites, name)[start:stop] for name in (
            "east_km", "north_km", "latitude_deg", "longitude_deg", "altitude_m",
            "ecef_km", "up",
        )))
        broad = None if broad_visible is None else broad_visible[start:stop]
        best, rows, boundary = _score_track_cells(
            y, p, v, norads, block, masks[start:stop], taus, threshold,
            broad, candidate_block,
        )
        best_parts.append(best)
        row_parts.extend(rows)
        boundary_parts.append(boundary)
    return np.concatenate(best_parts), row_parts, np.concatenate(boundary_parts)


def _blocked_look_sine(position, site_ecef, site_up):
    """Return cell-by-candidate-by-time look sine without 4-D deltas."""
    candidates, times, _ = position.shape
    flat = position.reshape(candidates * times, 3)
    projection = np.concatenate((site_ecef, site_up)) @ flat.T
    cells = len(site_ecef)
    position_norm2 = np.einsum("ij,ij->i", flat, flat)
    site_norm2 = np.einsum("ij,ij->i", site_ecef, site_ecef)
    distance2 = (
        position_norm2[None]
        + site_norm2[:, None]
        - 2.0 * projection[:cells]
    )
    distance = np.sqrt(np.maximum(distance2, 0.0))
    site_up_projection = np.einsum("ij,ij->i", site_ecef, site_up)
    sine = (projection[cells:] - site_up_projection[:, None]) / distance
    return sine.reshape(cells, candidates, times)


def _broad_visibility(
    catalogue, indices, start, sites, track_times, taus, candidate_block=64, cell_block=32
):
    if candidate_block <= 0 or candidate_block % 8:
        raise ValueError("candidate_block must be a positive multiple of eight")
    times = np.arange(-507.0, 809.0, 1.0)
    p, _, valid_indices = _states(catalogue, indices, start, times, np.asarray([0.0]))
    p = p[:, 0]
    visible = np.zeros((len(sites), len(valid_indices)), dtype=bool)
    packed_coarse = np.zeros(
        (len(track_times), len(sites), (len(valid_indices) + 7) // 8), dtype=np.uint8
    )
    horizon = np.sin(np.deg2rad(-1.0))
    for cell_start in range(0, len(sites), cell_block):
        cell_stop = min(cell_start + cell_block, len(sites))
        for begin in range(0, len(valid_indices), candidate_block):
            stop = min(begin + candidate_block, len(valid_indices))
            sine = _blocked_look_sine(
                p[begin:stop],
                sites.ecef_km[cell_start:cell_stop],
                sites.up[cell_start:cell_stop],
            )
            visible[cell_start:cell_stop, begin:stop] = np.max(sine, axis=2) >= horizon
            elevation = np.rad2deg(np.arcsin(np.clip(sine, -1.0, 1.0)))
            for track_index, track_time in enumerate(track_times):
                sampled = sample_grid(
                    elevation,
                    -507.0,
                    1.0,
                    np.asarray(track_time)[None, :] + np.asarray(taus)[:, None],
                )
                gate = np.max(sampled, axis=(2, 3)) >= -0.1
                packed = np.packbits(gate, axis=1, bitorder="little")
                packed_coarse[
                    track_index,
                    cell_start:cell_stop,
                    begin // 8 : begin // 8 + packed.shape[1],
                ] = packed
    return visible, packed_coarse, valid_indices


def run(args):
    started = time.monotonic()
    start, trajectory_config, tracks, eligible_count, reconstructed_count = _tracks(
        args.session, args.bulk_root, args.track_count
    )
    if (
        args.track_count != 10 or args.radius_km <= 0 or args.spacing_km <= 0
        or args.threshold_hz <= 0 or 2 * args.radius_km > args.region_size_km
    ):
        raise ValueError("valid fixed ten-track circle and positive threshold required")
    args.output.mkdir(parents=True)
    if (
        reconstructed_count != 28 or eligible_count != 21
        or tuple(row[0].split(":")[-1][:8] for row in tracks) != EXPECTED_TRACKS
    ):
        actual = tuple(row[0].split(":")[-1][:8] for row in tracks)
        raise ValueError(
            "expected 28 reconstructed/21 eligible and longest-ten ranking: "
            f"{reconstructed_count}, {eligible_count}, {actual}"
        )
    evidence = json.loads((args.evidence / "evidence" / f"{args.session}.json").read_text())
    authority = evidence["inventory"]
    tle = args.evidence / "evidence" / authority["tle_file"]
    if (
        _digest(tle) != authority["tle_digest"]
        or authority["tle_collected_ns"] >= start - 505_000_000_000
    ):
        raise ValueError("exact causal 505-second catalogue authority required")
    snapshot = TleArchiveReader(args.tle_root).select_latest_before(start - 505_000_000_000)
    if (
        snapshot.digest != authority["tle_digest"]
        or snapshot.collected_utc_ns != authority["tle_collected_ns"]
    ):
        raise ValueError("evidence is not the exact latest causal archive snapshot")
    catalogue = parse_element_sets(tle.read_text())
    indices = [
        i for i, name in enumerate(catalogue.names)
        if name.startswith("STARLINK") and not name.upper().endswith(" DEB")
    ]
    region = Region(args.center_lat, args.center_lon, args.region_size_km, args.region_size_km)
    if args.single_observer:
        sites = region.points([0.0], [0.0])
    else:
        full = region.grid(args.spacing_km)
        keep = np.hypot(full.east_km, full.north_km) <= args.radius_km
        sites = region.points(full.east_km[keep], full.north_km[keep])
    if not len(sites):
        raise ValueError("circle contains no 50 km cell centres")
    broad_visible, packed_coarse, broad_indices = _broad_visibility(
        catalogue, indices, start, sites, [row[3] for row in tracks], np.arange(-5.0, 6.0)
    )
    broad_lookup = {int(index): local for local, index in enumerate(broad_indices)}
    cells = [
        {"index": i, "east_km": float(sites.east_km[i]),
         "north_km": float(sites.north_km[i]),
         "latitude_deg": float(sites.latitude_deg[i]),
         "longitude_deg": float(sites.longitude_deg[i]), "tracks": []}
        for i in range(len(sites))
    ]
    count = np.zeros(len(sites), dtype=int)
    tie_score = np.zeros(len(sites))
    taus = np.arange(-5.0, 6.0)
    inventory = []
    seed_rows = []
    candidate_path = args.output / "candidates.jsonl.gz"
    temporary_candidates = args.output / "candidates.jsonl.gz.tmp"
    stream = gzip.open(temporary_candidates, "wt")  # noqa: SIM115
    try:
      for rank, (track_id, graph, observations, t, span) in enumerate(tracks, 1):
        support = CataloguePredictionSupportV1.from_graph(graph)
        partitions = [
            _partition(observations, support.content_digest, trajectory_config.digest,
                       ObserverSiteV1(latitude_deg=float(lat), longitude_deg=float(lon),
                                      altitude_m=0, label=args.observer_label))
            for i, (lat, lon) in enumerate(
                zip(sites.latitude_deg, sites.longitude_deg, strict=True)
            )
        ]
        masks = np.asarray([row[0] for row in partitions])
        seed_rows.append([row[1] for row in partitions])
        if np.any(np.sum(masks, axis=1) != int(np.floor(.6 * len(observations)))):
            raise ValueError("unexpected randomized partition count")
        y = np.asarray([row.measured_cfo_hz for row in observations])
        p, v, valid_indices = _states(catalogue, indices, start, t, taus)
        norads = np.asarray(catalogue.satellite_numbers)[valid_indices]
        broad = np.zeros((len(sites), len(valid_indices)), dtype=bool)
        coarse_all = np.unpackbits(
            packed_coarse[rank - 1], axis=1, count=len(broad_indices), bitorder="little"
        ).astype(bool)
        for local, index in enumerate(valid_indices):
            if int(index) in broad_lookup:
                broad_local = broad_lookup[int(index)]
                broad[:, local] = (
                    broad_visible[:, broad_local] & coarse_all[:, broad_local]
                )
        best, matches, boundary = _score_track(
            y, p, v, norads, sites, masks, taus, args.threshold_hz, broad
        )
        qualified = np.isfinite(best)
        count += qualified
        tie_score += np.minimum(best, args.threshold_hz)
        inventory.append({
            "rank": rank, "tracklet_id": track_id, "span_s": span,
            "observation_count": len(t), "support_digest": support.content_digest,
        })
        for cell in np.flatnonzero(qualified):
            cells[cell]["tracks"].append({
                "track_rank": rank, "tracklet_id": track_id,
                "best_heldout_rms_hz": float(best[cell]),
                "has_tau_boundary_match": bool(boundary[cell]),
                "candidate_count": len(matches[cell]),
                "partition_seed": partitions[cell][1],
            })
            for candidate in matches[cell]:
                stream.write(json.dumps({"cell_index": int(cell), "track_rank": rank,
                                         "tracklet_id": track_id, **candidate}) + "\n")
    finally:
        stream.close()
    temporary_candidates.replace(candidate_path)
    for i, cell in enumerate(cells):
        cell["qualifying_track_count"] = int(count[i])
        cell["clipped_best_rms_sum_hz"] = float(tie_score[i])
    order = sorted(range(len(cells)), key=lambda i: (-count[i], tie_score[i],
                                                     sites.east_km[i], sites.north_km[i]))
    result = {"schema": "randomized-tle-coverage-map/v1", "complete": True,
              "truth_accessed": False, "evaluation_used_for_cell_selection": True,
              "scientific_status": (
                  "exploratory coverage count; not independent holdout evidence "
                  "or joint-position confidence"
              ),
              "session_id": args.session, "eligible_track_count": eligible_count,
              "reconstructed_track_count": reconstructed_count,
              "track_inventory": inventory, "candidate_catalogue_count": len(indices),
              "snapshot_digest": snapshot.digest,
              "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
              "threshold_hz_strict_less_than": args.threshold_hz,
              "center_latitude_deg": args.center_lat,
              "center_longitude_deg": args.center_lon,
              "spacing_km": args.spacing_km, "radius_km": args.radius_km,
              "region_size_km": args.region_size_km,
              "observer_dependent_partition": True,
              "observer_label": args.observer_label,
              "command_parameters": {
                  "session": args.session,
                  "center_latitude_deg": args.center_lat,
                  "center_longitude_deg": args.center_lon,
                  "radius_km": args.radius_km,
                  "region_size_km": args.region_size_km,
                  "spacing_km": args.spacing_km,
                  "threshold_hz": args.threshold_hz,
                  "track_count": args.track_count,
                  "observer_label": args.observer_label,
                  "single_observer": args.single_observer,
              },
              "source_digest": _digest(Path(__file__)),
              "evidence_inventory_digest": _digest(args.evidence / "inventory.json"),
              "session_evidence_digest": _digest(
                  args.evidence / "evidence" / f"{args.session}.json"
              ),
              "cells": cells,
              "top_five_cells": [cells[i] for i in order[:5]],
              "maximum_count_tie_cells": int(np.sum(count == count[order[0]])),
              "candidate_inventory_file": candidate_path.name,
              "candidate_inventory_digest": _digest(candidate_path),
              "elapsed_s": time.monotonic() - started}
    (args.output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    np.savez_compressed(args.output / "map.npz", east_km=sites.east_km,
                        north_km=sites.north_km, latitude_deg=sites.latitude_deg,
                        longitude_deg=sites.longitude_deg, count=count, tie_score=tie_score,
                        partition_seeds=np.asarray(seed_rows))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--radius-km", type=float, required=True)
    parser.add_argument("--region-size-km", type=float, default=5000)
    parser.add_argument("--spacing-km", type=float, default=50)
    parser.add_argument("--threshold-hz", type=float, default=800)
    parser.add_argument("--track-count", type=int, default=10)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--single-observer", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    run(args)


if __name__ == "__main__":
    main()
