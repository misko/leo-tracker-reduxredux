"""Compare compact orbit projection to the capture-era formula on roof and transfer inputs."""

import argparse
import dataclasses
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np

from tools.pipeline_eval.__main__ import (
    DEFAULT_OUT,
    ROOT,
    encoded,
    local_output,
    public_cases,
    references,
    save_json,
    write,
)
from tools.pipeline_eval.reference import grid
from tools.pipeline_eval.variants import orbit_projector, v5_lean


def maximum_error(original, candidate):
    errors = []
    for correct, test in zip(original, candidate, strict=True):
        if correct.shape != test.shape or not (
            np.isfinite(correct).all() and np.isfinite(test).all()
        ):
            raise ValueError("nonfinite or differently shaped orbital output")
        errors.append(float(np.max(np.abs(correct - test))) if correct.size else None)
    return errors


def nbytes(prepared):
    if isinstance(prepared, np.ndarray):
        return prepared.nbytes
    return sum(nbytes(getattr(prepared, f.name)) for f in dataclasses.fields(prepared))


def roof_grid(bank, times, center, library):
    from leo.analysis.research import phase_linear_geometry as original

    projector = orbit_projector.Projector(library)
    start = perf_counter()
    grid_ref = original.prepare_phase_geometry(bank, times)
    baseline_prep = perf_counter() - start
    start = perf_counter()
    grid_test = orbit_projector.prepare(bank, times)
    compact_prep = perf_counter() - start
    rows = []
    lat, lon = center
    for i, (x, y) in enumerate(((0, 0), (12, -12), (-12, 12), (0, 0))):
        coords = (lat + y / 111, lon + x / (111.32 * np.cos(np.deg2rad(lat))))
        values, timed = {}, {}
        actions = (
            ("original", original.phase_linear_frequency, grid_ref),
            ("compact", projector.evaluate, grid_test),
        )
        for mode, operation, prepared in actions if i % 2 == 0 else actions[::-1]:
            start = perf_counter()
            values[mode] = operation(prepared, *coords)
            timed[mode] = perf_counter() - start
        rows.append(
            dict(
                offset_km=[x, y],
                wall_s=timed,
                max_error=maximum_error(values["original"], values["compact"]),
            )
        )
    return dict(
        case="DS26-0036",
        shape=list(values["original"][0].shape),
        knots=len(bank["time_s"]),
        prepared_bytes=dict(original=nbytes(grid_ref), compact=grid_test.bytes),
        prepare_s=dict(original=baseline_prep, compact=compact_prep),
        projection=rows,
    )


def archived_roof_grid(request):
    """Prepare the frozen orbit bank and unique track times for one roof recording."""
    original, request, job = v5_lean.bound_request(request)
    engine = original.ev.owned_import("leo.application.localization_v3_engine", request["source"])

    from leo.operations.localization_v3_job import read_bound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.tle_archive import TleArchiveReader

    center = job["screen_center"]
    p = engine.policy.prepare_native_scan(
        read_bound(job["native_input"]),
        TleArchiveReader(Path(job["tle_root"])),
        TrackConfig(**read_bound(job["track_config"])["config"]),
        screen_latitude_deg=center[0],
        screen_longitude_deg=center[1],
    )
    times = np.unique(np.concatenate([t["times"] for t in p["tracks"]["tracks"]]))
    return original, job, p["sky"]["bank"], times


def development(request, result, library, dest):
    original, job, bank, times = archived_roof_grid(request)
    data = roof_grid(bank, times, job["screen_center"], library)
    save_json(Path(dest), data)
    original.write(result, dict(status="ok", boundary="full development orbit grid", metrics={}))


def transfer_case(item):
    from leo.analysis.research import phase_linear_geometry as reference

    case, library = item
    obs = json.loads(Path(case["observation_path"]).read_bytes())
    result = dict(id=case["id"], offered_regions=[o["id"] for o in case["regions"]], rows=[])
    if not obs["tracks"]:
        result["empty_observation"] = True
        return result
    measured = np.unique(np.concatenate([t["times"] for t in obs["tracks"]]))
    times = measured[np.rint(np.linspace(0, len(measured) - 1, min(32, len(measured)))).astype(int)]
    sky = grid.prepare_sky(obs, Path(case["catalog_path"]).read_text())
    proj = orbit_projector.Projector(library)
    for offer in case["regions"]:
        point = offer["center"]
        tile = grid.make_tile(sky, point)
        bank = dict(
            position_km=tile.positions_km, velocity_km_s=tile.velocities_km_s, time_s=tile.knots_s
        )
        ns = len(tile.positions_km)
        for name, phase in (("zero", 0.0), ("shifted", np.linspace(-1.7, 1.7, ns))):
            original = reference.phase_linear_frequency(
                reference.prepare_phase_geometry(bank, times, phase), *point
            )
            candidate = proj.evaluate(orbit_projector.prepare(bank, times, phase), *point)
            result["rows"].append(
                dict(
                    region=offer["id"],
                    phase=name,
                    satellites=ns,
                    times=len(times),
                    max_error=maximum_error(original, candidate),
                )
            )
    return result


def transfer(dest, jobs):
    from leo.analysis.research import orbit_phase_geometry, phase_linear_geometry

    sources = (orbit_phase_geometry, phase_linear_geometry)
    if any(not Path(m.__file__).resolve().is_relative_to(v5_lean.SOURCE) for m in sources):
        raise ValueError("transfer audit requires the frozen v5 projection source")
    hashes = {
        m.__name__: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in sources
    }
    panel, refs = references("transfer124", None)
    cases = public_cases(panel, refs, DEFAULT_OUT / "inputs")
    with tempfile.TemporaryDirectory() as wd:
        lib = Path(wd) / "projector.so"
        orbit_projector.compile_kernel(lib)
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            records = list(pool.map(transfer_case, [(c, lib) for c in cases]))
    write(
        dest,
        gzip.compress(encoded(dict(reference_sha256=hashes, records=records)) + b"\n", mtime=0),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", choices=("development", "transfer124"), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--jobs", type=int, default=1)
    args = p.parse_args()
    if args.jobs < 1:
        p.error("jobs must be positive")
    dest = local_output(args.out)
    if args.panel == "transfer124":
        subprocess.run(
            [sys.executable, "-B", "-P", __file__, "transfer124", str(dest), str(args.jobs)],
            env=dict(os.environ, PYTHONPATH=f"{v5_lean.SOURCE}:{ROOT}"),
            check=True,
        )
        return

    with tempfile.TemporaryDirectory() as wd:
        work = Path(wd)
        lib = work / "projector.so"
        orbit_projector.compile_kernel(lib)
        panel, refs = references("smoke", ["DS26-0036"])
        (case,) = public_cases(panel, refs, DEFAULT_OUT / "inputs")
        result = v5_lean.run_bound_worker(
            case, work / "run", Path(__file__), worker_args=(str(lib), str(dest))
        )
        if result["status"] != "ok":
            raise ValueError(result["reason"])


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "transfer124":
        transfer(Path(sys.argv[2]), int(sys.argv[3]))
    elif len(sys.argv) == 5 and not sys.argv[1].startswith("--"):
        development(*sys.argv[1:])
    else:
        main()
