"""Truth-centred diagnostic of the existing bounded research loss, not a blind eval."""

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

OUTPUT = ROOT / "reports/2026_10_18_s01_local_loss"
REFERENCE = np.array([37.849061591561885, -122.48574968092912])
ROUNDS = 3
RADIUS = 10.0
LIMIT = 192
SCALES = (2.0, 1.0, 0.5, 0.25, 0.125, 0.0625)
DIRECTIONS = tuple((a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b)


def grid_points():
    points = {
        (float(e), float(n))
        for e in range(-10, 11, 2)
        for n in range(-10, 11, 2)
        if e * e + n * n <= RADIUS**2
    }
    for h in (0.125, 0.5, 1.0):
        points.update((h * e, h * n) for e, n in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    return sorted(points, key=lambda p: (p[0] ** 2 + p[1] ** 2, p))


def position(scan, local):
    """Invert Scan.latlon, placing the supplied reference exactly at local zero."""
    east, north = local
    longitude = REFERENCE[1] + east / (111.32 * np.cos(np.deg2rad(REFERENCE[0])))
    latitude = REFERENCE[0] + north / 111.0
    return np.array(
        [(longitude - scan.center[1]) * scan.scale, (latitude - scan.center[0]) * 111.0]
    )


def state_from_json(value):
    return dict(
        beta=np.array(value["beta"]),
        phases=np.array(value["phases"]),
        extra={int(k): np.array(v) for k, v in value["extra"].items()},
        smooth=np.array(value["smooth"]),
    )


def compact(local, fits):
    metrics = {}
    for key, fit in fits.items():
        accepted = [r for r in fit["rows"] if r["compatible"] and r["active_curvature"]]
        n = sum(r["points"] for r in accepted)
        metrics[key] = dict(
            score=fit["score"],
            curved_points=n,
            curved_tracks=len(accepted),
            native_rms_hz=float(
                np.sqrt(sum(r["points"] * r["rms_hz"] ** 2 for r in accepted) / max(1, n))
            ),
        )
    return dict(east_north_km=list(local), metrics=metrics)


def grid(worker, workers):
    OUTPUT.mkdir(exist_ok=True)
    scan = Scan("DSX01-S01")
    rows = []
    for i, local in enumerate(grid_points()):
        if i % workers != worker:
            continue
        mark = time.monotonic()
        fits = scan.at_point(position(scan, local), rounds=ROUNDS)
        rows.append(compact(local, fits))
        write(OUTPUT / f"grid_worker_{worker}.json", rows)
        if local == (0.0, 0.0):
            write(OUTPUT / "truth_fits.json", fits)
        print(
            json.dumps(
                dict(
                    worker=worker, completed=len(rows), point=local, seconds=time.monotonic() - mark
                )
            ),
            flush=True,
        )


def local_search(method, *, fine_start=False):
    scan = Scan("DSX01-S01")
    files = sorted(OUTPUT.glob("grid_worker_*.json"))
    grid = [row for p in files for row in json.loads(p.read_text())]
    assert len(grid) == len(grid_points())
    cache = {tuple(r["east_north_km"]): r for r in grid}
    keys = [f"{arm}/{method}" for arm in ("c0", "fitted_c")]
    centers = {key: (0.0, 0.0) for key in keys}
    paths = {
        key: [
            dict(
                east_north_km=[0.0, 0.0],
                score=cache[0.0, 0.0]["metrics"][key]["score"],
                scale_km=None,
            )
        ]
        for key in keys
    }
    progress_path = OUTPUT / f"{method}_progress.json"
    new = json.loads(progress_path.read_text()) if progress_path.exists() else []
    cache.update({tuple(r["east_north_km"]): r for r in new})
    initial_queries = len(new)
    limit = initial_queries + 96 if fine_start else LIMIT
    if fine_start:
        archive = OUTPUT / "coarse_start"
        archive.mkdir(exist_ok=True)
        for suffix in (
            "surface",
            "endpoints",
            "truth_all_tracks",
            "frozen_cuts",
            "iteration_sensitivity",
        ):
            source = OUTPUT / f"{method}_{suffix}.json"
            if not (archive / source.name).exists():
                shutil.copyfile(source, archive / source.name)
    checks = {key: [] for key in keys}
    previous_surface = OUTPUT / f"{method}_surface.json"
    resume_fine = False
    if fine_start and previous_surface.exists():
        previous = json.loads(previous_surface.read_text())
        if previous.get("fine_start", False):
            resume_fine = True
            paths, checks = previous["paths"], previous["checks"]
            centers = {
                key: tuple(previous["endpoints"][key]["final_east_north_km"]) for key in keys
            }

    def evaluate(point):
        point = tuple(np.round(point, 8))
        if point in cache:
            return True
        if np.linalg.norm(point) > RADIUS + 1e-8 or len(new) >= limit:
            return False
        fits = scan.at_point(position(scan, point), models=(method,), rounds=ROUNDS)
        row = compact(point, fits)
        new.append(row)
        cache[point] = row
        write(OUTPUT / f"{method}_progress.json", new)
        print(json.dumps(dict(method=method, evaluations=len(new), point=point)), flush=True)
        return True

    scales = (0.0625,) if resume_fine else ((0.125, 0.0625) if fine_start else SCALES)
    for scale in scales:
        # Repeated improving moves at a scale, rather than assuming a single
        # finite-difference step reaches a basin. Both c arms share every query.
        for sweep in range(24 if fine_start else 4):
            neighborhoods = {
                key: [
                    tuple(np.round(np.array(centers[key]) + scale * np.array(d), 8))
                    for d in DIRECTIONS
                    if np.linalg.norm(np.array(centers[key]) + scale * np.array(d)) <= RADIUS
                ]
                for key in keys
            }
            for p in sorted(set(sum(neighborhoods.values(), []))):
                evaluate(p)
            moved = False
            for key in keys:
                old = centers[key]
                choices = [old] + [p for p in neighborhoods[key] if p in cache]
                best = min(choices, key=lambda p: cache[p]["metrics"][key]["score"])
                improved = (
                    cache[best]["metrics"][key]["score"]
                    < cache[old]["metrics"][key]["score"] - 1e-8
                )
                complete = all(p in cache for p in neighborhoods[key])
                checks[key].append(
                    dict(
                        scale_km=scale,
                        sweep=sweep,
                        complete=complete,
                        improved=improved,
                        center=list(old),
                    )
                )
                if improved:
                    centers[key] = best
                    paths[key].append(
                        dict(
                            east_north_km=list(best),
                            score=cache[best]["metrics"][key]["score"],
                            scale_km=scale,
                        )
                    )
                    moved = True
            if not moved or len(new) >= limit:
                break
        if len(new) >= limit:
            break

    endpoints, budgets = {}, {}
    for key in keys:
        checked = [
            r
            for r in checks[key]
            if r["complete"] and not r["improved"] and tuple(r["center"]) == centers[key]
        ]
        budgets[key] = dict(
            final_east_north_km=list(centers[key]),
            stationary_stencil_scale_km=min((r["scale_km"] for r in checked), default=None),
            minimum_claim="bounded stencil endpoint, not proof of a differentiable/global minimum",
        )
    for point in set(centers.values()) | {(0.0, 0.0)}:
        fits = scan.at_point(
            position(scan, point), models=(method,), rounds=ROUNDS, all_tracks=True
        )
        for key in keys:
            if point == centers[key]:
                endpoints[key] = fits[key]
        if point == (0.0, 0.0):
            write(OUTPUT / f"{method}_truth_all_tracks.json", fits)
    write(OUTPUT / f"{method}_endpoints.json", endpoints)
    write(
        OUTPUT / f"{method}_surface.json",
        dict(
            method=method,
            samples=list(cache.values()),
            paths=paths,
            checks=checks,
            endpoints=budgets,
            additional_common_location_budget=limit,
            additional_locations_used=len(new),
            fine_start=fine_start,
            continued_from_previous_endpoint=resume_fine,
            initial_step_km=0.125 if fine_start else 2.0,
            new_queries_in_this_stage=len(new) - initial_queries,
            paired_c_arms_share_all_location_evaluations=True,
            known_reference_intentionally_used_for_region_and_local_start=True,
            inference_nuisance_rounds=ROUNDS,
        ),
    )
    # Frozen-calibration cuts isolate spatial sensitivity from refitting jumps.
    truth = json.loads((OUTPUT / "truth_fits.json").read_text())
    cuts = []
    for axis in (0, 1):
        for displacement in (-2.0, -1.0, -0.5, -0.125, 0.0, 0.125, 0.5, 1.0, 2.0):
            point = np.zeros(2)
            point[axis] = displacement
            xy = position(scan, point)
            base = phase_linear_frequency(scan.geometry, *scan.latlon(xy))
            scores = {}
            for key in keys:
                scores[key] = scan.association(
                    state_from_json(truth[key]["state"]), base, xy, method
                )[0]
            cuts.append(dict(axis=axis, displacement_km=displacement, scores=scores))
    write(OUTPUT / f"{method}_frozen_cuts.json", cuts)
    # Matched longer fitting budget at truth and the reached endpoints diagnoses
    # finite nuisance-iteration effects without using a different physical model.
    sensitivity = {}
    for point in set(centers.values()) | {(0.0, 0.0)}:
        fits = scan.at_point(position(scan, point), models=(method,), rounds=8)
        sensitivity[str(point)] = compact(point, fits)
    write(OUTPUT / f"{method}_iteration_sensitivity.json", sensitivity)


def protocol():
    OUTPUT.mkdir(exist_ok=True)
    write(
        OUTPUT / "protocol.json",
        dict(
            dataset="DSX01-S01",
            reference_latitude_longitude=REFERENCE,
            radius_km=RADIUS,
            region="10 km radius about supplied GPS; not a blind localization eval",
            grid_spacing_km=2,
            grid_points=len(grid_points()),
            grid_extra_probes_km=[0.125, 0.5, 1.0],
            local_start=[0, 0],
            local_scales_km=SCALES,
            local_extra_budget_per_method=LIMIT,
            maximum_sweeps_per_scale=4,
            same_observations_candidates_priors_and_fit_budgets_for_c_arms=True,
            calibration_population="raw-curved fragments only; linear points never rank location",
            location_prior="none inside disk; supplied GPS sets diagnostic region and start",
            score_type="existing gated composite loss; not a normalized posterior or probability",
            nuisance_refit="cold zero hardware start and original seed; three proposal rounds",
            limitation=(
                "effective finite-iteration loss, not an exactly optimized profile likelihood"
            ),
            orbit_model="same tangent eccentricity-vector state model as comparison fitter",
            source_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), ROOT / "tools/compare_dsx01_retention_localization.py")
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("protocol", "grid", "local"), required=True)
    parser.add_argument("--worker", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--method", choices=METHODS)
    args = parser.parse_args()
    if args.stage == "protocol":
        protocol()
    elif args.stage == "grid":
        grid(args.worker, args.workers)
    else:
        assert args.method is not None
        local_search(args.method)
