"""Blind 25-km search with joint nuisance integration; GPS used only by reporter."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_joint_marginal import JointMarginal
from profile_dsx01_geographic_calibration import incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_continuous_position import CENTER, GRID, latlon
from prototype_dsx01_glrt_weighting import variance_samples
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import measurement_path

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

OUTPUT = ROOT / "reports/2026_10_18_dsx01_joint_marginal"
VARIANTS = ("fixed", "radio_noise", "empirical")


def run(case, *, variants=VARIANTS, iterations=24, rounds=3):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    measurement = measurement_path(case)
    metadata = apply_measurements(scan, json.loads(measurement.read_text())["points"], "glrt300")
    scores_path = ROOT / "reports/2026_10_18_dsx01_causal_repairs/glrt_scores.json"
    scores = json.loads(scores_path.read_text())[case]["scores"]
    _, squares = variance_samples(scan, scores)
    noise_sigma = float(np.sqrt(np.mean(squares)))
    selection, pair = choose_pair(incumbents(case, "receiver_smooth"))
    parent = pair["c0"]
    seed = dict(state=parent["state"], rows=parent["rows"])
    # Reuse aliases exactly from the blind parent. No re-rounding after fitting.
    aliases = parent["aliases"]
    protocol = dict(
        region_center=CENTER,
        grid=GRID,
        box_width_km=25,
        no_GPS_or_future_TLE_in_inference=True,
        measurements="glrt300",
        measurement_metadata=metadata,
        measurement_sha256=hashlib.sha256(measurement.read_bytes()).hexdigest(),
        raw_curved_population_preserved_no_withholding=True,
        seed_selection=selection,
        seed_sha256=hashlib.sha256(json.dumps(parent, sort_keys=True).encode()).hexdigest(),
        noise_estimate_hz=noise_sigma,
        noise_estimate_method="radio-only piecewise-polynomial leverage-corrected residuals",
        model="diagonal noise plus jointly integrated radio/phase/orbit/curve-constant modes",
        cost="quadratic + logdet(C/D) + soft visibility; fixed noise determinant omitted",
        offsets_prior_sigma_hz=1 / 4.4e-6 / np.sqrt(12),
        receiver_drift_mean_sigma_hz_s=10,
        receiver_drift_contrast_sigma_hz_s=0.5,
        receiver_smooth_sigma_hz=200,
        curve_constant_sigma_hz=1000,
        RF_c_prior_sigma=200000,
        phase_sigma_floor_s=1,
        priors_are_declared_hypotheses_not_calibrated_probabilities=True,
        three_shared_c0_selected_starts=True,
        iterations_per_start=iterations,
        phase_linearization_rounds=rounds,
        phase_prior_remains_absolute_zero_mean_after_relinearization=True,
        shared_c0_phase_reference_in_both_c_arms=True,
        finite_phase_linearization_not_exact_orbit_marginalization=True,
        candidate_labels_unverified=True,
        bank_sha256=scan.receipt["bank_sha256"],
        source_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                ROOT / "tools/dsx01_joint_marginal.py",
                ROOT / "tools/build_dsx01_orbit_modes.py",
                ROOT / "src/leo/analysis/research/continuous_curve_fit.py",
            )
        },
    )
    write(directory / "protocol.json", protocol)
    for variant in variants:
        path = directory / variant / "rounds.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        records = json.loads(path.read_text()) if path.exists() else []
        reference = None
        anchor = [0.0, 0.0]
        hyper = np.zeros(3)
        if records:
            base = records[-1]["fits"]["c0"]
            reference = np.array(base["state"]["phases"])[
                sorted({r["candidate_index"] for r in seed["rows"] if r["active_curvature"]})
            ]
            anchor = base["east_north_km"]
            if variant == "empirical":
                hyper = np.asarray(base["parameters"])[2:]
        for iteration in range(len(records), rounds):
            problems = {
                arm: JointMarginal(
                    scan,
                    seed,
                    arm == "fitted_c",
                    variant=variant,
                    sigma=noise_sigma,
                    reference=reference,
                    aliases=aliases,
                )
                for arm in ("c0", "fitted_c")
            }
            if variant == "empirical":
                for p in problems.values():
                    p.initial[2:] = hyper
            grid = []
            for point in sorted(set(GRID) | {tuple(anchor)}):
                x = problems["c0"].initial.copy()
                x[:2] = point
                z = problems["c0"].residual(x)
                grid.append(dict(east_north_km=point, score=float(z @ z)))
            starts = sorted(grid, key=lambda r: r["score"])[:3]
            if not any(np.array_equal(r["east_north_km"], anchor) for r in starts):
                starts[-1] = next(r for r in grid if np.array_equal(r["east_north_km"], anchor))
            fits = {}
            for arm, p in problems.items():
                mark = time.monotonic()
                attempts = []
                for start in starts:
                    initial = p.initial.copy()
                    initial[:2] = start["east_north_km"]
                    result = bounded_gauss_newton(
                        p.residual, initial, p.lower, p.upper, iterations=iterations
                    )
                    attempts.append(dict(result, start_east_north_km=start["east_north_km"]))
                best = min(attempts, key=lambda r: r["score"])
                x = best["parameters"]
                penalty = len(x) * np.log(len(p.flat_times))
                fits[arm] = dict(
                    latitude_deg=latlon(x[:2])[0],
                    longitude_deg=latlon(x[:2])[1],
                    east_north_km=x[:2],
                    parameters=x,
                    frequency_prior_score=best["score"],
                    score=best["score"] + penalty,
                    complexity_penalty=penalty,
                    state=p.state(x),
                    rows=p.rows,
                    aliases=p.alias,
                    starts=starts,
                    grid=grid,
                    fits=attempts,
                    diagnostics=p.diagnostics(x),
                    seconds=time.monotonic() - mark,
                )
            records.append(dict(iteration=iteration, fits=fits))
            write(path, records)
            write(path.parent / "endpoints.json", dict(fits=fits, selected_round=iteration))
            print(
                json.dumps(
                    dict(
                        case=case,
                        variant=variant,
                        iteration=iteration,
                        endpoints={a: f["east_north_km"].tolist() for a, f in fits.items()},
                        scores={a: f["score"] for a, f in fits.items()},
                    )
                ),
                flush=True,
            )
            reference = np.clip(fits["c0"]["state"]["phases"][problems["c0"].labels], -14.9, 14.9)
            anchor = fits["c0"]["east_north_km"]
            if variant == "empirical":
                hyper = fits["c0"]["parameters"][2:]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    parser.add_argument("--iterations", type=int, default=24)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    run(args.case, variants=args.variants, iterations=args.iterations, rounds=args.rounds)
