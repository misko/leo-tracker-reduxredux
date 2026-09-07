#!/usr/bin/env python3
"""Recurrence, edge cross-validation, channel handoffs, and conditional positioning."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from evaluate_scan_pnt_cohort import OBSERVER, make_arc, write_json

from leo.analysis.research.scan_pnt_experiment import (
    Arc,
    doppler_from_ecef,
    fit_position,
    polynomial_fit,
    remove_offsets,
    segment_rms,
    split_segments,
)
from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

BASE = geodetic_to_ecef_km(OBSERVER.latitude_deg, OBSERVER.longitude_deg, OBSERVER.altitude_m)
ENU = ecef_to_enu_matrix(OBSERVER.latitude_deg, OBSERVER.longitude_deg)


def states(satellite, reference_ns: int, time_s: np.ndarray, tau: float = 0) -> tuple:
    utc_ns = reference_ns + np.rint((time_s + tau) * 1e9).astype(np.int64)
    jd, fraction = julian_day_from_utc_ns(utc_ns)
    errors, position, velocity = satellite.sgp4_array(jd, fraction)
    if np.any(errors):
        raise ValueError("SGP4 failed for selected satellite")
    return teme_to_ecef(position, velocity, greenwich_mean_sidereal_time_rad(jd, fraction))


def compare_edges(document: dict) -> list[dict]:
    output = []
    for merge in document["edge_merges"]:
        arc = make_arc(document, [merge["left_tracklet_id"], merge["right_tracklet_id"]])
        train, test = split_segments(arc)
        shared = polynomial_fit(arc, 3, train)
        names = np.unique(arc.segment)
        midpoint = (
            max(arc.time_s[arc.segment == name].min() for name in names)
            + min(arc.time_s[arc.segment == name].max() for name in names)
        ) / 2
        full = polynomial_fit(arc, 3, np.ones(len(train), bool), derivative_time_s=midpoint)
        separate_residual = np.zeros(len(train))
        separate_rates = []
        for name in np.unique(arc.segment):
            mask = arc.segment == name
            piece = Arc(arc.time_s[mask], arc.frequency_hz[mask], arc.segment[mask])
            fit = polynomial_fit(piece, 3, train[mask])
            separate_residual[mask] = fit["residual_hz"]
            separate_rates.append(
                polynomial_fit(piece, 3, np.ones(mask.sum(), bool), derivative_time_s=midpoint)[
                    "rate_se_hz_s"
                ]
            )
        output.append(
            {
                "channel": merge["channel"],
                "receiver": merge["receiver"],
                "overlap_s": merge["overlap_s"],
                "independent_heldout_rms_hz": float(
                    segment_rms(separate_residual, arc.segment, test)
                ),
                "shared_heldout_rms_hz": float(
                    segment_rms(shared["residual_hz"], arc.segment, test)
                ),
                "scaled_design_rate_precision_gain": float(
                    np.mean(separate_rates) / full["rate_se_hz_s"]
                ),
                "legacy_reported_rate_precision_gain": merge["rate_resolution_gain"],
                "full_rate_se_hz_s": full["rate_se_hz_s"],
            }
        )
    return output


def polynomial_predict(
    source: Arc, target: Arc, source_training: np.ndarray, reference_delta_s: float, degree: int
) -> np.ndarray:
    names = np.unique(source.segment)
    reference = np.mean(source.time_s[source_training])
    scale = max(float(np.ptp(source.time_s[source_training])), 1)
    x = (source.time_s - reference) / scale
    design = np.column_stack(
        [*(source.segment == name for name in names), *(x**d for d in range(1, degree + 1))]
    )
    coef = np.linalg.lstsq(
        design[source_training], source.frequency_hz[source_training], rcond=None
    )[0]
    target_x = (target.time_s + reference_delta_s - reference) / scale
    return sum(coef[len(names) + d - 1] * target_x**d for d in range(1, degree + 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    results = [json.loads(path.read_text()) for path in (output / "results").glob("*.json")]
    results.sort(key=lambda row: row["inventory"]["reference_utc_ns"])
    docs, satellites = {}, {}
    for row in results:
        sid = row["session_id"]
        docs[sid] = json.loads((output / "evidence" / f"{sid}.json").read_text())
        cat = parse_element_sets((output / "evidence" / row["inventory"]["tle_file"]).read_text())
        satellites[sid] = dict(zip(cat.satellite_numbers, cat.satellites, strict=True))

    edges, conflicts, handoffs, positioning = [], [], [], []
    pools = []
    recurrence = defaultdict(list)
    for row in results:
        sid = row["session_id"]
        doc = docs[sid]
        reference_ns = row["inventory"]["reference_utc_ns"]
        edge_rows = compare_edges(doc)
        edges.extend({"session_id": sid, **item} for item in edge_rows)
        candidates = [ep for ep in row["episodes"] if ep["match"]["candidate_pass"]]
        grouped = defaultdict(list)
        for ep in candidates:
            grouped[ep["match"]["primary"]["norad"]].append(ep)
            recurrence[ep["match"]["primary"]["norad"]].append((row, ep))
        conflicted = set()
        for norad, episodes in grouped.items():
            for i, a in enumerate(episodes):
                for b in episodes[i + 1 :]:
                    overlap = min(a["support_s"][1], b["support_s"][1]) - max(
                        a["support_s"][0], b["support_s"][0]
                    )
                    if a["channel"] != b["channel"] and overlap > 1.05:
                        conflicts.append(
                            {
                                "session_id": sid,
                                "norad": norad,
                                "episodes": [a["episode_id"], b["episode_id"]],
                                "channels": [a["channel"], b["channel"]],
                                "overlap_s": overlap,
                            }
                        )
                        conflicted.add(norad)
        by_id = {item["episode_id"]: item for item in row["episodes"]}
        for join in row["joins"]:
            left, right = by_id[join["left_track_id"]], by_id[join["right_track_id"]]
            if not join["supported"]:
                continue
            left_arc, right_arc = make_arc(doc, left["members"]), make_arc(doc, right["members"])
            left_train, _ = split_segments(left_arc)
            calibration, evaluation = split_segments(right_arc, 0.4)
            chosen = left["match"]["primary"]
            sat = satellites[sid][chosen["norad"]]
            pos, vel = states(sat, reference_ns, right_arc.time_s, chosen["tau_s"])
            predicted = doppler_from_ecef(pos, vel, BASE)
            residual = remove_offsets(
                right_arc.frequency_hz - predicted, right_arc.segment, calibration
            )
            tle_rms = float(segment_rms(residual, right_arc.segment, evaluation))
            nulls = []
            for degree in (1, 2, 3):
                prediction = polynomial_predict(left_arc, right_arc, left_train, 0, degree)
                residual = remove_offsets(
                    right_arc.frequency_hz - prediction, right_arc.segment, calibration
                )
                nulls.append(float(segment_rms(residual, right_arc.segment, evaluation)))
            handoffs.append(
                {
                    "session_id": sid,
                    "left": left["episode_id"],
                    "right": right["episode_id"],
                    "norad_from_left_training": chosen["norad"],
                    "right_independent_training_norad": right["match"]["primary"]["norad"],
                    "tau_from_left_s": chosen["tau_s"],
                    "tle_heldout_hz": tle_rms,
                    "polynomial_heldout_hz": nulls,
                    "supported": bool(
                        left["match"]["candidate_pass"]
                        and chosen["norad"] == right["match"]["primary"]["norad"]
                        and tle_rms <= 200
                        and tle_rms < min(nulls)
                    ),
                }
            )

        # One longest episode per distinct, channel-consistent NORAD avoids repetition weight.
        selected = [
            max(eps, key=lambda ep: ep["support_s"][1] - ep["support_s"][0])
            for number, eps in grouped.items()
            if number not in conflicted
        ]
        if len(selected) < 3:
            positioning.append(
                {
                    "session_id": sid,
                    "included": False,
                    "reason": "fewer than three channel-consistent NORAD candidates",
                }
            )
            continue
        observed, segments, train_rows, position0, velocity0, position_tau, velocity_tau = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        rate_columns = []
        for ep in selected:
            arc = make_arc(doc, ep["members"])
            chosen = ep["match"]["primary"]
            sat = satellites[sid][chosen["norad"]]
            p0, v0 = states(sat, reference_ns, arc.time_s)
            pt, vt = states(sat, reference_ns, arc.time_s, chosen["tau_s"])
            pm, vm = states(sat, reference_ns, arc.time_s, -0.1)
            pp, vp = states(sat, reference_ns, arc.time_s, 0.1)
            rates = (doppler_from_ecef(pp, vp, BASE) - doppler_from_ecef(pm, vm, BASE)) / 0.2
            rate_columns.append(rates)
            observed.append(arc.frequency_hz)
            segments.append(arc.segment)
            train_rows.append(split_segments(arc)[0])
            position0.append(p0)
            velocity0.append(v0)
            position_tau.append(pt)
            velocity_tau.append(vt)
        y, segment, training = (
            np.concatenate(observed),
            np.concatenate(segments),
            np.concatenate(train_rows),
        )
        p0, v0, pt, vt = map(np.concatenate, (position0, velocity0, position_tau, velocity_tau))
        nuisance = np.zeros((len(y), len(selected)))
        offset = 0
        for j, rates in enumerate(rate_columns):
            nuisance[offset : offset + len(rates), j] = rates
            offset += len(rates)
        pools.append(
            {
                "session_id": sid,
                "y": y,
                "segment": segment,
                "training": training,
                "p0": p0,
                "v0": v0,
                "pt": pt,
                "vt": vt,
                "nuisance": nuisance,
            }
        )
        modes = []
        for name, p, v, dimensions, tau_columns in (
            ("nominal_2d", p0, v0, 2, None),
            ("known_site_tau_2d", pt, vt, 2, None),
            ("nominal_3d", p0, v0, 3, None),
            ("joint_bounded_tau_2d", p0, v0, 2, nuisance),
        ):
            fits = [
                fit_position(
                    y,
                    segment,
                    p,
                    v,
                    BASE,
                    ENU,
                    np.array(initial),
                    training=training,
                    dimensions=dimensions,
                    nuisance=tau_columns,
                    nuisance_bound=2.0,
                )
                for initial in ((10, -10, 2), (-10, 10, -2))
            ]
            modes.append({"mode": name, "solutions": fits})
        # Drop-one-satellite stability uses the same frozen associations.
        leave_one = []
        if len(selected) >= 4:
            start = 0
            for ep, part in zip(selected, observed, strict=True):
                keep = np.ones(len(y), bool)
                keep[start : start + len(part)] = False
                start += len(part)
                fit = fit_position(
                    y[keep],
                    segment[keep],
                    p0[keep],
                    v0[keep],
                    BASE,
                    ENU,
                    np.array([10, -10]),
                    training=training[keep],
                )
                leave_one.append({"omitted_norad": ep["match"]["primary"]["norad"], **fit})
        positioning.append(
            {
                "session_id": sid,
                "included": True,
                "norad_count": len(selected),
                "norads": [ep["match"]["primary"]["norad"] for ep in selected],
                "episode_ids": [ep["episode_id"] for ep in selected],
                "observation_count": len(y),
                "modes": modes,
                "leave_one_satellite_out": leave_one,
            }
        )
        print(
            f"position {sid}: {len(selected)} NORADs, nominal="
            f"{modes[0]['solutions'][0]['horizontal_error_m']:.0f}m, bounded tau="
            f"{modes[3]['solutions'][0]['horizontal_error_m']:.0f}m",
            flush=True,
        )

    pooled_results = []
    for count in sorted({min(n, len(pools)) for n in (3, 6, 12, 18, len(pools))}):
        selected_pools = pools[:count]
        y, segment, training, p0, v0, pt, vt = [
            np.concatenate([part[key] for part in selected_pools])
            for key in ("y", "segment", "training", "p0", "v0", "pt", "vt")
        ]
        modes = []
        for name, p, v, robust in (
            ("nominal", p0, v0, False),
            ("robust_nominal", p0, v0, True),
            ("known_site_tau", pt, vt, False),
        ):
            fit = fit_position(
                y, segment, p, v, BASE, ENU, np.array([10, -10]), training=training, robust=robust
            )
            future_residuals = []
            observer = BASE + np.array(fit["enu_km"]) @ ENU[:2]
            for future in pools[count:]:
                position_key, velocity_key = (
                    ("pt", "vt") if name == "known_site_tau" else ("p0", "v0")
                )
                predicted = doppler_from_ecef(future[position_key], future[velocity_key], observer)
                residual = remove_offsets(
                    future["y"] - predicted, future["segment"], future["training"]
                )
                future_residuals.extend(residual[~future["training"]].tolist())
            modes.append(
                {
                    "mode": name,
                    **fit,
                    "future_scan_heldout_rms_hz": float(
                        np.sqrt(np.mean(np.square(future_residuals)))
                    )
                    if future_residuals
                    else None,
                }
            )
        pooled_results.append(
            {
                "scan_count": count,
                "session_ids": [p["session_id"] for p in selected_pools],
                "modes": modes,
            }
        )

    simulation = []
    if pools:
        # Exact ephemerides/identities on real geometry: isolates noise-limited solver behavior.
        fixture = pools[len(pools) // 2]
        ideal = doppler_from_ecef(fixture["p0"], fixture["v0"], BASE)
        for noise_type in ("independent_100hz", "five_sample_correlated_100hz"):
            for seed in range(20):
                rng = np.random.default_rng(seed + 100)
                noise = rng.normal(0, 100, len(ideal))
                if noise_type.startswith("five"):
                    for name in np.unique(fixture["segment"]):
                        indices = np.flatnonzero(fixture["segment"] == name)
                        noise[indices] = np.repeat(rng.normal(0, 100, (len(indices) + 4) // 5), 5)[
                            : len(indices)
                        ]
                fit = fit_position(
                    ideal + noise,
                    fixture["segment"],
                    fixture["p0"],
                    fixture["v0"],
                    BASE,
                    ENU,
                    np.array([10, -10]),
                    training=fixture["training"],
                )
                simulation.append(
                    {
                        "noise_type": noise_type,
                        "seed": seed,
                        "geometry_session": fixture["session_id"],
                        **fit,
                    }
                )

    recurrences = []
    for number, hits in recurrence.items():
        if len({row["session_id"] for row, ep in hits}) < 2:
            continue
        hits.sort(
            key=lambda pair: (
                pair[0]["inventory"]["reference_utc_ns"] + round(pair[1]["support_s"][0] * 1e9)
            )
        )
        first, earlier = hits[0]
        old_sid = first["session_id"]
        old_reference = first["inventory"]["reference_utc_ns"]
        earlier_arc = make_arc(docs[old_sid], earlier["members"])
        earlier_training = split_segments(earlier_arc)[0]
        old_sat = satellites[old_sid][number]
        for later, episode in hits[1:]:
            if later["session_id"] == old_sid:
                continue
            reference = later["inventory"]["reference_utc_ns"]
            arc = make_arc(docs[later["session_id"]], episode["members"])
            training, evaluation = split_segments(arc)
            scores = []
            for tau in (0, earlier["match"]["primary"]["tau_s"]):
                p, v = states(old_sat, reference, arc.time_s, tau)
                residual = remove_offsets(
                    arc.frequency_hz - doppler_from_ecef(p, v, BASE), arc.segment, training
                )
                scores.append(float(segment_rms(residual, arc.segment, evaluation)))
            nulls = []
            for degree in (1, 2, 3):
                predicted = polynomial_predict(
                    earlier_arc, arc, earlier_training, (reference - old_reference) / 1e9, degree
                )
                residual = remove_offsets(arc.frequency_hz - predicted, arc.segment, training)
                nulls.append(float(segment_rms(residual, arc.segment, evaluation)))
            recurrences.append(
                {
                    "norad": number,
                    "name": episode["match"]["name"],
                    "earlier_session": old_sid,
                    "later_session": later["session_id"],
                    "earlier_episode": earlier["episode_id"],
                    "later_episode": episode["episode_id"],
                    "gap_hours": (reference - old_reference) / 3.6e12,
                    "old_tau_s": earlier["match"]["primary"]["tau_s"],
                    "later_tau_s": episode["match"]["primary"]["tau_s"],
                    "frozen_old_tle_nominal_heldout_hz": scores[0],
                    "frozen_old_tle_tau_heldout_hz": scores[1],
                    "updated_tle_refit_heldout_hz": episode["match"]["primary"]["heldout_rms_hz"],
                    "old_polynomial_heldout_hz": nulls,
                    "same_snapshot": first["inventory"]["tle_digest"]
                    == later["inventory"]["tle_digest"],
                }
            )
    write_json(
        output / "longitudinal.json",
        {
            "edge_validation": edges,
            "conflicts": conflicts,
            "handoffs": handoffs,
            "positioning": positioning,
            "recurrences": recurrences,
            "pooled_positioning": pooled_results,
            "synthetic_positioning": simulation,
        },
    )


if __name__ == "__main__":
    main()
