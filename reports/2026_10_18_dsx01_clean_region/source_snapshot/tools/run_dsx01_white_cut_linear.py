"""Iterate linear geometry using baseline white-residual gates before search."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_cut_linear import bounded_scalar_newton
from probe_dsx01_cut_linear import OUTPUT, CutScore, prepare
from prototype_dsx01_continuous_position import CENTER, GRID, latlon
from report_dsx01_cut_linear import curved_metrics, linear_metrics


def keep_white(nominations, passing_components):
    """Preserve identities and aliases, accepting only a fixed baseline subset."""
    return [
        dict(r, accepted=r["accepted"] and r["component"] in passing_components)
        for r in nominations
    ]


def run(case):
    scan, parent, problems, nominations, source = prepare(case)
    baseline = problems["c0"]
    x = np.asarray(parent["c0"]["parameters"])
    curved = curved_metrics(baseline, parent["c0"], x)
    owners = {}
    for r in curved["tracks"]:
        if r["compatible"]:
            t = next(t for t in scan.tracks if t["key"] == r["component"])
            owners.setdefault(r["candidate_index"], set()).add((t["receiver"], t["channel"]))
    candidates = [r for r in nominations if r["accepted"]]
    metrics = linear_metrics(baseline, x, candidates)
    passing = {
        r["component"]
        for r in metrics
        if r["compatible"] and len(owners.get(r["candidate_index"], set())) >= 2
    }
    selected = keep_white(nominations, passing)
    directory = OUTPUT / case
    write(directory / "white_nominations.json", selected)
    write(directory / "white_baseline_gates.json", metrics)
    write(
        directory / "white_protocol.json",
        dict(
            region_center=CENTER,
            box_width_km=25,
            grid=GRID,
            common_c0_selected_starts=3,
            iterations_per_start=24,
            no_GPS_or_future_TLE_in_fit=True,
            linear_labels_aliases_noise_and_gates_frozen_before_search=True,
            baseline_white_gates_are_not_reselected_at_trial_positions=True,
            calibration_from_original_curved_data_only=True,
            matched_c0_and_fitted_c_observations=True,
            parent_endpoint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            source_sha256={
                str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in (
                    Path(__file__),
                    Path(__file__).with_name("dsx01_cut_linear.py"),
                    Path(__file__).with_name("probe_dsx01_cut_linear.py"),
                )
            },
        ),
    )
    scores = {arm: CutScore(p, selected, "joint") for arm, p in problems.items()}
    anchor = tuple(parent["c0"]["parameters"])
    grid = [
        dict(parameters=point, score=scores["c0"].score(point)["total"])
        for point in sorted(set(GRID) | {anchor})
    ]
    starts = sorted(grid, key=lambda r: r["score"])[:3]
    if not any(tuple(r["parameters"]) == anchor for r in starts):
        starts[-1] = next(r for r in grid if tuple(r["parameters"]) == anchor)
    fits = {}
    for arm, score in scores.items():
        attempts = [
            bounded_scalar_newton(
                lambda x, score=score: score.score(x)["total"], start["parameters"]
            )
            for start in starts
        ]
        best = min(attempts, key=lambda r: r["score"])
        x = np.asarray(best["parameters"])
        fits[arm] = dict(
            **best,
            latitude_deg=latlon(x)[0],
            longitude_deg=latlon(x)[1],
            starts=starts,
            grid=grid,
            attempts=attempts,
            parts=score.score(x),
            selected_linear_tracks=len(score.selected),
            selected_linear_points=sum(r["points"] for r in score.selected),
            curved_calibration_state=problems[arm].state(x),
        )
    write(directory / "white_endpoints.json", fits)
    print(
        json.dumps(
            dict(case=case, endpoints={a: f["parameters"].tolist() for a, f in fits.items()})
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    run(parser.parse_args().case)
