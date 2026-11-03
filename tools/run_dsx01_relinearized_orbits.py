"""Matched blind search with fixed versus iterated exact physical references."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_joint_exact_mean import exact_conditional_frequency
from dsx01_relinearized_orbits import VARIANTS, RelinearizedOrbits
from profile_dsx01_geographic_calibration import incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_continuous_position import CENTER, GRID, latlon
from prototype_dsx01_glrt_weighting import variance_samples
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import measurement_path

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

OUTPUT = ROOT / "reports/2026_10_18_dsx01_relinearized_orbits"


def run(case, *, variants=VARIANTS, rounds=4):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    measurement = measurement_path(case)
    metadata = apply_measurements(scan, json.loads(measurement.read_text())["points"], "glrt300")
    scores = json.loads(
        (ROOT / "reports/2026_10_18_dsx01_causal_repairs/glrt_scores.json").read_text()
    )[case]["scores"]
    _, squares = variance_samples(scan, scores)
    sigma = float(np.sqrt(np.mean(squares)))
    source, pair = choose_pair(incumbents(case, "receiver_smooth"))
    parent = pair["c0"]
    seed, aliases = dict(state=parent["state"], rows=parent["rows"]), parent["aliases"]
    write(
        directory / "protocol.json",
        dict(
            region_center=CENTER,
            grid=GRID,
            region_width_km=25,
            no_GPS_or_future_TLE_in_inference=True,
            variants=variants,
            original_curved_points_preserved_no_withholding=True,
            measurement="300 known pilot symbols at 2.5 MS/s, existing 20 ms windows",
            measurement_metadata=metadata,
            noise_sigma_hz=sigma,
            source_selection=source,
            source_seed_sha256=hashlib.sha256(
                json.dumps(parent, sort_keys=True).encode()
            ).hexdigest(),
            four_independent_RX_band_offsets=True,
            drift_prior_RX_mean_contrast_sigmas_hz_s=[10.0, 0.5],
            source_rows_and_aliases_fixed_for_all_variants=True,
            local_starts=3,
            iterations_per_start=24,
            phase_and_reference_rounds=rounds,
            c0_grid_starts_and_references_shared_by_both_c_arms=True,
            original_absolute_zero_mean_phase_and_physical_priors_preserved=True,
            mean_motion_reference="scan midpoint mean longitude",
            derivative_standard_step=0.01,
            likelihood="Gaussian/Gamma Student bound with local physical linearization",
            inference_is_not_exact_nonlinear_marginalization=True,
            source_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    ROOT / "tools/dsx01_relinearized_orbits.py",
                    ROOT / "tools/dsx01_joint_exact_mean.py",
                )
            },
        ),
    )
    for variant in variants:
        path = directory / variant / "rounds.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        records = json.loads(path.read_text()) if path.exists() else []
        reference, orbit_reference, anchor = None, None, [0.0, 0.0]
        labels = sorted({r["candidate_index"] for r in seed["rows"] if r["active_curvature"]})
        if records:
            previous = records[-1]["fits"]["c0"]
            reference = np.clip(np.array(previous["state"]["phases"])[labels], -14.9, 14.9)
            anchor = previous["east_north_km"]
            if variant.startswith("relinearized"):
                orbit_reference = previous["diagnostics"]["posterior_orbit_standard"]
        for iteration in range(len(records), rounds):
            problems = {
                arm: RelinearizedOrbits(
                    scan,
                    seed,
                    arm == "fitted_c",
                    variant=variant,
                    sigma=sigma,
                    reference=reference,
                    orbit_reference=orbit_reference,
                    aliases=aliases,
                )
                for arm in ("c0", "fitted_c")
            }
            grid = []
            for point in sorted(set(GRID) | {tuple(anchor)}):
                z = problems["c0"].residual(np.array(point))
                grid.append(dict(east_north_km=point, score=float(z @ z)))
            starts = sorted(grid, key=lambda r: r["score"])[:3]
            if not any(np.array_equal(row["east_north_km"], anchor) for row in starts):
                starts[-1] = next(
                    row for row in grid if np.array_equal(row["east_north_km"], anchor)
                )
            fits = {}
            for arm, p in problems.items():
                mark, attempts = time.monotonic(), []
                for start in starts:
                    result = bounded_gauss_newton(
                        p.residual,
                        np.array(start["east_north_km"]),
                        p.lower,
                        p.upper,
                        iterations=24,
                    )
                    attempts.append(dict(result, start_east_north_km=start["east_north_km"]))
                best = min(attempts, key=lambda r: r["score"])
                x = best["parameters"]
                diagnostics = p.diagnostics(x)
                exact, _, _ = exact_conditional_frequency(p, x)
                tangent, _ = p.conditional_frequency(x)
                diagnostics["exact_sgp4_mean_rms_hz"] = float(
                    np.sqrt(np.mean((p.q * (exact - tangent)) ** 2))
                )
                penalty = len(x) * np.log(len(p.flat_times))
                fits[arm] = dict(
                    latitude_deg=latlon(x[:2])[0],
                    longitude_deg=latlon(x[:2])[1],
                    east_north_km=x[:2],
                    parameters=x,
                    frequency_prior_score=best["score"],
                    complexity_penalty=penalty,
                    score=best["score"] + penalty,
                    state=p.state(x),
                    rows=p.rows,
                    aliases=p.alias,
                    starts=starts,
                    grid=grid,
                    fits=attempts,
                    diagnostics=diagnostics,
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
                        exact_mean_rms_hz={
                            a: f["diagnostics"]["exact_sgp4_mean_rms_hz"] for a, f in fits.items()
                        },
                    )
                ),
                flush=True,
            )
            reference = np.clip(fits["c0"]["state"]["phases"][labels], -14.9, 14.9)
            anchor = fits["c0"]["east_north_km"]
            if variant.startswith("relinearized"):
                orbit_reference = fits["c0"]["diagnostics"]["posterior_orbit_standard"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    args = parser.parse_args()
    run(args.case, variants=args.variants)
