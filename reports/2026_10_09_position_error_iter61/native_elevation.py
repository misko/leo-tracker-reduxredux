"""Private prebuilt research kernel; missing library is an explicit failure."""

import ctypes
from pathlib import Path

import numpy as np

from leo.analysis.regional_position_score import observer

_library = ctypes.CDLL(str(Path(__file__).resolve().parent / "local/elevation.so"))
_kernel = _library.elevation
_array = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
_kernel.argtypes = [ctypes.c_int] * 3 + [ctypes.c_double] * 2 + [_array] * 10
_kernel.restype = ctypes.c_int


def predict_elevation(bank, observations, prior, point, shifts_s):
    times, shifts, positions, nodes = [
        np.ascontiguousarray(v, dtype=np.float64)
        for v in (observations.times_s, shifts_s, bank.position_km, bank.nodes_s)
    ]
    n, k, t = len(times), len(bank.numbers), len(nodes)
    if (
        n < 1
        or k < 1
        or t < 2
        or max(n, k, t) >= 2**31
        or times.shape != (n,)
        or shifts.shape != (k,)
        or positions.shape != (k, t, 3)
        or nodes.shape != (t,)
        or not all(np.isfinite(v).all() for v in (times, shifts, positions, nodes))
        or nodes[1] <= nodes[0]
        or not np.allclose(np.diff(nodes), nodes[1] - nodes[0], rtol=1e-12, atol=1e-12)
    ):
        raise ValueError("invalid native elevation inputs")
    site, up = observer(prior, point)
    chart = np.array(
        [
            (
                np.asarray(observer(prior, np.asarray(point) + d))
                - np.asarray(observer(prior, np.asarray(point) - d))
            )
            / 0.002
            for d in np.eye(2) * 0.001
        ]
    )
    site, up, site_jac, up_jac = [
        np.ascontiguousarray(v, dtype=np.float64) for v in (site, up, chart[:, 0], chart[:, 1])
    ]
    if not all(np.isfinite(v).all() for v in (site, up, site_jac, up_jac)):
        raise ValueError("invalid observer geometry")
    angle, spatial, timing = np.empty((n, k)), np.empty((n, k, 2)), np.empty((n, k))
    status = _kernel(
        n,
        k,
        t,
        nodes[0],
        nodes[1] - nodes[0],
        times,
        shifts,
        positions,
        site,
        up,
        site_jac,
        up_jac,
        angle,
        spatial,
        timing,
    )
    if status:
        raise ValueError(f"native elevation failed: {status}")
    return angle, spatial, timing
