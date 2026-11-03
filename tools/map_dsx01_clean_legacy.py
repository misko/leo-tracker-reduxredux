"""Freshly initialized loss/gradient maps for the six original graph methods.

Nuisance coefficients are profiled numerically at each map pixel with an
explicit finite budget. Labels are generated from the full regional bank at
the 25 search nodes, then the selected branch is held fixed for this surface.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS
from dsx01_inference_audit import InferenceReadGuard, disk_grid
from iterate_dsx01_profiled_identity import explore
from map_dsx01_clean_region import finite_gradient
from profile_dsx01_geographic_calibration import geometry_problem
from prototype_dsx01_continuous_position import GRID, latlon
from run_dsx01_clean_region import OUTPUT, load_scan, reference_state

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton


def make_problem(scan, seed, method, arm, anchor):
    return geometry_problem(
        scan, seed, method, arm == "fitted_c", anchor, mean_sigma=10, height_sigma=0
    )


def run(case, method):
    directory = OUTPUT / case
    path = directory / "surfaces" / f"legacy_{method}" / "result.json"
    if path.exists():
        return
    guard = InferenceReadGuard(OUTPUT)
    guard.install()
    scan, _ = load_scan(case)
    atlas = json.loads((directory / "atlas.json").read_text())["nodes"]
    mark = time.monotonic()
    nodes = []
    for node in atlas:
        seed, _ = explore(
            scan,
            reference_state(node["seed"]["state"]),
            node["point"],
            method,
            compact_update=False,
        )
        p = make_problem(scan, seed, method, "c0", node["point"])
        initial = p.initial.copy()
        r = p.residual(initial)
        nodes.append(dict(seed=seed, point=node["point"], aliases=p.alias, score=float(r @ r)))
    node = min(nodes, key=lambda n: n["score"])
    problems = {
        a: make_problem(scan, node["seed"], method, a, node["point"]) for a in ("c0", "fitted_c")
    }
    for p in problems.values():
        p.alias = node["aliases"]
    grid = []
    for point in GRID:
        x = problems["c0"].initial.copy()
        x[:2] = point
        r = problems["c0"].residual(x)
        grid.append(dict(point=point, score=float(r @ r)))
    starts = sorted(grid, key=lambda r: r["score"])[:3]
    axis, points = disk_grid(step_km=2.0)
    arms = {}
    for arm, p in problems.items():
        attempts = []
        for start in starts:
            x = p.initial.copy()
            x[:2] = start["point"]
            attempts.append(bounded_gauss_newton(p.residual, x, p.lower, p.upper, iterations=24))
        fit = min(attempts, key=lambda r: r["score"])
        endpoint = np.array(fit["parameters"])
        cache = {}

        def profile(point, p=p, endpoint=endpoint, cache=cache):
            key = tuple(np.asarray(point, float))
            if key not in cache:

                def residual(z):
                    return p.residual(np.r_[point, z])

                result = bounded_gauss_newton(
                    residual, endpoint[2:], p.lower[2:], p.upper[2:], iterations=2
                )
                cache[key] = result
            return cache[key]["score"]

        values = [profile(point) for point in points]
        longer_checks = []
        for point in [[0.0, 0.0], [-10.0, 0.0], [10.0, 0.0], [0.0, -10.0], [0.0, 10.0]]:

            def residual(z, point=point, p=p):
                return p.residual(np.r_[point, z])

            checked = bounded_gauss_newton(
                residual, endpoint[2:], p.lower[2:], p.upper[2:], iterations=8
            )
            longer_checks.append(
                dict(
                    point=point,
                    two_iteration_score=profile(point),
                    eight_iteration_score=checked["score"],
                    score_gap=profile(point) - checked["score"],
                )
            )
        probes = []
        for start in [[0.0, 0.0], *[points[i] for i in np.argsort(values)[:2]]]:
            x = endpoint.copy()
            x[:2] = start
            probes.append(bounded_gauss_newton(p.residual, x, p.lower, p.upper, iterations=24))
        arms[arm] = dict(
            fit=dict(fit, attempts=attempts),
            map_points=points,
            loss=values,
            multistart_probes=probes,
            endpoint_latlon=latlon(endpoint[:2]),
            gradient_at_center=finite_gradient(profile, [0, 0]),
            gradient_at_endpoint=finite_gradient(profile, endpoint[:2]),
            map_profile_stops=[cache[tuple(point)]["stopped"] for point in points],
            map_profile_iteration_budget=2,
            longer_profile_checks=longer_checks,
            frequency_residual_rms_available=False,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    write(
        path,
        dict(
            case=case,
            method=f"legacy_{method}",
            arms=arms,
            axis=axis,
            conditional_assignment=True,
            nuisance_surface="two-step pixel profiles; five eight-step validation probes per arm",
            selected_assignment_node=node,
            actual_report_inputs_read=sorted(guard.read_paths),
            GPS_or_following_TLE_used=False,
            seconds=time.monotonic() - mark,
        ),
    )
    print(case, method, round(time.monotonic() - mark, 1), flush=True)


def worker(case, method):
    path = OUTPUT / "logs" / f"{case}_legacy_{method}.log"
    with path.open("w") as handle:
        result = subprocess.run(
            [sys.executable, __file__, "--case", case, "--method", method],
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            env=dict(
                os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", PYTHONPATH="src:tools"
            ),
        )
    return dict(case=case, method=method, returncode=result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case")
    parser.add_argument("--method", choices=METHODS)
    args = parser.parse_args()
    if args.case:
        run(args.case, args.method)
    else:
        with ThreadPoolExecutor(max_workers=12) as pool:
            tasks = [pool.submit(worker, f"DSX01-S0{k}", m) for k in range(1, 6) for m in METHODS]
            rows = []
            for task in as_completed(tasks):
                rows.append(task.result())
                print(rows[-1], flush=True)
                write(OUTPUT / "legacy_worker_status.json", rows)
        if any(r["returncode"] for r in rows):
            raise SystemExit("some legacy workers failed")
