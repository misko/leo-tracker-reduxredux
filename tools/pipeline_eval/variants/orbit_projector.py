"""Project Doppler and its phase derivative directly from the orbit knots."""

import ctypes
import hashlib
import json
import subprocess
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import v5_core, v5_lean

KERNEL = Path(__file__).with_suffix(".c")
FLAGS = ("-std=c11", "-O3", "-ffp-contract=off", "-fno-math-errno", "-fPIC", "-shared")
BOUNDARY = (
    "All native detector observations through the v5 cavity fit with compact orbital projection"
)


def compile_kernel(path):
    subprocess.run(["cc", *FLAGS, str(KERNEL), "-lm", "-o", str(path)], check=True)


@dataclass(frozen=True)
class Stencil:
    positions: np.ndarray
    velocities: np.ndarray
    index: np.ndarray
    fraction: np.ndarray
    rotation: np.ndarray
    step: float

    @property
    def bytes(self):
        return sum(
            v.nbytes
            for v in (self.positions, self.velocities, self.index, self.fraction, self.rotation)
        )


def prepare(bank, times, phases=0.0, *, derivative_step_s=0.05):
    from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
    from leo.analysis.research.track_catalogue_geometry import interpolate_states

    interpolate_states(bank, np.empty(0))
    t, phase = np.asarray(times, float), np.asarray(phases, float)
    if t.ndim != 1 or not np.isfinite(t).all() or not np.isfinite(phase).all():
        raise ValueError("finite observation times and orbit phases required")
    p, v = (
        np.array(bank[k], dtype=np.float64, order="C", copy=True)
        for k in ("position_km", "velocity_km_s")
    )
    if phase.ndim != 0 and phase.shape != (len(p),):
        raise ValueError("expected one phase or one per satellite")
    if not np.isfinite(derivative_step_s) or derivative_step_s <= 0:
        raise ValueError("positive phase step required")
    phase = np.atleast_1d(phase) if len(p) else np.empty(0)
    offsets = phase[:, None] + np.array([0.0, derivative_step_s, -derivative_step_s])
    knots = np.asarray(bank["time_s"], float)
    q = t + offsets[..., None]
    if np.any(q < knots[0]) or np.any(q > knots[-1]):
        raise ValueError("orbit phase interpolation never extrapolates")
    index = np.clip(np.searchsorted(knots, q, side="right") - 1, 0, len(knots) - 2).astype(np.int64)
    frac = (q - knots[index]) / (knots[index + 1] - knots[index])
    angle = EARTH_ROTATION_RAD_S * offsets
    rot = np.stack((np.cos(angle), np.sin(angle)), axis=-1)
    for a in (p, v, index, frac, rot):
        a.setflags(write=False)
    return Stencil(p, v, index, frac, rot, derivative_step_s)


class Projector:
    def __init__(self, library):
        self.call = ctypes.CDLL(str(Path(library).resolve())).project_orbit_grid
        real = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
        integer = np.ctypeslib.ndpointer(dtype=np.int64, flags="C_CONTIGUOUS")
        self.call.argtypes = [
            real,
            real,
            *([ctypes.c_size_t] * 4),
            integer,
            real,
            real,
            ctypes.c_double,
            real,
            real,
            ctypes.c_double,
            real,
            real,
            real,
        ]
        self.call.restype = ctypes.c_int
        self.calls = self.max_bytes = self.max_original_bytes = 0

    def evaluate(self, grid, latitude_deg, longitude_deg, *, altitude_m=0.0, rf_hz=11.5e9):
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

        if not (-90 <= latitude_deg <= 90 and -180 <= longitude_deg <= 180):
            raise ValueError("geodetic coordinate outside domain")
        if not np.isfinite(altitude_m) or not np.isfinite(rf_hz) or rf_hz <= 0:
            raise ValueError("finite height and positive reference RF required")
        site = geodetic_to_ecef_km(latitude_deg, longitude_deg, altitude_m)
        up = ecef_to_enu_matrix(latitude_deg, longitude_deg)[2]
        ns, nk, dim = grid.positions.shape
        groups, arms, nt = grid.index.shape
        if (
            dim != 3
            or nk < 2
            or grid.velocities.shape != grid.positions.shape
            or groups not in (1, ns)
            or arms != 3
            or grid.fraction.shape != grid.index.shape
            or grid.rotation.shape != (groups, 3, 2)
        ):
            raise ValueError("inconsistent orbit bank or interpolation stencil")
        f, e, h = (np.empty((ns, nt)) for _ in range(3))
        error = self.call(
            grid.positions,
            grid.velocities,
            ns,
            nk,
            nt,
            len(grid.index),
            grid.index,
            grid.fraction,
            grid.rotation,
            grid.step,
            site,
            up,
            rf_hz,
            f,
            e,
            h,
        )
        if error == 2:
            raise ValueError("interpolation index outside orbit bank")
        if error:
            raise ValueError("positive finite satellite ranges required")
        np.clip(e, -1.0, 1.0, out=e)
        np.arcsin(e, out=e)
        np.rad2deg(e, out=e)
        self.calls += 1
        self.max_bytes = max(self.max_bytes, grid.bytes)
        # The reference owns four 3-vector and four scalar double grids per cell.
        self.max_original_bytes = max(self.max_original_bytes, 16 * 8 * ns * nt)
        return f, e, h


def worker(request, result, library, *, select_initial=None):
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        discovery,
        family_weighting,
        scan,
    )

    from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

    projector = Projector(library)

    def evaluate(grid, *args, **kwargs):
        return (projector.evaluate if isinstance(grid, Stencil) else phase_linear_frequency)(
            grid, *args, **kwargs
        )

    with ExitStack() as stack:
        stack.enter_context(patch.object(scan, "prepare_phase_geometry", prepare))
        for m in (scan, discovery, family_weighting, conservative_recovery):
            stack.enter_context(patch.object(m, "phase_linear_frequency", evaluate))
        options = {} if select_initial is None else {"select_initial": select_initial}
        v5_core.worker(request, result, **options)
    out = json.loads(Path(result).read_bytes())
    out["metrics"].update(
        compact_projections=projector.calls,
        max_prepared_bytes=projector.max_bytes,
        original_grid_bytes_at_largest_shape=projector.max_original_bytes,
        kernel_sha256=hashlib.sha256(KERNEL.read_bytes()).hexdigest(),
    )
    from tools.pipeline_eval.__main__ import save_json

    save_json(Path(result), out)


def run(case, work_dir):
    lib = Path(work_dir) / "orbit_projector.so"
    compile_kernel(lib)
    result = v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(lib),))
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
