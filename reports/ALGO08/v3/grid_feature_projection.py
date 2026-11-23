"""Experimental fixed-view observer projection and curved design preparation."""

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
MATRIX_SOURCES = ("hardware", "smooth", "constants", "flat_labels")


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


class Design:
    """Own input snapshots and a template per view for one sampler call."""

    def __init__(self, original):
        self.original = original
        self.views = {}
        self.counts = Counter()

    def assemble(self, problem, derivative, modes, scales):
        rows = len(derivative)
        arrays = tuple(getattr(problem, key) for key in MATRIX_SOURCES)
        supported = tuple(problem.supported_local)
        labels = problem.flat_labels
        if (len(problem.supported) != len(supported)
                or len(set(supported)) != len(supported)
                or len(problem.labels) != len(problem.phase_sigma)
                or not contiguous(derivative, (rows,))
                or not contiguous(modes, (rows, 3))
                or not contiguous(labels, (rows,), np.int64)
                or not np.array_equal(scales, [1., 1., 1.])
                or any(a.dtype != np.float64 for a in (*arrays[:3], problem.q, problem.phase_sigma))):
            self.counts["design_fallback"] += 1
            return self.original(problem, derivative, modes, scales)
        key = id(problem)
        if key not in self.views:
            matrix = self.original(problem, np.zeros_like(derivative), np.zeros_like(modes), scales)
            first_phase = problem.hardware.shape[1] + problem.smooth.shape[1]
            slots = np.full(len(problem.labels), -1, dtype=np.intp)
            slots[list(supported)] = np.arange(len(supported))
            column = slots[labels]
            active = np.flatnonzero(column >= 0)
            orbit = first_phase + len(problem.labels) + 3 * column[active, None] + np.arange(3)
            self.views[key] = (problem, matrix, tuple(a.copy() for a in arrays), supported,
                               np.arange(rows), first_phase + labels, active, orbit)
            self.counts["design_views"] += 1
        _, template, snapshot, current, index, phase, active, orbit = self.views[key]
        if supported != current or not all(exact(a, b) for a, b in zip(arrays, snapshot, strict=True)):
            self.counts["design_fallback"] += 1
            return self.original(problem, derivative, modes, scales)
        features = template.copy()
        features[index, phase] = problem.q * derivative * problem.phase_sigma[labels]
        features[active[:, None], orbit] = problem.q[active, None] * modes[active] * scales[2]
        self.counts["template_design"] += 1
        return features
