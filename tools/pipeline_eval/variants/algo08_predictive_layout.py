"""Reuse fixed predictive rows while preserving the original Gaussian arithmetic."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from inspect import getsource
from threading import Lock
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import event_position, marginal, predictive_linear

MAX_SCRATCH_BYTES = 16 * 1024**2


def stock_gram(problem, powers, result):
    groups = problem.noise_groups[problem.keep]
    weights = np.asarray(powers)[groups] * result["noise_precision"][groups] / (
        problem.point_noise[problem.keep] ** 2
    )
    features = result["features"][problem.keep]
    return np.diag(result["coefficient_prior_precision"]) + features.T @ (
        features * weights[:, None]
    )


class CurvedRows:
    """Scratch for the exact selected rows and the weighted right product."""

    def __init__(self, problem, powers, width):
        self.keep = problem.keep.copy()
        self.indexes = np.flatnonzero(self.keep)
        self.noise = problem.point_noise.copy()
        self.noise_groups = problem.noise_groups.copy()
        self.powers = np.asarray(powers).copy()
        self.groups = self.noise_groups[self.keep]
        self.power = self.powers[self.groups]
        self.variance = self.noise[self.keep] ** 2
        self.take = self.indexes.size != self.keep.size
        shape = (len(self.indexes), width)
        self.selected = np.empty(shape) if self.take else None
        self.weighted = np.empty(shape)

    def gram(self, problem, powers, result):
        matrix = result["features"]
        if (
            not matrix.flags.c_contiguous
            or matrix.dtype != np.float64
            or matrix.shape != (self.keep.size, self.weighted.shape[1])
            or not np.array_equal(self.keep, problem.keep)
            or not np.array_equal(self.noise_groups, problem.noise_groups)
            or not np.array_equal(self.noise, problem.point_noise)
            or not np.array_equal(self.powers, powers)
        ):
            return None
        weights = self.power * result["noise_precision"][self.groups] / self.variance
        features = matrix
        if self.take:
            features = self.selected
            np.take(matrix, self.indexes, axis=0, out=features, mode="clip")
        np.multiply(features, weights[:, None], out=self.weighted)
        return np.diag(result["coefficient_prior_precision"]) + features.T @ self.weighted


class GeometryRows:
    """Build the static parts and sparse slots of the privately owned predictive view."""

    def __init__(self, view):
        self.view = view
        hardware = view.hardware.copy()
        hardware[:, [4, 6]] *= 10
        count = len(view.flat_times)
        phase_start = hardware.shape[1] + view.smooth.shape[1]
        orbit_start = phase_start + len(view.labels)
        self.rows = np.arange(count)
        self.phase_columns = phase_start + view.flat_labels
        self.orbit = [
            (np.flatnonzero(view.flat_labels == label),
             slice(orbit_start + 3 * k, orbit_start + 3 * k + 3))
            for k, label in enumerate(view.supported_local)
        ]
        self.features = np.column_stack((
            hardware, view.smooth * 200, np.zeros((count, len(view.labels))),
            np.zeros((count, 3 * len(view.supported))), view.constants,
        ))

    def evaluate(self, position):
        view = self.view
        frequency, elevation, derivative, modes = marginal._phase_geometry(view, position)
        intercept = marginal.absolute_phase_linearization(
            frequency, derivative, view.reference[view.flat_labels]
        )
        self.features[self.rows, self.phase_columns] = (
            view.q * derivative * view.phase_sigma[view.flat_labels]
        )
        for rows, columns in self.orbit:
            self.features[rows, columns] = view.q[rows, None] * modes[rows]
        return self.features, intercept, elevation


class PredictiveRows:
    """The stock predictive Gaussian with fixed noise and curve bias columns."""

    def __init__(self, sigma, groups, width):
        self.noise = sigma * np.sqrt(2)
        self.observation_ones = np.ones(len(groups))
        bias_count = int(groups.max()) + 1
        self.biases = np.zeros((len(groups), bias_count))
        self.biases[np.arange(len(groups)), groups] = 300.
        self.design = None
        self.prior = np.ones(width + bias_count)

    def residual(self, raw, design, curved_gram):
        root = np.linalg.cholesky(curved_gram)
        uncertainty = np.linalg.solve(root, design.T).T
        if self.design is None:
            self.design = np.column_stack((uncertainty, self.biases))
        else:
            self.design[:, :design.shape[1]] = uncertainty
        return predictive_linear.conditional_gaussian(
            raw, self.design, self.noise, self.observation_ones, self.observation_ones,
            self.prior, 1.,
        )


class Plan:
    def __init__(self, problem, view, powers, sigma, groups):
        self.geometry = GeometryRows(view)
        width = self.geometry.features.shape[1]
        self.gram = CurvedRows(problem, powers, width)
        self.predictive = PredictiveRows(sigma, groups, width)
        self.lock = Lock()


def make_plan(problem, view, powers, sigma, groups, design, stats):
    width = view.hardware.shape[1] + view.smooth.shape[1] + len(view.labels)
    width += 3 * len(view.supported) + view.constants.shape[1]
    storage = (
        2 * int(problem.keep.sum()) * width
        + len(sigma) * (2 * width + 2 * (int(groups.max()) + 1))
    ) * np.dtype(float).itemsize
    if view.variant == "empirical" or design.shape[1] or storage > MAX_SCRATCH_BYTES:
        stats["unsupported_layouts"] += 1
        return None
    try:
        prepared = Plan(problem, view, powers, sigma, groups)
    except MemoryError:
        stats["unsupported_layouts"] += 1
        return None
    stats["scaffolds"] += 1
    return prepared


def prediction_terms(
    plan, problem, view, powers, values, sigma, groups, design, c, position, stats,
):
    mode = plan is not None and plan.lock.acquire(blocking=False)
    try:
        start = process_time_ns()
        gram = plan.gram.gram(problem, powers, c) if mode else None
        if gram is None:
            if plan is not None:
                stats["replayed_gram"] += 1
            gram = stock_gram(problem, powers, c)
        stats["gram_ns"] += process_time_ns() - start

        start = process_time_ns()
        if mode:
            features, intercept, elevation = plan.geometry.evaluate(position)
        else:
            geometry = event_position.geometry_features(view, position, 0.0)
            features = np.column_stack((geometry["features"], design))
            intercept, elevation = geometry["intercept"], geometry["elevation"]
        stats["geometry_ns"] += process_time_ns() - start

        start = process_time_ns()
        predicted = view.q * intercept + features @ c["coefficient"]
        raw = values - predicted
        if mode:
            prediction = plan.predictive.residual(raw, features, gram)
            stats["prepared_calls"] += 1
        else:
            prediction = event_position.predictive_residual(
                raw, features, gram, sigma * np.sqrt(2), groups
            )
        stats["predictive_gaussian_ns"] += process_time_ns() - start
        return predicted, prediction, elevation
    finally:
        if mode:
            plan.lock.release()


def instrument(original, enabled, stats):
    source = getsource(original)
    beginning = "    curved = p.calculate\n"
    first = "        c = curved(position)\n"
    last = '        c["curved_negative_twice_elbo"]'
    if source.count(beginning) != 1 or source.count(first) != 1 or source.count(last) != 1:
        raise ValueError("Unexpected event predictive likelihood")
    before, after = source.index(first), source.index(last)
    source = source[:before] + """        started = process_time_ns()
        c = curved(position)
        stats["curved_ns"] += process_time_ns() - started
        stats["prediction_calls"] += 1
        predicted, prediction, elevation = prediction_terms(
            plan, p, view, powers, values, sigma, groups, design, c, position, stats
        )
""" + source[after:]
    source = source.replace(beginning, beginning + """
    started = process_time_ns()
    plan = make_plan(p, view, powers, sigma, groups, design, stats) if enabled else None
    stats["setup_ns"] += process_time_ns() - started
""")
    source = source.replace('c["linear_elevation"] = geometry["elevation"]',
                            'c["linear_elevation"] = elevation')
    names = dict(vars(event_position), make_plan=make_plan, process_time_ns=process_time_ns,
                 prediction_terms=prediction_terms, stats=stats, enabled=enabled)
    exec(compile(source, original.__code__.co_filename, "exec"), names)
    return names[original.__name__]


@contextmanager
def measured_prediction(*, enabled):
    """Bind the event predictive port and its existing solver/publication callers."""
    from leo.analysis.localization_v3 import (
        family_cavity,
        feasible,
        joint_recovery,
        prediction,
        recovery_inclusion,
        recovery_inventory,
    )

    stats = Counter()
    original = event_position.attach_event_predictive
    calculate = instrument(original, enabled, stats)
    with ExitStack() as stack:
        for module in (event_position, family_cavity, feasible, joint_recovery, prediction,
                       recovery_inclusion, recovery_inventory):
            if getattr(module, "attach_event_predictive") is original:
                stack.enter_context(patch.object(module, "attach_event_predictive", calculate))
        yield stats
