"""Replace coarse legacy profiles with longer sparse-derivative refits."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_legacy_jacobian import fit, jacobian
from map_dsx01_clean_legacy import make_problem
from map_dsx01_clean_region import finite_gradient
from run_dsx01_clean_region import OUTPUT, load_scan


def run(case, method):
    path = OUTPUT / case / "surfaces" / f"legacy_{method}" / "result.json"
    data = json.loads(path.read_text())
    if data.get("sparse_profile_refined"):
        return
    scan, _ = load_scan(case)
    node = data["selected_assignment_node"]
    checks = []
    for arm, row in data["arms"].items():
        p = make_problem(scan, node["seed"], method, arm, node["point"])
        p.alias = node["aliases"]
        endpoint = np.array(row["fit"]["parameters"])
        j = jacobian(p, endpoint)
        finite = []
        for k in range(len(endpoint)):
            a, b = endpoint.copy(), endpoint.copy()
            a[k] = max(p.lower[k], endpoint[k] - 0.001)
            b[k] = min(p.upper[k], endpoint[k] + 0.001)
            finite.append((p.residual(b) - p.residual(a)) / (b[k] - a[k]))
        error = np.max(abs(j - np.array(finite).T))
        relative = float(error / max(1, np.max(np.abs(finite))))
        if relative > 2e-4:
            raise ValueError(f"derivative mismatch {case}/{method}/{arm}: {relative}")
        checks.append(dict(arm=arm, maximum_absolute_error=float(error), relative_error=relative))
        cache = {}

        def profile(x, p=p, endpoint=endpoint, cache=cache):
            key = tuple(np.asarray(x, float))
            if key not in cache:
                candidate = fit(p, endpoint, fixed_xy=x, iterations=48)
                cache[key] = candidate
            return cache[key]["score"]

        row["loss"] = [profile(x) for x in row["map_points"]]
        row["gradient_at_center"] = finite_gradient(profile, [0, 0])
        row["gradient_at_endpoint"] = finite_gradient(profile, endpoint[:2])
        row["map_profile_stops"] = [cache[tuple(x)]["stopped"] for x in row["map_points"]]
        row["map_profile_iteration_budget"] = 48
        row["longer_profile_checks"] = []
        row["map_profile_minimum"] = min(row["loss"])
    before = path.with_name("pre_sparse_profile_result.json")
    if not before.exists():
        before.write_bytes(path.read_bytes())
    data.update(
        sparse_profile_refined=True,
        nuisance_surface="48-iteration sparse-Jacobian refit per pixel; same objective",
        derivative_checks=checks,
    )
    write(path, data)
    picture = path.with_name("loss_gradient.png")
    if picture.exists():
        picture.rename(picture.with_name("pre_sparse_profile_loss_gradient.png"))
    print(case, method, "refined", flush=True)


def worker(case, method):
    path = OUTPUT / "logs" / f"{case}_refine_{method}.log"
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
    parser.add_argument("--method")
    parser.add_argument("--exclude", nargs="+", default=[])
    args = parser.parse_args()
    if args.case:
        run(args.case, args.method)
    else:
        paths = [
            p
            for p in OUTPUT.glob("DSX*/surfaces/legacy_*/result.json")
            if f"{p.parents[2].name}/{p.parent.name[7:]}" not in args.exclude
        ]
        with ThreadPoolExecutor(max_workers=8) as pool:
            tasks = [pool.submit(worker, p.parents[2].name, p.parent.name[7:]) for p in paths]
            for task in as_completed(tasks):
                print(task.result(), flush=True)
