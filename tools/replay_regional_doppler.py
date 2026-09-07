#!/usr/bin/env python3
"""Blind regional search of RF-only archived scan evidence and causal TLEs.

No import of the earlier known-site scorer is allowed. This adapter whitelists
observation fields, verifies source/catalogue digests, and never reads prior
matching results, site configuration, or a true position. Output is exploratory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.research.regional_doppler import (
    ObservationArc,
    Region,
    ScoreConfig,
    logsumexp,
    score_states,
)
from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid


def write_json(path, document):
    path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_observations(document, max_per_partition=8, individual=False):
    """Only RF fields; no source observation may enter two scored episodes."""
    sources = {row["tracklet_id"]: row for row in document["series"]}
    episodes = (
        [
            {"episode_id": key, "members": [key], "channel": row["channel"]}
            for key, row in sources.items()
        ]
        if individual
        else document["episodes"]
    )
    used, output = set(), []
    for episode in episodes:
        times, values, segments, train = [], [], [], []
        for number, key in enumerate(episode["members"]):
            row = sources[key]
            ids = row["candidate_ids"]
            if len(ids) != len(set(ids)) or used.intersection(ids):
                raise ValueError("duplicate RF observations across episodes")
            used.update(ids)
            t, y = np.asarray(row["t_s"]), np.asarray(row["y_hz"])
            if len(t) != len(y) or len(t) != len(ids) or row["actual_rf_hz"] <= 0:
                raise ValueError("invalid source observation arrays / RF metadata")
            order = np.argsort(t, kind="stable")
            count = int(np.floor(len(t) * 0.6))
            if min(count, len(t) - count) < 2:
                raise ValueError("source too short for chronological split")
            for part, is_train in ((order[:count], True), (order[count:], False)):
                if max_per_partition and len(part) > max_per_partition:
                    part = part[
                        np.unique(
                            np.rint(np.linspace(0, len(part) - 1, max_per_partition)).astype(int)
                        )
                    ]
                times.extend(t[part])
                values.extend(y[part])
                segments.extend([number] * len(part))
                train.extend([is_train] * len(part))
        # y_hz is already RF-normalized to 11.2 GHz by fractional RF-only export.
        output.append(
            (
                str(episode["episode_id"]),
                ObservationArc(
                    np.array(times),
                    np.array(values),
                    np.array(segments),
                    np.array(train, dtype=bool),
                ),
            )
        )
    return output


def state_arrays(catalogue, indices, reference_ns, times, orbit_time_s=0.0, clock_s=0.0):
    receive_ns = reference_ns + np.rint((times + clock_s) * 1e9).astype(np.int64)
    orbit_ns = receive_ns + round(orbit_time_s * 1e9)
    grid = SamplingGrid(tuple(int(t) for t in orbit_ns), 0, 1.0)
    state = propagate_grid(catalogue, grid, indices)
    jd, fraction = julian_day_from_utc_ns(receive_ns)
    # Orbit-time adjustment changes the inertial orbit phase, not Earth rotation.
    p, v = teme_to_ecef(
        state.position_teme_km,
        state.velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(jd, fraction),
    )
    valid = np.all(state.error_code == 0, axis=1) & np.all(np.isfinite(p), axis=(1, 2))
    valid &= np.all(np.isfinite(v), axis=(1, 2))
    valid &= np.min(np.linalg.norm(p, axis=-1), axis=1) > 6478.137
    return p[valid], v[valid], np.asarray(indices)[valid]


def regional_catalogue(catalogue, reference_ns, region, clock_s=0.0):
    causal = [
        i
        for i, (name, epoch) in enumerate(
            zip(catalogue.names, catalogue.element_epoch_utc_ns(), strict=True)
        )
        if name.startswith("STARLINK") and epoch < reference_ns
    ]
    p, _, ids = state_arrays(
        catalogue, causal, reference_ns, np.arange(-10.0, 321.0, 30.0), clock_s=clock_s
    )
    central = region.points([0.0], [0.0]).ecef_km[0]
    central /= np.linalg.norm(central)
    radius = np.linalg.norm(p, axis=-1)
    cosine = np.sum(p / radius[..., None] * central, axis=-1)
    # Wide cap bounds the entire square, Earth flattening, sample spacing and
    # +/-2 s future sensitivity. This is only a computational prefilter.
    cap = np.arccos(6350.0 / radius) + np.hypot(region.width_km, region.height_km) / 2 / 6300.0
    cap += np.deg2rad(4.0)
    selected = ids[np.any(cosine >= np.cos(cap), axis=1)]
    return selected, len(causal)


def summarize_grid(grid, total, heldout):
    order = np.argsort(-total, kind="stable")
    best = int(order[0])
    modes = []
    for i in order:
        if all(
            np.hypot(grid.east_km[i] - row["east_km"], grid.north_km[i] - row["north_km"]) >= 50
            for row in modes
        ):
            modes.append(
                {
                    "index": int(i),
                    "east_km": float(grid.east_km[i]),
                    "north_km": float(grid.north_km[i]),
                    "latitude_deg": float(grid.latitude_deg[i]),
                    "longitude_deg": float(grid.longitude_deg[i]),
                    "delta_score": float(total[best] - total[i]),
                }
            )
        if len(modes) >= 12:
            break
    return {
        "best_index": best,
        "latitude_deg": float(grid.latitude_deg[best]),
        "longitude_deg": float(grid.longitude_deg[best]),
        "east_km": float(grid.east_km[best]),
        "north_km": float(grid.north_km[best]),
        "altitude_m": float(grid.altitude_m[best]),
        "train_score": float(total[best]),
        "heldout_score_at_train_best": float(heldout[best]),
        "cells_within_10_log_units": int(np.sum(total >= total[best] - 10)),
        "separated_modes": modes,
    }


def run(args):
    if args.output.exists():
        raise ValueError("output must be a fresh directory; never overwrite a completed experiment")
    if not args.max_per_partition >= 0 or args.max_per_partition == 1:
        raise ValueError("partition cap must be zero (all) or at least two")
    region = Region(args.center_lat, args.center_lon, args.region_size_km, args.region_size_km)
    if args.points:
        requested = json.loads(args.points.read_text())
        grid = region.points(
            np.array(requested["east_km"]),
            np.array(requested["north_km"]),
            np.array(requested.get("altitude_m", args.altitude_m)),
        )
    else:
        grid = region.grid(args.spacing_km, args.altitude_m, args.shifted_grid)
    config = ScoreConfig(signal_sigma_hz=args.sigma_hz, effective_count=args.effective_count)
    inventory_path = args.evidence / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    scans = sorted(
        [r for r in inventory["scans"] if r["included"]], key=lambda r: r["reference_utc_ns"]
    )
    if args.scan_limit:
        scans = scans[: args.scan_limit]
    args.output.mkdir(parents=True)
    configuration = {
        "region": asdict(region),
        "score": asdict(config),
        "spacing_km": args.spacing_km,
        "shifted_grid": args.shifted_grid,
        "altitude_m": args.altitude_m,
        "clock_s": args.clock_s,
        "max_per_partition": args.max_per_partition,
        "individual_sources": args.individual_sources,
        "inventory_digest": digest(inventory_path),
        "points_digest": digest(args.points) if args.points else None,
        "full_region_grid": args.points is None,
        "refinement_is_retrospective": args.points is not None,
        "scientific_status": "exploratory composite score, not calibrated confidence",
        "position_truth_used": False,
        "prior_matched_norads_used": False,
        "orbit_corrections_used": False,
        "rf_association_is_retrospective": True,
    }
    write_json(args.output / "configuration.json", configuration)
    np.savez_compressed(args.output / "grid.npz", **asdict(grid))
    total, heldout = np.zeros(len(grid)), np.zeros(len(grid))
    history, started = [], time.monotonic()
    for scan_index, row in enumerate(scans):
        evidence_path = args.evidence / "evidence" / f"{row['session_id']}.json"
        document = json.loads(evidence_path.read_text())
        metadata = document["inventory"]
        reference_ns = int(metadata["reference_utc_ns"])
        if reference_ns != row["reference_utc_ns"]:
            raise ValueError("inventory/evidence reference mismatch")
        if metadata["tle_collected_ns"] >= reference_ns - 5_000_000_000:
            raise ValueError("noncausal catalogue snapshot")
        tle_name = metadata["tle_file"]
        if Path(tle_name).name != tle_name:
            raise ValueError("catalogue must be an evidence-local file")
        tle_path = evidence_path.parent / tle_name
        if digest(tle_path) != metadata["tle_digest"]:
            raise ValueError("catalogue digest mismatch")
        catalogue = parse_element_sets(tle_path.read_text())
        selected, causal_count = regional_catalogue(catalogue, reference_ns, region, args.clock_s)
        arcs = load_observations(document, args.max_per_partition, args.individual_sources)
        scores, details = [], []
        for episode_id, arc in arcs:
            p, v, ids = state_arrays(
                catalogue, selected, reference_ns, arc.time_s, clock_s=args.clock_s
            )
            score = score_states(arc, p, v, grid, causal_count, config)
            numbers = np.array(catalogue.satellite_numbers)[ids]
            best = score.pop("best_index")
            score["best_norad"] = np.where(
                best >= 0, numbers[np.maximum(best, 0)] if len(numbers) else -1, -1
            )
            scores.append(score)
            details.append(
                {
                    "episode_id": episode_id,
                    "points": len(arc.time_s),
                    "segments": len(np.unique(arc.segment)),
                    "catalogue_count": len(ids),
                }
            )
        arrays = {key: np.array([score[key] for score in scores]) for key in scores[0]}
        scan_train = np.sum(arrays["train_logbf"], axis=0)
        scan_test = np.sum(arrays["heldout_logbf"], axis=0)
        previous_best = int(np.argmax(total)) if scan_index else None
        # Equal-area approximation only for this diagnostic integration. Grid
        # resolution sensitivity is reported; these are not credible intervals.
        predictive_previous_map = float(logsumexp(total + scan_test) - logsumexp(total))
        total += scan_train
        heldout += scan_test
        np.savez_compressed(args.output / f"{row['session_id']}.npz", **arrays)
        record = {
            "scan_index": scan_index,
            "session_id": row["session_id"],
            "reference_utc_ns": reference_ns,
            "source_digest": digest(evidence_path),
            "tle_digest": digest(tle_path),
            "causal_catalogue_count": causal_count,
            "regional_catalogue_count": len(selected),
            "episodes": details,
            "elapsed_s": time.monotonic() - started,
            "heldout_score_previous_best": float(scan_test[previous_best])
            if previous_best is not None
            else None,
            "heldout_score_previous_map": predictive_previous_map,
            **summarize_grid(grid, total, heldout),
        }
        history.append(record)
        write_json(args.output / "history.json", history)
        np.savez_compressed(args.output / "accumulated.npz", train=total, heldout=heldout)
        print(
            f"{scan_index + 1}/{len(scans)} {row['session_id']} {len(arcs)} episodes; "
            f"best {record['latitude_deg']:.5f},{record['longitude_deg']:.5f}; "
            f"elapsed {record['elapsed_s']:.1f}s",
            flush=True,
        )
    write_json(
        args.output / "result.json",
        {
            **configuration,
            **summarize_grid(grid, total, heldout),
            "scan_count": len(history),
            "episode_count": sum(len(r["episodes"]) for r in history),
            "elapsed_s": time.monotonic() - started,
            "complete": True,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--region-size-km", type=float, default=1000.0)
    parser.add_argument("--spacing-km", type=float, default=25.0)
    parser.add_argument("--altitude-m", type=float, default=0.0)
    parser.add_argument("--sigma-hz", type=float, default=250.0)
    parser.add_argument("--effective-count", type=float, default=6.0)
    parser.add_argument("--clock-s", type=float, default=0.0)
    parser.add_argument("--max-per-partition", type=int, default=8)
    parser.add_argument("--scan-limit", type=int)
    parser.add_argument("--shifted-grid", action="store_true")
    parser.add_argument("--individual-sources", action="store_true")
    parser.add_argument("--points", type=Path)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
