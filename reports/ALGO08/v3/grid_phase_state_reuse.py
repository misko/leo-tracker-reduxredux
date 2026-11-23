"""Reuse exact phase interpolation in the installed predictive grid handoff."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


SOURCES = {
    "continuous_curve_fit": "693a580ccbf8b134858448e4700a9b495dc5b9cc301b7ffc3a1e5dae4fab847d",
    "event_position": "3a8c9bde7ddddc115fcb219f8588fd51188ef4081567d8e2fe91df8324418e9f",
    "marginal": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
    "orbit_uncertainty": "b6bf1a89c15abd071681241d7259ca0d2b9b97bc22bdf4f9b75f4c5d896fa370",
    "predictive_linear": "1c1930b8fc71b6fafd43fa744661a785b7d243b74b1ab39ab1f59d8fe800dcc6",
    "prepared_phase_geometry": "df57600e500f731e61b2636e03d682221b74e65b8b624ddb262942213cfbb01c",
}
HANDOFF_SHA256 = "aa5d7ab17ce82e4bd64e463de0fddf710275634cf48675cf6076eeba6c184831"
PRESENTATION_SHA256 = "5dd6dbc63a4078e4b7fffcf10237d4f92429a1ea07d585eb3a49d0eca02cae2b"
PHASE_CACHE = "_fixed_phase_geometry_cache"


def prepared_features(original, phase_geometry):
    """Keep predictive allocation and reductions, replacing just phase-state sourcing."""
    source = getsource(original)
    start = "    coordinates = p.scan.search_region.latlon(np.asarray(position)[:2])\n"
    end = "    intercept = absolute_phase_linearization(f, derivative, p.reference[p.flat_labels])\n"
    modes = "    modes = paired_frequency_modes(\n"
    orbital = "    orbital = np.zeros((len(f), 3 * len(p.supported)))\n"
    if any(source.count(anchor) != 1 for anchor in (start, end, modes, orbital)):
        raise ValueError("The pinned predictive geometry boundary changed")
    source = (source[:source.index(start)]
              + "    f, elevation, derivative, modes = _phase_geometry(p, np.asarray(position)[:2])\n"
              + source[source.index(end):source.index(modes)] + source[source.index(orbital):])
    globals_ = dict(original.__globals__, _phase_geometry=phase_geometry)
    exec(compile(source, original.__code__.co_filename, "exec"), globals_)
    operation = globals_[original.__name__]

    def geometry(view, position, altitude_m):
        if altitude_m != 0. or view.variant == "empirical":
            return original(view, position, altitude_m)
        return operation(view, position, altitude_m)

    return geometry


def identical(left, right):
    if left.keys() != right.keys():
        return False
    for key, a in left.items():
        b = right[key]
        if (a.dtype != b.dtype or a.shape != b.shape or a.strides != b.strides
                or not np.array_equal(a.view(np.uint64), b.view(np.uint64))):
            return False
    return True


def checked_geometry():
    from leo.analysis.localization_v3 import event_position, marginal, predictive_linear
    from leo.analysis.research import continuous_curve_fit, orbit_uncertainty, prepared_phase_geometry

    modules = (event_position, marginal, predictive_linear, continuous_curve_fit, orbit_uncertainty,
               prepared_phase_geometry)
    for module in modules:
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != SOURCES[module.__name__.split(".")[-1]]:
            raise ValueError(f"Unexpected release source for predictive grid geometry: {module.__name__}")
    original = event_position.geometry_features
    if original is not predictive_linear.geometry_features:
        raise ValueError("The installed grid no longer calls the original predictive geometry")
    return event_position, original, prepared_features(original, marginal._phase_geometry), (
        continuous_curve_fit, orbit_uncertainty, prepared_phase_geometry, marginal)


def sample_with_cached_features(sample, event, original, prepared, counts):
    """Install the geometry only for one invocation of the current grid sampler."""
    def grid(*args, **kwargs):
        if kwargs.get("map_batches") is not None or event.geometry_features is not original:
            counts["ordinary_grids"] += 1
            return sample(*args, **kwargs)
        counts["grids"] += 1
        views = {}
        absent = object()

        def geometry(view, position, altitude_m):
            if type(view) is not SimpleNamespace or altitude_m != 0. or view.variant == "empirical":
                counts["ordinary_calls"] += 1
                return original(view, position, altitude_m)
            key = id(view)
            if key not in views:
                views[key] = view, getattr(view, PHASE_CACHE, absent)
                counts["prepared_views"] += 1
            counts["prepared_calls"] += 1
            return prepared(view, position, altitude_m)

        try:
            with patch.object(event, "geometry_features", geometry):
                return sample(*args, **kwargs)
        finally:
            for view, previous in views.values():
                if previous is absent:
                    vars(view).pop(PHASE_CACHE, None)
                else:
                    setattr(view, PHASE_CACHE, previous)

    return grid


@contextmanager
def cached_predictive_grid(*, bind=None):
    """Reuse predictive phase states while the current publication grid callback runs."""
    from leo.presentation import localization_v3 as presentation
    from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

    for module, expected in ((handoff, HANDOFF_SHA256), (presentation, PRESENTATION_SHA256)):
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Unexpected source for the checked grid handoff: {module.__name__}")
    event, original, prepared, _ = checked_geometry()
    counts = Counter(grids=0, prepared_views=0, prepared_calls=0)
    sample = presentation.sample_position_grid
    if bind is not None:
        sample, prepared = bind(sample, original, prepared)
    grid = sample_with_cached_features(sample, event, original, prepared, counts)
    with patch.object(presentation, "sample_position_grid", grid):
        yield counts


class GridAudit:
    """Compare the geometries once per genuine predictive objective call."""

    def __init__(self):
        self.work = Counter()
        self.calls = []
        self.domain = "curved"
        self.point = None
        self.clocks = None
        self.views = {}

    def interpolate(self, original):
        def timed(bank, times, labels, phases):
            start = process_time_ns()
            values = original(bank, times, labels, phases)
            self.work[self.domain + "_interpolation_cpu_ns"] += process_time_ns() - start
            self.work[self.domain + "_interpolation_calls"] += 1
            self.work[self.domain + "_interpolated_rows"] += len(times)
            return values

        return timed

    def measure_geometry(self, original, candidate):
        def evaluate(view, position, altitude):
            views = self.views
            if id(view) not in views:
                # Retain the real object so identity cannot be reassigned to another view.
                views[id(view)] = view
            clocks, results = {}, {}
            order = ("released", "prepared") if len(self.calls) % 2 == 0 else ("prepared", "released")
            try:
                for kind in order:
                    self.domain = kind
                    operation = original if kind == "released" else candidate
                    start = process_time_ns()
                    results[kind] = operation(view, position, altitude)
                    clocks[kind] = process_time_ns() - start
            finally:
                self.domain = "curved"
            exact = identical(results["released"], results["prepared"])
            self.calls.append(dict(arm=self.point[0], point=self.point[1], rows=len(view.flat_times),
                                   altitude=altitude, clocks_ns=clocks, exact=exact))
            return results["prepared" if exact else "released"]

        return evaluate

    def grid(self, original):
        event_position, baseline, candidate, interpolators = checked_geometry()
        measured = self.measure_geometry(baseline, candidate)

        def with_audit(score, endpoints, **kwargs):
            if self.clocks is not None:
                raise ValueError("Expected one genuine saved grid")

            def point(arm, position):
                self.point = arm, tuple(position)
                try:
                    return score(arm, position)
                finally:
                    self.point = None

            start, wall = process_time_ns(), perf_counter_ns()
            with ExitStack() as scope:
                for module in interpolators:
                    scope.enter_context(patch.object(module, "paired_phase_states", self.interpolate(module.paired_phase_states)))
                scope.enter_context(patch.object(event_position, "geometry_features", measured))
                result = original(point, endpoints, **kwargs)
            self.clocks = dict(cpu_ns=process_time_ns()-start, elapsed_ns=perf_counter_ns()-wall)
            return result

        return with_audit

    def report(self):
        totals = {kind: sum(row["clocks_ns"][kind] for row in self.calls) for kind in ("released", "prepared")}
        return dict(grid_clocks=self.clocks, predictive_geometry_ns=totals,
                    measured_shared_and_pair_overhead_ns=self.clocks["cpu_ns"]-sum(totals.values()),
                    interpolation=dict(self.work), private_views=len(self.views), calls=self.calls)
