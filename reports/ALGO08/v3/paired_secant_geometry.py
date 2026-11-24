"""Prepare the original two position probes together without sharing their scores."""

from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
from inspect import getsource
from pathlib import Path
import subprocess
from time import process_time_ns
from types import FunctionType
from unittest.mock import patch

import numpy as np

from grid_feature_projection import FLAGS, PHASE_SHA, contiguous, exact, supported_cpu
from grid_phase_state_reuse import SOURCES, identical, prepared_features


SECANT = "5bceea78eaece66c20f1e12c1fd109182a8cc5cc2e8b6d410f2d68d93e9110a3"
GRID_C = "bdfc20a3acd1fce79897839252ae4abb6da3bfb3ce3929ffa67ed167adb22e6a"
CACHE = "_fixed_phase_geometry_cache"


def build(path):
    source = Path(__file__).with_suffix(".c")
    if not supported_cpu():
        raise ValueError("The exact binary64 comparison was frozen for this x86-64 provider")
    if sha256(source.with_name("grid_feature_projection.c").read_bytes()).hexdigest() != GRID_C:
        raise ValueError("Expected the reviewed binary64 projection primitives")
    subprocess.run(["cc", *FLAGS, source, "-lm", "-o", path], check=True, timeout=20)


def projection_inputs(problem):
    buffers = tuple(bank[key] for bank in (problem.sky, problem.mode_bank)
                    for key in ("time_s", "position_km", "velocity_km_s"))
    grid = tuple((a.dtype.str, a.shape, a.tobytes()) for a in
                 map(np.asarray, (problem.flat_times, problem.flat_labels, problem.reference)))
    return buffers, grid


class PairedProjection:
    def __init__(self, path):
        library = ct.CDLL(str(path))
        self.project = library.project_secant_pair
        self.project.argtypes = [ct.c_size_t] + [ct.c_void_p] * 13
        self.project.restype = ct.c_int

    def __call__(self, center, shifts, coordinates):
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

        states = center.position_km, center.velocity_km_s, *shifts[0], *shifts[1]
        modes = center.mode_position_km, center.mode_velocity_km_s
        rows = len(states[0])
        if (not rows or len(coordinates) != 2 or not all(contiguous(a, (rows, 3)) for a in states)
                or not all(contiguous(a, (rows, 3, 3)) for a in modes)
                or not all(abs(lat) <= 90 and abs(lon) <= 180 for lat, lon in coordinates)):
            return None
        observers = np.stack([geodetic_to_ecef_km(*place, 0.) for place in coordinates])
        lines, frequency, derivative, physical = (
            np.empty((2, rows, 3)), np.empty((2, rows)), np.empty((2, rows)), np.empty((2, rows, 3)),
        )
        if not self.project(rows, *(a.ctypes.data for a in (
            observers, *states, *modes, lines, frequency, derivative, physical,
        ))):
            return None
        result = []
        for i, place in enumerate(coordinates):
            east, north, up = (lines[i] @ ecef_to_enu_matrix(*place).T).T
            elevation = np.rad2deg(np.arctan2(up, np.hypot(east, north)))
            result.append((frequency[i], elevation, derivative[i], physical[i]))
        return result


class Experiment:
    def __init__(self, secant, phase, predictive, native):
        if (sha256(Path(secant.__code__.co_filename).read_bytes()).hexdigest() != SECANT
                or sha256(getsource(phase).encode()).hexdigest() != PHASE_SHA):
            raise ValueError("The installed optimizer or curved geometry boundary changed")
        self.phase, self.predictive, self.native = phase, predictive, native
        self.prepared = prepared_features(predictive, phase)
        self.mode = "outside"
        self.samples = {name: Counter() for name in ("outside", "stock", "pair", "cache")}
        self.arm_samples = None
        self.owner = self.queue = self.hashes = self.predictive_view = None
        self.column = self.checked = self.predictive_checked = False
        self.secant = FunctionType(secant.__code__, dict(secant.__globals__, _forward_points=self.points),
                                   secant.__name__, secant.__defaults__, secant.__closure__)
        self.secant.__kwdefaults__ = secant.__kwdefaults__.copy()
        self.original_points = secant.__globals__["_forward_points"]

    @property
    def counts(self):
        return self.samples[self.mode] if self.arm_samples is None else self.arm_samples

    def geometry(self, owner, point):
        if not self.column and self.owner is None:
            return self.phase(owner, point)
        before = process_time_ns()
        role = "column" if self.column else "other"
        count = self.counts
        queued = self.queue
        observed = expected = None
        if (queued is not None and owner is self.owner and getattr(owner, CACHE, None) is queued[0]
                and len(queued[1]) and queued[1][0][0] == point.tobytes()):
            _, expected = queued[1].pop(0)
            if self.checked:
                observed = expected
                count["served_columns"] += 1
        if observed is None:
            observed = self.phase(owner, point)
            if expected is not None and not self.checked:
                self.checked = all(exact(a, b) for a, b in zip(observed, expected, strict=True))
                if not self.checked:
                    self.queue = None
                    count["comparison_failure"] += 1
                count["comparison"] += 1
        count[role + "_projection_ns"] += process_time_ns() - before
        count[role + "_projections"] += 1
        return observed

    def points(self, point, low, high, step):
        points = tuple(self.original_points(point, low, high, step))
        self.counts["refreshes"] += 1
        self.column = True
        try:
            if self.mode in ("pair", "cache"):
                self.prepare_pair(points)
            yield from points
        finally:
            self.column = False
            self.queue = None

    def prepare_pair(self, points):
        before = process_time_ns()
        owner = self.owner
        cache = getattr(owner, CACHE, None)
        try:
            if cache is not None:
                buffers, grid = projection_inputs(owner)
                if grid == cache[1] and all(a is b for a, b in zip(cache[0], buffers, strict=True)):
                    coordinates = [owner.scan.search_region.latlon(xy) for _, xy, _ in points]
                    result = self.native(cache[2], cache[3], coordinates)
                    if result is not None:
                        self.queue = cache, [(xy.tobytes(), value)
                                             for (_, xy, _), value in zip(points, result, strict=True)]
                        self.counts["batch_calls"] += 1
                        return
            self.counts["batch_fallback"] += 1
        finally:
            self.counts["batch_prepare_ns"] += process_time_ns() - before

    def predictive_geometry(self, view, point, altitude):
        start = process_time_ns()
        if self.mode == "cache":
            if view is not self.predictive_view:
                self.predictive_view = view
                self.predictive_checked = False
                candidate = self.prepared(view, point, altitude)
                result = self.predictive(view, point, altitude)
                self.predictive_checked = identical(candidate, result)
                self.counts["predictive_check"] += 1
                self.counts["predictive_comparison_failure"] += not self.predictive_checked
            elif self.predictive_checked:
                result = self.prepared(view, point, altitude)
            else:
                result = self.predictive(view, point, altitude)
        else:
            result = self.predictive(view, point, altitude)
        self.counts[("column" if self.column else "other") + "_predictive_ns"] += process_time_ns() - start
        self.counts["predictive_calls"] += 1
        return result

    def optimize(self, residual, *args, **kwargs):
        self.owner = getattr(residual, "__self__", None)
        self.checked = False
        evaluated = 0
        count = self.counts
        count["fits"] += 1

        def objective(point):
            nonlocal evaluated
            role = "column" if self.column else ("start" if evaluated == 0 else "trial")
            before = process_time_ns()
            result = residual(point)
            count[role + "_objective_ns"] += process_time_ns() - before
            count[role + "_calls"] += 1
            evaluated += 1
            if self.hashes is not None:
                before = process_time_ns()
                self.hashes.update(np.asarray(point).tobytes())
                self.hashes.update(result.tobytes())
                count["diagnostic_hash_ns"] += process_time_ns() - before
            return result

        before = process_time_ns()
        try:
            result = self.secant(objective, *args, **kwargs)
        finally:
            count["optimizer_ns"] += process_time_ns() - before
            self.owner = self.queue = None
        count["rejected_trials"] += result["rejected_trials"]
        return result

    @contextmanager
    def treatment(self, mode):
        self.mode = mode
        self.arm_samples = Counter()
        self.hashes = sha256()
        try:
            yield self.arm_samples, self.hashes
        finally:
            self.samples[mode].update(self.arm_samples)
            self.arm_samples = self.hashes = self.predictive_view = None
            self.mode = "outside"


@contextmanager
def binding(native):
    from leo.analysis.localization_v3 import marginal, predictive_linear
    from tools.pipeline_eval.variants import v5_direct_cavity

    if sha256(Path(predictive_linear.__file__).read_bytes()).hexdigest() != SOURCES["predictive_linear"]:
        raise ValueError("Expected the original predictive-feature boundary")
    study = Experiment(v5_direct_cavity.bounded_secant, marginal._phase_geometry,
                       predictive_linear.geometry_features, native)
    with (patch.object(v5_direct_cavity, "bounded_secant", study.optimize),
          patch.object(marginal, "_phase_geometry", study.geometry),
          patch.object(predictive_linear, "geometry_features", study.predictive_geometry)):
        yield study
