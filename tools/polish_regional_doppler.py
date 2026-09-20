#!/usr/bin/env python3
"""Local physical refinement of blind regional modes, with held-out evaluation.

Identities are frozen at a TRAINING-selected regional mode. No truth coordinate
or earlier known-site analysis is read. The orbit-time alternative shares one
correction per NORAD / TLE snapshot across every included segment and scan.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, load_observations, state_arrays, write_json

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    Region,
    fit_local_mode,
)
from leo.sky.propagation import parse_element_sets


def training_episode_gate(signal_weight, train_rms_hz, minimum_weight, maximum_rms_hz):
    if not 0 <= minimum_weight <= 1 or not maximum_rms_hz > 0:
        raise ValueError("invalid training-only episode gate")
    return (np.asarray(signal_weight) >= minimum_weight) & (
        np.asarray(train_rms_hz) <= maximum_rms_hz
    )


def candidate_elevation_deg(position_km, receiver_km, receiver_up):
    delta = np.asarray(position_km) - np.asarray(receiver_km)
    sine = np.sum(delta * receiver_up, axis=-1) / np.linalg.norm(delta, axis=-1)
    return np.rad2deg(np.arcsin(np.clip(sine, -1, 1)))


def polish(
    run,
    evidence,
    output,
    fit_height=False,
    min_signal_weight=0.95,
    max_train_rms_hz=500.0,
    min_training_elevation_deg=-90.0,
):
    if output.exists():
        raise ValueError("fresh output required")
    training_episode_gate([], [], min_signal_weight, max_train_rms_hz)
    if not -90 <= min_training_elevation_deg <= 90:
        raise ValueError("invalid training elevation gate")
    parent = json.loads((run / "result.json").read_text())
    if not parent["complete"] or parent["position_truth_used"]:
        raise ValueError("finished blind parent run required")
    region = Region(**parent["region"])
    parent_point = region.points([parent["east_km"]], [parent["north_km"]], parent["altitude_m"])
    history = json.loads((run / "history.json").read_text())
    index = parent["best_index"]
    catalogues, groups, records = {}, {}, []
    frequencies, segment, train, orbit_group = [], [], [], []
    offset, segment_count = 0, 0
    for scan in history:
        path = evidence / "evidence" / f"{scan['session_id']}.json"
        if digest(path) != scan["source_digest"]:
            raise ValueError("source changed since blind search")
        document = json.loads(path.read_text())
        metadata = document["inventory"]
        tle_path = path.parent / metadata["tle_file"]
        if digest(tle_path) != scan["tle_digest"]:
            raise ValueError("catalogue changed since blind search")
        key = metadata["tle_digest"]
        if key not in catalogues:
            catalogue = parse_element_sets(tle_path.read_text())
            catalogues[key] = (catalogue, {n: i for i, n in enumerate(catalogue.satellite_numbers)})
        catalogue, numbers = catalogues[key]
        saved = np.load(run / f"{scan['session_id']}.npz")
        # Gate is predeclared and uses no held-out or known-site evidence.
        keep = training_episode_gate(
            saved["signal_weight"][:, index],
            saved["best_train_rms_hz"][:, index],
            min_signal_weight,
            max_train_rms_hz,
        )
        arcs = load_observations(document, 0, parent["individual_sources"])
        for j, (episode_id, arc) in enumerate(arcs):
            if not keep[j]:
                continue
            norad = int(saved["best_norad"][j, index])
            training_indices = np.flatnonzero(arc.training)
            training_middle = training_indices[len(training_indices) // 2]
            sky_position, _, sky_ids = state_arrays(
                catalogue,
                [numbers[norad]],
                metadata["reference_utc_ns"],
                arc.time_s,
                clock_s=parent["clock_s"],
            )
            if len(sky_ids) != 1:
                continue
            training_elevation_deg = float(
                candidate_elevation_deg(
                    sky_position[0, training_middle],
                    parent_point.ecef_km[0],
                    parent_point.up[0],
                )
            )
            if training_elevation_deg < min_training_elevation_deg:
                continue
            group_key = (key, norad)
            group = groups.setdefault(group_key, len(groups))
            n = len(arc.time_s)
            records.append(
                {
                    "slice": slice(offset, offset + n),
                    "catalogue": catalogue,
                    "index": numbers[norad],
                    "reference_ns": metadata["reference_utc_ns"],
                    "time_s": arc.time_s,
                    "group": group,
                    "norad": norad,
                    "episode_id": episode_id,
                    "session_id": scan["session_id"],
                    "tle_digest": key,
                    "segments": len(np.unique(arc.segment)),
                    "training_elevation_deg": training_elevation_deg,
                }
            )
            frequencies.extend(arc.frequency_hz)
            segment.extend(arc.segment + segment_count)
            train.extend(arc.training)
            orbit_group.extend([group] * n)
            segment_count += len(np.unique(arc.segment))
            offset += n
    if len(groups) < 3:
        raise ValueError("insufficient independently assigned orbit groups for local fit")
    cache_key, cache = None, None

    def predict(position, shifts):
        nonlocal cache_key, cache
        shift_key = shifts.tobytes()
        if shift_key != cache_key:
            p, v = np.empty((offset, 3)), np.empty((offset, 3))
            for record in records:
                pp, vv, ids = state_arrays(
                    record["catalogue"],
                    [record["index"]],
                    record["reference_ns"],
                    record["time_s"],
                    shifts[record["group"]],
                    parent["clock_s"],
                )
                if len(ids) != 1:
                    raise ValueError("chosen satellite state is invalid")
                p[record["slice"]], v[record["slice"]] = pp[0], vv[0]
            cache, cache_key = (p, v), shift_key
        p, v = cache
        altitude = position[2] * 1000 if len(position) == 3 else parent["altitude_m"]
        receiver = region.points([position[0]], [position[1]], altitude).ecef_km[0]
        delta = p - receiver
        return (
            -REFERENCE_RF_HZ
            / LIGHT_KM_S
            * np.sum(delta * v, axis=-1)
            / np.linalg.norm(delta, axis=-1)
        )

    initial = [parent["east_km"], parent["north_km"]]
    lower = [-region.width_km / 2, -region.height_km / 2]
    upper = [region.width_km / 2, region.height_km / 2]
    if fit_height:
        initial.append(parent["altitude_m"] / 1000)
        lower.append(-0.5)
        upper.append(5.0)
    results = []
    for timing in (False, True):
        answer = fit_local_mode(
            np.array(frequencies),
            np.array(segment),
            np.array(train, bool),
            np.array(orbit_group),
            predict,
            initial,
            lower,
            upper,
            fit_orbit_time=timing,
        )
        x = answer["position_km"]
        lat, lon = region.coordinates(x[0], x[1])
        answer.update(
            {
                "latitude_deg": float(lat),
                "longitude_deg": float(lon),
                "fit_orbit_time": timing,
                "fit_height": fit_height,
                "orbit_sigma_s": 0.5,
                "orbit_bound_s": 2.0,
                "height_prior_sigma_m": 1000 if fit_height else None,
            }
        )
        results.append(answer)
        print(
            f"{run.name} {'bounded-time' if timing else 'nominal'}: {lat:.7f},{lon:.7f}; "
            f"held-out {answer['heldout_rms_hz']:.1f} Hz; converged {answer['converged']}",
            flush=True,
        )
    write_json(
        output,
        {
            "parent_run": run.name,
            "parent_result_digest": digest(run / "result.json"),
            "region": as_region(region),
            "position_truth_used": False,
            "identity_source": (
                "site-conditioned catalogue candidates; not blind geolocation"
                if parent.get("prior_matched_norads_used")
                else "blind regional training mode"
            ),
            "prior_matched_norads_used": parent.get("prior_matched_norads_used", False),
            "catalogue_minimum_elevation_deg": parent.get("score", {}).get(
                "minimum_elevation_deg", -1.0
            ),
            "training_only_episode_gate": {
                "minimum_signal_weight": min_signal_weight,
                "maximum_training_rms_hz": max_train_rms_hz,
                "minimum_training_elevation_deg": min_training_elevation_deg,
            },
            "point_count": offset,
            "source_segment_count": segment_count,
            "orbit_group_count": len(groups),
            "episode_count": len(records),
            "full_sample_polish": True,
            "complete": True,
            "models": results,
            "assignments": [
                {
                    k: r[k]
                    for k in (
                        "norad",
                        "group",
                        "episode_id",
                        "session_id",
                        "tle_digest",
                        "training_elevation_deg",
                    )
                }
                for r in records
            ],
        },
    )


def as_region(region):
    return {
        "latitude_deg": region.latitude_deg,
        "longitude_deg": region.longitude_deg,
        "width_km": region.width_km,
        "height_km": region.height_km,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fit-height", action="store_true")
    parser.add_argument("--min-signal-weight", type=float, default=0.95)
    parser.add_argument("--max-train-rms-hz", type=float, default=500.0)
    parser.add_argument("--min-training-elevation-deg", type=float, default=-90.0)
    args = parser.parse_args()
    polish(
        args.run,
        args.evidence,
        args.output,
        args.fit_height,
        args.min_signal_weight,
        args.max_train_rms_hz,
        args.min_training_elevation_deg,
    )


if __name__ == "__main__":
    main()
