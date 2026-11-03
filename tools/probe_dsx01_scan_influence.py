"""Blind scan-deletion influence diagnostic; the main estimator retains all scans."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from prototype_dsx01_continuous_position import GRID, latlon
from prototype_dsx01_pooled_position import Pool
from prototype_dsx01_receiver_geometry import SOURCE, geometry_problem

from leo.analysis.research.factor_position_fit import factor_gauss_newton

OUTPUT = ROOT / "reports/2026_10_18_dsx01_orbit_uncertainty"


def run(omitted, method="orbit_em"):
    directory = OUTPUT / "scan_influence" / method / omitted
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    if path.exists():
        return json.loads(path.read_text())
    scans = [Scan(f"DSX01-S0{k}") for k in range(1, 6) if f"DSX01-S0{k}" != omitted]
    paths = [SOURCE / s.case / f"{method}_center.json" for s in scans]
    seeds = [{f"c0/{method}": json.loads(p.read_text())} for p in paths]

    def factory(scan, seed, method, variant, fitted_c):
        return geometry_problem(scan, seed, method, fitted_c, (0, 0), mean_sigma=10, height_sigma=0)

    problems = {
        a: Pool(scans, seeds, method, a, "independent_phase", problem_factory=factory)
        for a in ("c0", "fitted_c")
    }
    write(
        directory / "protocol.json",
        dict(
            diagnostic_only_main_fit_keeps_all_five_scans=True,
            no_reference_GPS_or_oracle_initialization=True,
            omitted_scan=omitted,
            retained_scans=[s.case for s in scans],
            no_omitted_scan_fit_or_nuisance_state_used=True,
            mean_drift_sigma_hz_s=10,
            band_contrast_sigma_hz_s=0.5,
            same_grid_3_starts_24_iterations_in_both_c_arms=True,
            retained_center_seed_sha256={
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
    results = {}
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
        results[arm] = dict(
            latitude_deg=latlon(x[:2])[0],
            longitude_deg=latlon(x[:2])[1],
            east_north_km=x[:2],
            score=best["score"],
            grid=grid,
            starts=selected,
            fits=fits,
            names=p.names,
            mappings=p.mappings,
            states={
                s.case: pp.decode(x[m])
                for s, pp, m in zip(scans, p.problems, p.mappings, strict=True)
            },
            local_parameters={s.case: x[m] for s, m in zip(scans, p.mappings, strict=True)},
            seconds=time.monotonic() - mark,
        )
        print(omitted, arm, list(x[:2]), flush=True)
    write(path, results)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--omit", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    run(p.parse_args().omit)
