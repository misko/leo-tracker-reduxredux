"""Use a time-interpolated tangent for the first trust-region proposals."""

from dataclasses import dataclass, replace
from time import process_time

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.retained_position import PositionNormal
from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states
from tools.pipeline_eval.variants.algo08_track_moments import track_moments
from tools.pipeline_eval.variants.compact_cavity_optimizer import _forward_points, bounded_secant

MIN_ACTIVE_ROWS = 256
MAX_NODE_FRACTION = 0.6


@dataclass(frozen=True)
class TemporalLayout:
    nodes: np.ndarray
    blocks: tuple
    length: int

    def interpolate(self, values):
        full = np.empty((self.length, *values.shape[1:]))
        for rows, node_rows, transfer in self.blocks:
            full[rows] = transfer @ values[node_rows]
        return full


def temporal_layout(times, slices):
    indexes, blocks, start = [], [], 0
    for rows in slices:
        track = times[rows]
        moments = track_moments(track)
        stop = start + len(moments.nodes)
        indexes.append(rows.start + np.searchsorted(track, moments.nodes))
        blocks.append((rows, slice(start, stop), moments.basis @ moments.transfer))
        start = stop
    return TemporalLayout(np.concatenate(indexes), tuple(blocks), len(times))


def layout_for(problem):
    cache = getattr(problem.scan, "_temporal_trust_layout", None)
    times = problem.flat_times
    key = times.tobytes(), tuple((rows.start, rows.stop) for rows in problem.slices)
    if cache is None or cache[0] != key:
        cache = key, temporal_layout(times, problem.slices)
        problem.scan._temporal_trust_layout = cache
    return cache[1]


def profile_jacobian(design, prior, response_jacobian):
    """Project trial changes through the frozen Gaussian nuisance posterior."""
    normal = design.T @ design
    normal.flat[::len(normal) + 1] += prior
    root = cho_factor(normal, lower=True)
    shift = cho_solve(root, design.T @ response_jacobian)
    return response_jacobian - design @ shift, np.sqrt(prior[:, None]) * shift


def conditional_geometry(problem, calculation, layout):
    """Freeze the current nuisance means and evaluate orbit fields only at nodes."""
    nodes = layout.nodes
    _, _, prepared, states = problem._fixed_phase_geometry_cache
    short = replace(
        prepared,
        position_km=prepared.position_km[nodes], velocity_km_s=prepared.velocity_km_s[nodes],
        mode_position_km=prepared.mode_position_km[nodes],
        mode_velocity_km_s=prepared.mode_velocity_km_s[nodes],
    )
    phase_states = [(positions[nodes], velocities[nodes]) for positions, velocities in states]
    labels = problem.flat_labels[nodes]
    q = problem.q[nodes]
    coefficients = calculation["coefficient"]
    start = problem.hardware.shape[1] + problem.smooth.shape[1]
    stop = start + len(problem.labels)
    phases = coefficients[start:stop] * problem.phase_sigma - problem.reference
    modes = np.zeros((len(problem.labels), 3))
    modes[problem.supported_local] = coefficients[stop:stop + 3 * len(problem.supported)].reshape(
        -1, 3
    )

    def at(point):
        coordinates = problem.scan.search_region.latlon(point)
        frequency, elevation, basis = short.evaluate(*coordinates)
        plus, minus = [
            phase_frequency_from_states(*pair, *coordinates)[0] for pair in phase_states
        ]
        derivative = (plus - minus) / 0.02
        correction = np.einsum("nd,nd->n", modes[labels], basis)
        return np.column_stack((q * (frequency + phases[labels] * derivative + correction),
                                elevation))

    return at


def proposal_jacobian(problem, calculation, residual, layout, anchor, nearby):
    """Profile all observation rows using a short-grid conditional Doppler tangent."""
    geometry = conditional_geometry(problem, calculation, layout)
    center = geometry(anchor)
    fields = np.stack([(geometry(point) - center) / delta for _, point, delta in nearby],
                      axis=-1)
    full = layout.interpolate(fields.reshape(len(layout.nodes), -1)).reshape(-1, 2, 2)
    keep = problem.keep
    groups = problem.noise_groups[keep]
    weights = np.sqrt(calculation["noise_precision"][groups]) / problem.point_noise[keep]
    design = calculation["features"][keep] * weights[:, None]
    # The Jacobian is taken with fitted precisions, prior volume and Gamma
    # residuals frozen. The release likelihood recomputes those for every move.
    innovation, coefficients = profile_jacobian(
        design, calculation["coefficient_prior_precision"], -full[keep, 0] * weights[:, None]
    )
    count, width = design.shape
    jacobian = np.zeros((len(residual), 2))
    jacobian[:count] = innovation
    jacobian[count:count + width] = coefficients
    jacobian[-count:] = (-0.5 * (calculation["elevation"][keep] < 0)[:, None]
                         * full[keep, 1])
    return jacobian


def eligible(problem):
    return (
        type(problem) in (NormalPosition, PositionNormal)
        and "calculate" not in vars(problem)
        and not getattr(problem, "scale_labels", ())
        and problem.keep.sum() >= MIN_ACTIVE_ROWS
    )


def optimizer(enabled, stats, residual, initial, lower, upper, *, iterations=24, step=1e-3):
    """Supply a surrogate for the first two derivative probes of the stock secant."""
    started = process_time()
    problem = getattr(residual, "__self__", None)
    qualifies = eligible(problem)
    counts = stats.setdefault("eligible" if qualifies else "ordinary", dict(
        fits=0, exact_calls=0, approximate_calls=0, fallbacks=0, cpu_s=0,
        rows=0, nodes=0, jacobian_cpu_s=0,
    ))
    counts["fits"] += 1
    try:
        if enabled and qualifies:
            result = proposed_fit(
                problem, counts, residual, initial, lower, upper, iterations, step
            )
            if result is not None:
                return result
        result = bounded_secant(residual, initial, lower, upper, iterations=iterations, step=step)
        counts["exact_calls"] += result["evaluations"]
        return result
    finally:
        counts["cpu_s"] += process_time() - started


def proposed_fit(problem, counts, residual, initial, lower, upper, iterations, step):
    layout = layout_for(problem)
    if len(layout.nodes) > MAX_NODE_FRACTION * layout.length:
        return None
    counts["rows"] += layout.length
    counts["nodes"] += len(layout.nodes)
    anchor = np.clip(initial, lower, upper)
    calculation = problem.calculate(anchor)
    elevation = np.maximum(0, -calculation["elevation"][problem.keep]) / 2
    original = np.r_[calculation["residual"], elevation]
    counts["exact_calls"] += 1
    nearby = list(_forward_points(anchor, lower, upper, step))
    started = process_time()
    jacobian = proposal_jacobian(problem, calculation, original, layout, anchor, nearby)
    counts["jacobian_cpu_s"] += process_time() - started
    pending = [(point, original + jacobian[:, axis] * delta)
               for axis, point, delta in nearby]
    initial_call = True

    def exact(point):
        if np.array_equal(point, anchor):
            return original
        counts["exact_calls"] += 1
        return residual(point)

    def trial(point):
        nonlocal initial_call
        if initial_call:
            initial_call = False
            return exact(point)
        if pending and np.array_equal(pending[0][0], point):
            counts["approximate_calls"] += 1
            return pending.pop(0)[1]
        pending.clear()
        return exact(point)

    result = bounded_secant(trial, initial, lower, upper, iterations=iterations, step=step)
    if len(result["history"]) == 1:
        # Confirm apparent stationarity or failure to find a decrease with the
        # stock exact derivatives at the original coordinate.
        counts["fallbacks"] += 1
        result = bounded_secant(exact, initial, lower, upper, iterations=iterations, step=step)
    return result
