"""Matched 25-km-box searches using linear evidence with curved-only calibration."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_cut_linear import bounded_scalar_newton
from probe_dsx01_cut_linear import OUTPUT, VARIANTS, CutScore, prepare
from prototype_dsx01_continuous_position import CENTER, GRID, latlon


def run(case):
    scan, parent, problems, nominations, source = prepare(case)
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    existing = json.loads((directory / "nominations.json").read_text())
    # Enumeration and floating results must remain identical to the diagnostic.
    encoded = json.dumps(nominations, default=lambda x: x.item() if hasattr(x, "item") else x)
    if json.loads(encoded) != existing:
        raise ValueError("linear nominations changed after diagnostic")
    write(
        directory / "protocol.json",
        dict(
            case=case,
            region_center=CENTER,
            box_width_km=25,
            grid=GRID,
            c0_selected_common_starts=3,
            iterations_per_start=24,
            no_GPS_or_future_TLE_in_inference=True,
            no_points_withheld=True,
            calibration_from_original_curves_only=True,
            linear_candidates_aliases_and_acceptance_frozen_from_blind_c0=True,
            linear_noise_sigma_hz=150,
            independent_linear_bias_sigma_hz=1000,
            shape_variant_bias_sigma_hz=1e6,
            continuation_max_same_RX_CH_gap_s=10,
            conditional_shared_calibration_covariance_retained=True,
            approximate_modular_score_not_full_joint_Bayesian_posterior=True,
            phase_reference_frozen_from_previous_blind_curved_three_round_search=True,
            original_curved_points=sum(len(scan.tracks[i]["times"]) for i in scan.curved),
            source_endpoint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            nominations_sha256=hashlib.sha256(
                (directory / "nominations.json").read_bytes()
            ).hexdigest(),
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
    destination = directory / "endpoints.json"
    results = {}
    for variant in VARIANTS:
        scores = {arm: CutScore(p, nominations, variant) for arm, p in problems.items()}
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
                    lambda x, score=score: score.score(x)["total"],
                    start["parameters"],
                    iterations=24,
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
        results[variant] = fits
        write(destination, results)
        print(
            json.dumps(
                dict(
                    case=case,
                    variant=variant,
                    endpoints={a: f["parameters"].tolist() for a, f in fits.items()},
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    run(parser.parse_args().case)
