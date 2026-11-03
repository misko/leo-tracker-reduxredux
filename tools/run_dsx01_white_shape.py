"""Matched strict-subset control for the offset-insensitive transfer variant."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_cut_linear import bounded_scalar_newton
from probe_dsx01_cut_linear import OUTPUT, CutScore, prepare
from prototype_dsx01_continuous_position import GRID, latlon


def run(case):
    _, parent, problems, _, source = prepare(case)
    directory = OUTPUT / case
    path = directory / "white_nominations.json"
    nominations = json.loads(path.read_text())
    scores = {arm: CutScore(p, nominations, "shape") for arm, p in problems.items()}
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
    write(directory / "white_shape_endpoints.json", fits)
    write(
        directory / "white_shape_protocol.json",
        dict(
            same_white_nominations_as_white_joint=True,
            white_nominations_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            parent_endpoint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            independent_linear_bias_sigma_hz=1e6,
            linear_noise_sigma_hz=150,
            shared_c0_starts=3,
            iterations_per_start=24,
            box_width_km=25,
            curved_calibration_only=True,
            no_GPS_or_future_TLE_in_fit=True,
            source_sha256={
                str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in [
                    Path(__file__),
                    Path(__file__).with_name("dsx01_cut_linear.py"),
                    Path(__file__).with_name("probe_dsx01_cut_linear.py"),
                ]
            },
        ),
    )
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
