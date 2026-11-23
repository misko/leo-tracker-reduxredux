"""Experimental fixed-view observer projection and selected design packing."""

from collections import Counter
import ctypes as ct
from hashlib import sha256
from inspect import getsource
from pathlib import Path
import subprocess

import numpy as np


PHASE_SHA = "0e067ad8d0d7a69bda355e3c46c409e3ecd3fc469447a80aabb21f7bfaeb4a63"
FLAGS = (
    "-std=c11", "-O3", "-march=haswell", "-fno-fast-math", "-fno-math-errno",
    "-ffp-contract=off", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
)


def build(output):
    source = Path(__file__).with_suffix(".c")
    subprocess.run(["cc", *FLAGS, str(source), "-lm", "-o", str(output)], check=True, timeout=20)


def contiguous(array, shape, dtype=np.float64):
    return (type(array) is np.ndarray and array.dtype == dtype and array.shape == shape
            and array.flags.c_contiguous and array.flags.aligned)


def exact(left, right):
    return (left.shape == right.shape and left.dtype == right.dtype and left.strides == right.strides
            and np.array_equal(left.view(np.uint64), right.view(np.uint64)))


class Native:
    def __init__(self, path):
        library = ct.CDLL(str(path))
        self.project = library.project_grid_phase
        self.project.argtypes = [ct.c_size_t] + [ct.c_void_p] * 13
        self.project.restype = ct.c_int
        self.select = library.select_grid_design
        self.select.argtypes = [ct.c_size_t, ct.c_size_t] + [ct.c_void_p] * 4
        self.select.restype = None
        self.counts = Counter()

    def projection(self, center, shifts, latitude, longitude):
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

        nominal = center.position_km, center.velocity_km_s
        local = *nominal, *shifts[0], *shifts[1]
        rows = len(nominal[0])
        modes = center.mode_position_km, center.mode_velocity_km_s
        if (not rows or not all(contiguous(a, (rows, 3)) for a in local)
                or not all(contiguous(a, (rows, 3, 3)) for a in modes)
                or not abs(latitude) <= 90 or not abs(longitude) <= 180):
            return None
        observer = geodetic_to_ecef_km(latitude, longitude, 0.)
        line, frequency, derivative, physical = (
            np.empty((rows, 3)), np.empty(rows), np.empty(rows), np.empty((rows, 3)),
        )
        if not self.project(rows, *(a.ctypes.data for a in (
            observer, *local, *modes, line, frequency, derivative, physical,
        ))):
            return None
        east, north, up = (line @ ecef_to_enu_matrix(latitude, longitude).T).T
        elevation = np.rad2deg(np.arctan2(up, np.hypot(east, north)))
        return frequency, elevation, derivative, physical

    def phase(self, original, *, verify=False):
        source = getsource(original)
        if sha256(source.encode()).hexdigest() != PHASE_SHA:
            raise ValueError("Expected the pinned cached phase geometry")
        checked = {}

        def projected(center, shifts, *coordinates):
            key = id(center)
            if key in checked and not checked[key][1]:
                self.counts["projection_fallback"] += 1
                return baseline_projection(center, shifts, coordinates)
            candidate = self.projection(center, shifts, *coordinates)
            if candidate is not None and not verify and key in checked:
                self.counts["native_projection"] += 1
                return candidate
            baseline = baseline_projection(center, shifts, coordinates)
            matches = candidate is not None and all(exact(a, b) for a, b in zip(candidate, baseline, strict=True))
            checked[key] = center, matches
            if not matches:
                self.counts["projection_fallback"] += 1
                return baseline
            self.counts["exact_projection_checks"] += 1
            return candidate

        def baseline_projection(center, shifts, coordinates):
            expected = center.evaluate(*coordinates)
            offset = [original.__globals__["phase_frequency_from_states"](*a, *coordinates)[0] for a in shifts]
            return expected[0], expected[1], (offset[0] - offset[1]) / 0.02, expected[2]

        anchor = "    frequency, elevation, modes = cached[2].evaluate"
        index = source.index(anchor)
        scope = dict(original.__globals__, projected=projected)
        exec(compile(source[:index] + "    return projected(cached[2], cached[3], *coordinates)\n",
                     original.__code__.co_filename, "exec"), scope)
        return scope[original.__name__]

    def selected_design(self, source, scale, keep, fallback):
        if type(source) is not np.ndarray or source.ndim != 2:
            self.counts["selection_fallback"] += 1
            return fallback(source, scale, keep)
        rows, width = source.shape
        if (not contiguous(source, (rows, width)) or not contiguous(scale, (width,))
                or not contiguous(keep, (rows,), np.bool_)
                or not np.isfinite(scale).all()):
            self.counts["selection_fallback"] += 1
            return fallback(source, scale, keep)
        output = np.empty((np.count_nonzero(keep), width))
        self.select(rows, width, *(a.ctypes.data for a in (source, scale, keep, output)))
        self.counts["native_selection"] += 1
        return output
