"""Blind Mill Valley calibration multistarts and continuous nomination refresh.

The previous fixed-family experiment is left frozen. No evaluation site or
oracle nuisance state enters this fitter. Candidate refresh is a heuristic
alternating procedure, not a calibrated posterior or a classical EM proof.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from evaluate_shared_satellite_phase import solve_joint
from prototype_dsx01_continuous_position import (
    CENTER,
    GRID,
    FixedFamilies,
    latlon,
    native_point,
    numpy_state,
)

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics

OUTPUT = ROOT / "reports/2026_10_18_dsx01_nomination_iteration"


def nomination_rows(scan, rows, nominations):
    """Take the lowest visible cost nominee, independent of binary noise gates."""
    result = []
    for row in rows:
        if not row["active_curvature"]:
            raise ValueError("linear tracks cannot nominate calibration families")
        i = next(k for k in scan.curved if scan.tracks[k]["key"] == row["component"])
        n = nominations[i]
        j, terms = n["j"], n["terms"]
        result.append(
            dict(
                row,
                candidate_index=int(j),
                candidate_norad=int(scan.norads[j]),
                rms_hz=float(terms["rms"][j]),
                bias_hz=float(terms["bias"][j]),
                cost=float(terms["cost"][j]),
                parts=int(terms["parts"][j]),
                split_at=int(terms["split_at"][j]),
                compatible=bool(terms["passing"][j]),
            )
        )
    return result


class AnchoredFamilies(FixedFamilies):
    """Fix aliases at the actual blind calibration anchor, rather than town zero."""

    def __init__(self, scan, seed, method, fitted_c, anchor):
        super().__init__(scan, seed, method, "continuous", fitted_c)
        self.initial[:2] = anchor
        frequency, _ = self.predicted(self.initial)
        self.alias = []
        for i, block in zip(self.members, self.slices, strict=True):
            t = scan.tracks[i]
            raw = t["values"] - scan.hardware(t, self.starts["beta"])
            raw = raw - t["rf_hz"] / 11.5e9 * frequency[block]
            if method == "receiver_smooth":
                raw -= (
                    t["rf_hz"]
                    / 11.5e9
                    * scan.rx_basis[i]
                    @ self.starts["smooth"][t["receiver"] - 1]
                )
            self.alias.append(int(np.rint(-raw.mean() / PERIOD)))


def calibrate(scan, seed_budget):
    base = phase_linear_frequency(scan.geometry, *CENTER)
    stats = matching.statistics(
        scan.groups,
        dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
        {str(t["channel"]): 0.0 for t in scan.tracks},
    )
    stats = augment_phase_statistics(stats, scan.times, base[0], base[2])
    seed = solve_joint(
        stats,
        np.zeros(8),
        scan.sigma,
        np.full(len(scan.norads), 15.0),
        seed_budget,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1.0,
    )
    return (
        dict(
            beta=seed[1], phases=seed[2], extra={}, smooth=np.zeros((2, scan.rx_basis[0].shape[1]))
        ),
        int(seed[-1]),
        base,
    )


def refine_center(scan, initial, base, method):
    point = native_point(scan, (0, 0))
    state, history, best = numpy_state(initial), [], None
    for iteration in range(9):
        score, rows, nominees, predicted = scan.association(state, base, point, method)
        history.append(dict(iteration=iteration, gated_score=score))
        if best is None or score < best[0]:
            best = score, state, nomination_rows(scan, rows, nominees)
        if iteration < 8:
            state, _ = scan.update(state, nominees, predicted, point, method)
    return dict(score=best[0], state=best[1], rows=best[2], history=history)


def fit_once(scan, seed, method, anchor, iterations=24, *, problem_class=AnchoredFamilies):
    problems = {
        arm: problem_class(scan, seed, method, arm == "fitted_c", anchor)
        for arm in ("c0", "fitted_c")
    }
    grid = []
    for point in sorted(set(GRID) | {tuple(anchor)}):
        row = dict(east_north_km=list(point), scores={})
        for arm, problem in problems.items():
            x = problem.initial.copy()
            x[:2] = point
            z = problem.residual(x)
            row["scores"][arm] = float(z @ z)
        grid.append(row)
    selected = sorted(grid, key=lambda r: r["scores"]["c0"])[:3]
    if not any(np.array_equal(row["east_north_km"], anchor) for row in selected):
        selected[-1] = next(row for row in grid if np.array_equal(row["east_north_km"], anchor))
    output = {}
    for arm, p in problems.items():
        mark, fits = time.monotonic(), []
        for row in selected:
            x = p.initial.copy()
            x[:2] = row["east_north_km"]
            fit = bounded_gauss_newton(p.residual, x, p.lower, p.upper, iterations=iterations)
            fit["start_east_north_km"] = row["east_north_km"]
            fits.append(fit)
        best = min(fits, key=lambda r: r["score"])
        x = best["parameters"]
        penalty = len(x) * np.log(len(p.flat_times))
        output[arm] = dict(
            latitude_deg=latlon(x[:2])[0],
            longitude_deg=latlon(x[:2])[1],
            east_north_km=x[:2],
            score=best["score"] + penalty,
            frequency_prior_score=best["score"],
            complexity_penalty=penalty,
            state=p.decode(x),
            rows=p.rows,
            aliases=p.alias,
            grid=grid,
            starts=selected,
            fits=fits,
            anchor=anchor,
            seconds=time.monotonic() - mark,
        )
    return output


def run(case, seed_budget=32, refresh_rounds=2, methods=METHODS):
    directory = OUTPUT / f"seeds_{seed_budget}" / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    source = directory / "shared_center_seed.json"
    if source.exists():
        frozen = json.loads(source.read_text())
        initial = numpy_state(frozen["state"])
        base = phase_linear_frequency(scan.geometry, *CENTER)
    else:
        mark = time.monotonic()
        initial, count, base = calibrate(scan, seed_budget)
        frozen = dict(
            state=initial,
            calibration_seeds_evaluated=count,
            seconds=time.monotonic() - mark,
            no_evaluation_position=True,
        )
        write(source, frozen)
        print(
            json.dumps(
                dict(
                    case=case, seed_budget=seed_budget, seed_seconds=frozen["seconds"], seeds=count
                )
            ),
            flush=True,
        )
    write(
        directory / "protocol.json",
        dict(
            region_center=CENTER,
            region_box_km=[[-12.5, 12.5]] * 2,
            grid=GRID,
            no_evaluation_GPS_or_oracle_state_in_fit=True,
            raw_curved_only_calibration=True,
            common_c0_calibration_seed_for_both_c_arms=True,
            fixed_aliases_recomputed_only_at_blind_calibration_anchor=True,
            common_candidate_nominations_for_both_c_arms_each_round=True,
            common_c0_geographic_starts_and_same_24_iteration_budget=True,
            seed_budget=seed_budget,
            actual_seeds=frozen["calibration_seeds_evaluated"],
            refresh_rounds=refresh_rounds,
            nuisance_center_rounds=8,
            complexity_penalty="parameter_count * log(curved_observations)",
            nominal_labels_are_not_verified_identities=True,
            bank_sha256=scan.receipt["bank_sha256"],
            source_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    ROOT / "tools/prototype_dsx01_continuous_position.py",
                    ROOT / "src/leo/analysis/research/continuous_curve_fit.py",
                )
            },
        ),
    )
    final_path = directory / "endpoints.json"
    endpoints = json.loads(final_path.read_text()) if final_path.exists() else {}
    for method in methods:
        output = directory / f"{method}_iterations.json"
        records = json.loads(output.read_text()) if output.exists() else []
        if records:
            last = records[-1]["fits"]["c0"]
            anchor, state = last["east_north_km"], numpy_state(last["state"])
            point = native_point(scan, anchor)
            local_base = phase_linear_frequency(scan.geometry, *latlon(anchor))
            _, rows, nominees, _ = scan.association(state, local_base, point, method)
            seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        else:
            seed = refine_center(scan, initial, base, method)
            anchor = (0.0, 0.0)
            write(directory / f"{method}_center.json", seed)
        for iteration in range(len(records), refresh_rounds + 1):
            fits = fit_once(scan, seed, method, anchor)
            records.append(dict(iteration=iteration, fits=fits))
            write(output, records)
            print(
                json.dumps(
                    dict(
                        case=case,
                        method=method,
                        iteration=iteration,
                        positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                        scores={arm: f["score"] for arm, f in fits.items()},
                    )
                ),
                flush=True,
            )
            anchor, state = fits["c0"]["east_north_km"], fits["c0"]["state"]
            point = native_point(scan, anchor)
            local_base = phase_linear_frequency(scan.geometry, *latlon(anchor))
            _, rows, nominees, _ = scan.association(state, local_base, point, method)
            seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        for arm in ("c0", "fitted_c"):
            best_round = min(records, key=lambda r: r["fits"][arm]["score"])
            endpoints[f"{arm}/{method}"] = dict(
                best_round["fits"][arm], selected_iteration=best_round["iteration"]
            )
        write(final_path, endpoints)
    return endpoints


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--seed-budget", type=int, default=32)
    parser.add_argument("--refresh-rounds", type=int, default=2)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    args = parser.parse_args()
    run(
        args.case,
        seed_budget=args.seed_budget,
        refresh_rounds=args.refresh_rounds,
        methods=tuple(args.methods),
    )
