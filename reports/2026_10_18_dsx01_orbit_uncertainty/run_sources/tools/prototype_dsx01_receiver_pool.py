"""Joint stationary-site fit with independent scan hardware and common RX drift."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from prototype_dsx01_continuous_position import GRID, latlon
from prototype_dsx01_pooled_position import Pool
from prototype_dsx01_receiver_geometry import OUTPUT, SOURCE, geometry_problem

from leo.analysis.research.factor_position_fit import factor_gauss_newton


def run(method, *, mean=10.0):
    directory = OUTPUT / "pooled" / method
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"mean_{mean:g}_endpoints.json"
    if output.exists():
        return json.loads(output.read_text())
    scans = [Scan(f"DSX01-S0{k}") for k in range(1, 6)]
    paths = [SOURCE / s.case / f"{method}_center.json" for s in scans]
    seeds = [{f"c0/{method}": json.loads(p.read_text())} for p in paths]

    def factory(scan, seed, method, variant, fitted_c):
        return geometry_problem(
            scan, seed, method, fitted_c, (0, 0), mean_sigma=mean, height_sigma=0
        )

    problems = {
        arm: Pool(scans, seeds, method, arm, "independent_phase", problem_factory=factory)
        for arm in ("c0", "fitted_c")
    }
    write(
        directory / f"mean_{mean:g}_protocol.json",
        dict(
            cases=[s.case for s in scans],
            mean_prior_sigma_hz_s=mean,
            band_contrast_sigma_hz_s=0.5,
            stationary_receiver_site_assumption=True,
            no_reference_GPS_or_oracle_initialization=True,
            hardware_and_phase_remain_independent_per_scan=True,
            all_five_scans_original_curved_points_retained=True,
            same_25_grid_points_three_starts_24_iteration_budgets_for_c_arms=True,
            seed_sha256={
                s.case: hashlib.sha256(p.read_bytes()).hexdigest()
                for s, p in zip(scans, paths, strict=True)
            },
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    grid = []
    for point in GRID:
        row = dict(east_north_km=point, scores={})
        for arm, p in problems.items():
            x = p.initial.copy()
            x[:2] = point
            row["scores"][arm] = p.score(x)
        grid.append(row)
    selected = sorted(grid, key=lambda r: r["scores"]["c0"])[:3]
    result = {}
    for arm, p in problems.items():
        mark, fits = time.monotonic(), []
        for row in selected:
            x = p.initial.copy()
            x[:2] = row["east_north_km"]
            fits.append(
                factor_gauss_newton(p.functions, p.mappings, x, p.lower, p.upper, iterations=24)
            )
        best = min(fits, key=lambda f: f["score"])
        x = best["parameters"]
        result[arm] = dict(
            latitude_deg=latlon(x[:2])[0],
            longitude_deg=latlon(x[:2])[1],
            east_north_km=x[:2],
            score=best["score"],
            grid=grid,
            starts=selected,
            fits=fits,
            states={
                s.case: pp.decode(x[m])
                for s, pp, m in zip(scans, p.problems, p.mappings, strict=True)
            },
            local_parameters={s.case: x[m] for s, m in zip(scans, p.mappings, strict=True)},
            mappings=p.mappings,
            names=p.names,
            elapsed_seconds=time.monotonic() - mark,
        )
        print(
            json.dumps(
                dict(
                    method=method,
                    arm=arm,
                    position=list(x[:2]),
                    score=best["score"],
                    seconds=time.monotonic() - mark,
                )
            ),
            flush=True,
        )
    write(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--mean", type=float, default=10.0)
    args = parser.parse_args()
    run(args.method, mean=args.mean)
