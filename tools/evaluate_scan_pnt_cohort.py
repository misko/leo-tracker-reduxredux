#!/usr/bin/env python3
"""Evaluate exported scan evidence and causal catalogues without accessing live storage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.scan_pnt_experiment import (
    Arc,
    interpolate_bank,
    match_catalogue,
    polynomial_comparison,
    remove_offsets,
    screen_candidate,
    split_segments,
)
from leo.contracts.sky import ObserverSiteV1
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid

OBSERVER = ObserverSiteV1(
    latitude_deg=37.858988,
    longitude_deg=-122.478103,
    altitude_m=-29.0,
    label="Spinnaker, Sausalito",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sampling(reference_ns: int, times: np.ndarray) -> SamplingGrid:
    return SamplingGrid(
        tuple(int(reference_ns) + round(float(t) * 1e9) for t in times),
        len(times) // 2,
        float(times[1] - times[0]),
    )


def orbit_bank(
    payload: str, reference_ns: int, observer: ObserverSiteV1 = OBSERVER, wrong_time_s: float = 0.0
) -> dict:
    catalogue = parse_element_sets(payload)
    causal = [
        i
        for i, (name, epoch) in enumerate(
            zip(catalogue.names, catalogue.element_epoch_utc_ns(), strict=True)
        )
        if name.startswith("STARLINK") and epoch < reference_ns
    ]
    times = np.arange(-6, 307, 2.0)
    grid = sampling(reference_ns, times + wrong_time_s)
    coarse = observe_grid(propagate_grid(catalogue, grid, indices=causal), observer, grid)
    plausible = (
        coarse.usable
        & (coarse.altitude_km.min(axis=1) > 100)
        & (coarse.elevation_deg.max(axis=1) >= -1.5)
    )
    selected = np.array(causal)[plausible]
    times = np.arange(-6, 307, 0.25)
    grid = sampling(reference_ns, times + wrong_time_s)
    fine = observe_grid(propagate_grid(catalogue, grid, indices=selected.tolist()), observer, grid)
    usable = fine.usable & (fine.altitude_km.min(axis=1) > 100)
    selected = selected[usable]
    return {
        "times": times,
        "numbers": np.array(catalogue.satellite_numbers)[selected],
        "names": np.array(catalogue.names)[selected],
        "indices": selected,
        "doppler": doppler_shift_hz(11.2e9, fine.range_rate_km_s[usable]),
        "elevation": fine.elevation_deg[usable],
        "causal_count": len(causal),
    }


def make_arc(document: dict, members: list[str]) -> Arc:
    source = {row["tracklet_id"]: row for row in document["series"]}
    t = np.concatenate([source[name]["t_s"] for name in members])
    y = np.concatenate([source[name]["y_hz"] for name in members])
    segment = np.concatenate([[name] * len(source[name]["t_s"]) for name in members])
    order = np.argsort(t, kind="stable")
    return Arc(t[order], y[order], segment[order])


def score_arc(arc: Arc, bank: dict, polynomial: dict, *, wide: bool = True) -> dict:
    support = (bank["times"] >= arc.time_s.min()) & (bank["times"] <= arc.time_s.max())
    # Only train-time visibility admits a candidate. The wide bound is not selected by holdout.
    training, _ = split_segments(arc)
    train_elevation = interpolate_bank(bank["elevation"], bank["times"], arc.time_s[training])
    visible = np.flatnonzero(np.max(train_elevation, axis=1) >= 0)
    if visible.size < 2 or not np.any(support):
        raise ValueError("fewer than two visible causal objects")
    taus = np.arange(-5 if wide else -2, 5.125 if wide else 2.125, 0.25)
    result, _ = match_catalogue(
        arc, bank["doppler"][visible], bank["times"], taus, bank["numbers"][visible]
    )
    row = np.flatnonzero(bank["numbers"] == result["primary"]["norad"])[0]
    prediction = interpolate_bank(
        bank["doppler"][[row]], bank["times"], arc.time_s + result["primary"]["tau_s"]
    )[0]
    residual = remove_offsets(arc.frequency_hz - prediction, arc.segment, training)
    result["name"] = str(bank["names"][row])
    result["candidate_pass"] = screen_candidate(result, polynomial, float(np.ptp(arc.time_s)))
    result["peak_elevation_deg"] = float(np.max(bank["elevation"][row, support]))
    result["residual_hz"] = residual.tolist()
    return result


def evaluate_document(path: Path, output: Path, *, controls: bool = True) -> None:
    document = json.loads(path.read_text())
    capture = document["inventory"]
    session_id = capture["session_id"]
    dest = output / "results" / f"{session_id}.json"
    if dest.exists():
        print(f"cached {session_id}", flush=True)
        return
    payload = (path.parent / capture["tle_file"]).read_text()
    bank = orbit_bank(payload, capture["reference_utc_ns"])
    episodes = []
    for episode in document["episodes"]:
        arc = make_arc(document, episode["members"])
        polynomial = polynomial_comparison(arc)
        match = score_arc(arc, bank, polynomial)
        episodes.append(
            {
                **episode,
                "point_count": len(arc.time_s),
                "polynomial": polynomial,
                "match": match,
                "controls": [],
            }
        )
    joins = []
    by_id = {item["episode_id"]: item for item in document["episodes"]}
    for join in document["joins"]:
        left, right = by_id[join["left_track_id"]], by_id[join["right_track_id"]]
        arc = make_arc(document, left["members"] + right["members"])
        polynomial = polynomial_comparison(arc)
        match = score_arc(arc, bank, polynomial)
        joins.append({**join, "polynomial": polynomial, "match": match})
    for shift in (-600, 600) if controls else ():
        control_bank = orbit_bank(payload, capture["reference_utc_ns"], wrong_time_s=shift)
        for episode in episodes:
            arc = make_arc(document, episode["members"])
            control = score_arc(arc, control_bank, episode["polynomial"], wide=False)
            control.pop("residual_hz")
            episode["controls"].append({"wrong_time_s": shift, **control})
    write_json(
        dest,
        {
            "session_id": session_id,
            "inventory": capture,
            "causal_count": bank["causal_count"],
            "episodes": episodes,
            "joins": joins,
        },
    )
    passes = sum(item["match"]["candidate_pass"] for item in episodes)
    false_passes = sum(control["candidate_pass"] for ep in episodes for control in ep["controls"])
    print(
        f"scored {session_id}: {len(episodes)} episodes, {passes} candidates, "
        f"{false_passes} wrong-time candidates, {len(joins)} joins",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index", type=int)
    parser.add_argument("--no-controls", action="store_true")
    args = parser.parse_args()
    inventory = json.loads((args.output / "inventory.json").read_text())
    scans = [row for row in inventory["scans"] if row["included"]]
    if args.index is not None:
        scans = [scans[args.index]]
    for scan in scans:
        evaluate_document(
            args.output / "evidence" / f"{scan['session_id']}.json",
            args.output,
            controls=not args.no_controls,
        )


if __name__ == "__main__":
    main()
