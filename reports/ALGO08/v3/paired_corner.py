"""Experimental pair of ordinary cold projections with one stencil traversal."""

import ctypes
from hashlib import sha256
from pathlib import Path
import subprocess

import numpy as np


SOURCE = Path(__file__).with_suffix(".c")
STOCK_C = "47d8605da701d4426d2a3a6f8a3e9dd272b1499a9f5e0b19e406087ff211a28f"
STOCK_PY = "873b856dd081269234f9af8415e7c1abaa00afb27c991dad43ab24e0764dd668"
MAX_LOOKAHEAD_BYTES = 128 * 1024**2


def build(ordinary, binary):
    """Build with the released source and floating point flags."""
    source = Path(ordinary.__file__)
    declarations = source.with_suffix(".c")
    for path, expected in ((source, STOCK_PY), (declarations, STOCK_C)):
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("The original native projection source changed")
    subprocess.run(["cc", *ordinary.FLAGS, "-I", str(source.parent), str(SOURCE), "-lm", "-o", str(binary)], check=True)


def frozen(array, kind=np.float64):
    return (type(array) is np.ndarray and array.dtype == np.dtype(kind) and array.flags.c_contiguous
            and array.flags.aligned and not array.flags.writeable)


class PairProjector:
    def __init__(self, ordinary, binary):
        from tools.pipeline_eval.variants.orbit_projector import Projector

        if type(ordinary) is not Projector:
            raise ValueError("Expected the released ordinary projector")
        self.call = ctypes.CDLL(str(Path(binary).resolve())).project_orbit_pair
        real = np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED"))
        integer = np.ctypeslib.ndpointer(dtype=np.int64, flags=("C_CONTIGUOUS", "ALIGNED"))
        self.call.argtypes = [real, real, *([ctypes.c_size_t] * 4), integer, real, real, ctypes.c_double,
                              real, real, ctypes.c_double, *([real] * 6)]
        self.call.restype = ctypes.c_int

    def evaluate(self, grid, locations, *, altitude_m=0., rf_hz=11.5e9):
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
        from tools.pipeline_eval.variants.orbit_projector import Stencil

        if type(grid) is not Stencil or not all(frozen(a) for a in (
            grid.positions, grid.velocities, grid.fraction, grid.rotation,
        )) or not frozen(grid.index, np.int64):
            raise ValueError("Expected the released immutable orbit stencil")
        ns, nk, dim = grid.positions.shape
        groups, arms, nt = grid.index.shape
        if (dim != 3 or nk < 2 or grid.velocities.shape != grid.positions.shape or groups not in (1, ns)
                or arms != 3 or grid.fraction.shape != grid.index.shape or grid.rotation.shape != (groups, 3, 2)
                or not np.isfinite(grid.step) or grid.step <= 0):
            raise ValueError("Inconsistent orbit bank or interpolation stencil")
        coordinates = np.asarray(locations, dtype=np.float64)
        if (coordinates.shape != (2, 2) or not np.isfinite(coordinates).all()
                or np.any(np.abs(coordinates) > (90, 180)) or not np.isfinite(altitude_m)
                or not np.isfinite(rf_hz) or rf_hz <= 0):
            raise ValueError("Expected two legal geographic points and a common height and RF")
        sites = np.stack([geodetic_to_ecef_km(lat, lon, altitude_m) for lat, lon in coordinates])
        ups = np.stack([ecef_to_enu_matrix(lat, lon)[2] for lat, lon in coordinates])
        planes = tuple(np.empty((ns, nt)) for _ in range(6))
        error = self.call(grid.positions, grid.velocities, ns, nk, nt, groups, grid.index, grid.fraction,
                          grid.rotation, grid.step, sites, ups, rf_hz, *planes)
        if error == 2:
            raise ValueError("interpolation index outside orbit bank")
        if error:
            raise ValueError("positive finite satellite ranges required")
        for elevation in (planes[1], planes[4]):
            np.clip(elevation, -1., 1., out=elevation)
            np.arcsin(elevation, out=elevation)
            np.rad2deg(elevation, out=elevation)
        return planes[:3], planes[3:]


def ordered_corners(operation, grid, locations, pair, counters, *, limit=MAX_LOOKAHEAD_BYTES):
    """Serve one pair in its original order, with ordinary projection on mismatch."""
    points = tuple(np.asarray(point, dtype=np.float64).tobytes() for point in locations)
    if len(points) != 2:
        raise ValueError("Schedule exactly two consecutive nominal queries")
    ready = None
    started = False
    footprint = grid.positions.shape[0] * grid.index.shape[-1] * 3 * np.dtype(np.float64).itemsize

    def project(current, latitude, longitude, **options):
        nonlocal ready, started
        if current is grid and not options:
            point = np.asarray((latitude, longitude), dtype=np.float64).tobytes()
            if ready is not None and point == points[1]:
                second, ready = ready, None
                counters["served_second"] += 1
                return second
            if ready is not None:
                ready = None
            if not started:
                started = True
                if point == points[0] and points[0] != points[1] and footprint <= limit:
                    try:
                        first, ready = pair.evaluate(grid, locations)
                    except (ValueError, MemoryError):
                        counters["pair_fallback"] += 1
                    else:
                        counters["paired_calls"] += 1
                        counters["lookahead_bytes"] += footprint
                        return first
        counters["ordinary_calls"] += 1
        return operation(current, latitude, longitude, **options)

    return project
