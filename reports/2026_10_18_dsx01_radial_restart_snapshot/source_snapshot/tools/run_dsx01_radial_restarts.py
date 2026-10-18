"""Run isolated, causal association/localization restarts in bounded parallelism.

Position-independent radio observations are cached. Discovery and learned
states never cross starting positions. No saved conditional-map atlas is read.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT
from dsx01_inference_audit import CENTER, InferenceReadGuard, disk_grid
from dsx01_radial_legacy_linear import run_legacy_recipe, run_linear_recipe
from dsx01_radial_restarts import discover_at_start, run_modern_recipe
from map_dsx01_clean_linear import VARIANTS as LINEAR
from map_dsx01_clean_region import SPECS
from run_dsx01_clean_region import OUTPUT as CLEAN
from run_dsx01_clean_region import load_scan

OUTPUT = ROOT / "reports/2026_10_18_dsx01_radial_restarts"
CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))
ALL_METHODS = (*SPECS, *(f"legacy_{m}" for m in METHODS), *(f"linear_{m}" for m in LINEAR))
STARTS = sorted(disk_grid(step_km=5)[1], key=lambda x: (float(np.linalg.norm(x)), x[0], x[1]))
SOURCES = tuple(sorted({
    Path(__file__),
    ROOT / "tools/dsx01_radial_restarts.py",
    ROOT / "tools/dsx01_radial_legacy_linear.py",
    *(
        Path(m.__file__).resolve()
        for m in tuple(sys.modules.values())
        if getattr(m, "__file__", None)
        and str(Path(m.__file__).resolve()).startswith((str(ROOT / "tools/"), str(ROOT / "src/")))
    ),
}))


class RestartReadGuard(InferenceReadGuard):
    def check_path(self, path):
        if isinstance(path, (str, bytes)):
            name = str(path)
            if name.startswith(str(OUTPUT) + "/") and Path(name).name in {
                "discovery.json", "result.json"
            }:
                self.read_paths.add(name)
                return
        super().check_path(path)


def fingerprint():
    values = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def result_path(case, method, start_id):
    if method == "discover":
        return OUTPUT / case / "discovery" / f"start_{start_id:02d}" / "discovery.json"
    return OUTPUT / case / method / f"start_{start_id:02d}" / "result.json"


def valid_result(path, binding):
    if not path.exists():
        return False
    value = json.loads(path.read_text())
    if value.get("source_fingerprint") != binding:
        raise ValueError(f"preserve existing artifact from another source version: {path}")
    return value.get("status") == "complete"


def worker(case, method, start_id):
    binding = fingerprint()
    path = result_path(case, method, start_id)
    if valid_result(path, binding):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    guard = RestartReadGuard(CLEAN)
    guard.install()
    mark = time.monotonic()
    scan, sigma = load_scan(case)
    scan.strict_causal_history = json.loads((CLEAN / case / "causal_history.json").read_text())
    point = np.asarray(STARTS[start_id], float)
    if method == "discover":
        result = discover_at_start(scan, sigma, point, budget=8)
    else:
        discovery_path = result_path(case, "discover", start_id)
        discovery = json.loads(discovery_path.read_text())
        if discovery.get("source_fingerprint") != binding or discovery.get("status") != "complete":
            raise ValueError("same-start fresh discovery receipt does not match this run")
        if not np.array_equal(discovery["start_east_north_km"], point):
            raise ValueError("another starting position's discovery cannot be reused")
        if discovery.get("case") != case or discovery.get("start_id") != start_id:
            raise ValueError("discovery receipt belongs to another scan or start id")
        if method.startswith("legacy_"):
            result = run_legacy_recipe(scan, sigma, discovery, method.removeprefix("legacy_"))
        elif method.startswith("linear_"):
            parent_path = result_path(case, "normal", start_id)
            parent = json.loads(parent_path.read_text())
            if parent.get("source_fingerprint") != binding or parent.get("status") != "complete":
                raise ValueError("linear parent must be this start's completed normal restart")
            if (
                parent.get("case") != case
                or parent.get("start_id") != start_id
                or not np.array_equal(parent.get("start_east_north_km"), point)
            ):
                raise ValueError("normal parent belongs to another scan or starting position")
            result = run_linear_recipe(scan, sigma, parent, method.removeprefix("linear_"))
            result["parent_sha256"] = hashlib.sha256(parent_path.read_bytes()).hexdigest()
        else:
            result = run_modern_recipe(scan, sigma, discovery, method)
        result["discovery_sha256"] = hashlib.sha256(discovery_path.read_bytes()).hexdigest()
    result.update(
        case=case,
        method=method,
        start_id=start_id,
        start_east_north_km=point,
        source_fingerprint=binding,
        status="complete",
        seconds=time.monotonic() - mark,
        sigma_hz=sigma,
        curved_points=sum(len(scan.tracks[i]["times"]) for i in scan.curved),
        tracked_glrt_points=sum(len(t["times"]) for t in scan.tracks),
        candidate_count=len(scan.norads),
        actual_report_inputs_read=sorted(guard.read_paths),
        input_audit=scan.inference_input_audit,
        GPS_or_following_TLE_used=False,
        regional_center=CENTER,
        box_width_km=25,
    )
    temporary = path.with_suffix(".tmp")
    write(temporary, result)
    temporary.replace(path)
    print(
        json.dumps(dict(case=case, method=method, start_id=start_id, seconds=result["seconds"])),
        flush=True,
    )


def subprocess_job(case, method, start_id):
    log = OUTPUT / "logs" / f"{case}_{method}_{start_id:02d}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as handle:
        process = subprocess.run(
            [
                sys.executable, __file__, "--case", case,
                "--method", method, "--start-id", str(start_id),
            ],
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=dict(
                os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", PYTHONPATH="src:tools"
            ),
            check=False,
        )
    return dict(
        case=case, method=method, start_id=start_id, returncode=process.returncode, log=str(log)
    )


def dependencies(case, method, start_id):
    if method == "discover":
        return []
    result = [(case, "discover", start_id)]
    if method.startswith("linear_"):
        result.append((case, "normal", start_id))
    return result


def run(cases=CASES, methods=ALL_METHODS, starts=None, workers=20):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ids = list(range(len(STARTS))) if starts is None else starts
    if any(i < 0 or i >= len(STARTS) for i in ids):
        raise ValueError("unknown start id")
    methods = list(dict.fromkeys(methods))
    if any(m.startswith("linear_") for m in methods) and "normal" not in methods:
        methods.insert(0, "normal")
    # First cover all starts and scans; then finish each method's full basin
    # plot. This avoids spending the first batch on many recipes at one start.
    ordered_methods = sorted(
        methods,
        key=lambda m: (0 if m == "normal" else 1 if m.startswith("legacy_") else 2),
    )
    jobs = [(c, m, i) for m in ("discover", *ordered_methods) for c in cases for i in ids]
    binding = fingerprint()
    complete = {j for j in jobs if valid_result(result_path(*j), binding)}
    waiting = [j for j in jobs if j not in complete]
    rows, failures = [], set()
    protocol = dict(
        source_fingerprint=binding,
        source_bindings={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES
        },
        center=CENTER,
        radius_km=10,
        start_spacing_km=5,
        starts=[dict(start_id=i, east_north_km=STARTS[i]) for i in ids],
        cases=list(cases),
        methods=methods,
        expected_pipeline_results=len(cases) * len(ids) * len(methods),
        workers=workers,
        independent_zero_state_discovery_per_scan_and_start=True,
        discovery_reused_only_between_recipes_at_identical_start=True,
        cached_position_independent_acquisition_GLRT_and_graph_tracks=True,
        global_atlas_or_previous_endpoint_used=False,
        causal_TLE_collection_and_element_epochs_checked=True,
        matched_c0_fitted_c_observations_candidates_priors_and_search_budgets=True,
        association_refresh_rounds=2,
        iterations_per_fit=24,
        plots_are_start_to_endpoint_basin_maps_not_pointwise_loss_surfaces=True,
    )
    protocol_path = OUTPUT / "protocol.json"
    if protocol_path.exists():
        old = json.loads(protocol_path.read_text())
        if old["source_fingerprint"] != binding:
            raise ValueError("existing campaign source fingerprint differs; preserve old campaign")
    write(protocol_path, protocol)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        while waiting or active:
            ready = [j for j in waiting if all(d in complete for d in dependencies(*j))]
            for job in ready[: max(0, workers - len(active))]:
                waiting.remove(job)
                active[pool.submit(subprocess_job, *job)] = job
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                job = active.pop(future)
                row = future.result()
                rows.append(row)
                if row["returncode"]:
                    failures.add(job)
                else:
                    complete.add(job)
                print(json.dumps(row), flush=True)
            write(OUTPUT / "worker_status.json", dict(
                completed=len(complete), requested=len(jobs), failed=len(failures),
                active=len(active), waiting=len(waiting), results=rows,
            ))
    write(OUTPUT / "run_receipt.json", dict(
        requested=len(jobs), completed=len(complete), failures=sorted(failures),
        blocked_by_dependency=waiting, source_fingerprint=binding,
    ))
    if failures or waiting:
        raise SystemExit("restart failures or blocked dependencies; inspect worker_status.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    parser.add_argument("--method", choices=("discover", *ALL_METHODS))
    parser.add_argument("--methods", nargs="+", choices=ALL_METHODS, default=ALL_METHODS)
    parser.add_argument("--start-id", type=int)
    parser.add_argument("--starts", type=int, nargs="+")
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    if args.case:
        try:
            worker(args.case, args.method, args.start_id)
        except Exception:
            traceback.print_exc()
            raise
    else:
        run(args.cases, args.methods, args.starts, args.workers)
