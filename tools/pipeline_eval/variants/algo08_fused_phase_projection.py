"""Share identical LOS work in the curved likelihood's three phase projections."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import marginal
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km


GEOMETRY_SOURCE = "0e067ad8d0d7a69bda355e3c46c409e3ecd3fc469447a80aabb21f7bfaeb4a63"


def nominal_frequency(line, distance, velocity):
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(distance > 0., np.einsum("...i,...i->...", line, velocity) / distance, 0.)
    return -11.5e9 * rate / 299792.458


def fused_projection(center, shifts, latitude, longitude):
    observer = geodetic_to_ecef_km(latitude, longitude, 0.)
    line = center.position_km - observer
    distance = np.linalg.norm(line, axis=-1)
    velocity = center.velocity_km_s
    frequency = nominal_frequency(line, distance, velocity)

    east, north, up = (line @ ecef_to_enu_matrix(latitude, longitude).T).T
    elevation = np.rad2deg(np.arctan2(up, np.hypot(east, north)))

    # Keep the separate mode-rate reduction and scale, including their
    # original floating-point operation order.
    direction = line / distance[:, None]
    rate = np.sum(direction * velocity, axis=1)
    gradient = (velocity - rate[:, None] * direction) / distance[:, None]
    derivative = (np.einsum("nd,nkd->nk", gradient, center.mode_position_km)
                  + np.einsum("nd,nkd->nk", direction, center.mode_velocity_km_s))
    modes = -11.5e9 / 299792.458 * derivative

    def shifted_frequency(state):
        position, velocity = state
        line = position - observer
        return nominal_frequency(line, np.linalg.norm(line, axis=-1), velocity)

    plus, minus = map(shifted_frequency, shifts)
    return frequency, elevation, (plus - minus) / (2 * 0.01), modes


def fused_geometry(original):
    source = getsource(original)
    if sha256(source.encode()).hexdigest() != GEOMETRY_SOURCE:
        raise ValueError("Expected the reviewed curved phase geometry implementation")
    # Retain the entire cache key, state interpolation and region conversion.
    tail = source.index("    frequency, elevation, modes = cached[2].evaluate")
    source = source[:tail] + "    return fused_projection(cached[2], cached[3], *coordinates)\n"
    namespace = dict(vars(marginal), fused_projection=fused_projection)
    exec(compile(source, original.__code__.co_filename, "exec"), namespace)
    return namespace[original.__name__]


@contextmanager
def measured_phase_projection(*, enabled, stage):
    original = marginal._phase_geometry
    operation = fused_geometry(original) if enabled else original
    timings = Counter()

    def evaluate(problem, coordinates):
        label = stage()
        timings[f"{label}_calls"] += 1
        timings[f"{label}_rows"] += len(problem.flat_times)
        start = process_time_ns()
        try:
            return operation(problem, coordinates)
        finally:
            timings[f"{label}_cpu_ns"] += process_time_ns() - start

    with patch.object(marginal, "_phase_geometry", evaluate):
        yield timings
