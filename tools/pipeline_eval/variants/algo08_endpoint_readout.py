"""Reuse the complete selected endpoint calculation during fixed-model readout."""

from contextlib import contextmanager
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.retained_position import PositionNormal

CONTEXT_ARRAYS = (
    "reference", "phase_sigma", "keep", "point_noise", "values", "q", "flat_times",
    "flat_labels", "hardware", "smooth", "constants", "noise_groups", "scale_reference",
)
CONTEXT_BANKS = ("sky", "mode_bank")
BANK_ARRAYS = ("time_s", "position_km", "velocity_km_s")
MISSING = object()


def fixed_context(problem):
    arrays = [np.asarray(getattr(problem, name, ())) for name in CONTEXT_ARRAYS]
    arrays.extend(np.asarray(getattr(problem, bank, {}).get(name, ()))
                  for bank in CONTEXT_BANKS for name in BANK_ARRAYS)
    if any(array.dtype.hasobject or not (array.flags.c_contiguous or array.flags.f_contiguous)
           for array in arrays):
        return None
    layout = tuple((array.shape, array.strides, array.dtype.str) for array in arrays)
    science = tuple(tuple(getattr(problem, name, ()))
                    for name in ("labels", "supported", "supported_local", "scale_labels"))
    options = tuple(getattr(problem, name, None)
                    for name in ("fitted_c", "sigma", "variant", "noise_volume"))
    scan = getattr(problem, "scan", None)
    ports = tuple(id(getattr(scan, name, None)) for name in ("bound", "search_region"))
    raw = tuple(array.ravel(order="K").view(np.uint8) for array in arrays)
    return (layout, science, options, ports), raw


def readout(problem, point, counts, *, reuse):
    """Memoize one selected point after the optimizer has returned."""
    instance_value = vars(problem).get("calculate", MISSING)
    original = problem.calculate
    selected = np.asarray(point, dtype=np.float64).tobytes()
    identity, snapshot, saved = None, None, None

    def calculate(point):
        nonlocal identity, snapshot, saved
        key = np.asarray(point, dtype=np.float64).tobytes()
        if key != selected:
            counts["other_coordinate_calls"] += 1
            return original(point)
        current = fixed_context(problem)
        if current is None:
            counts["unsupported_context_calls"] += 1
            return original(point)
        metadata, raw = current
        matched = metadata == identity and all(np.array_equal(a, b) for a, b in
                                               zip(raw, snapshot, strict=True))
        if matched:
            counts["repeated_endpoint_calls"] += 1
            if reuse:
                return saved
        elif identity is not None:
            counts["context_rebuilds"] += 1
        start = process_time()
        result = original(point)
        counts["endpoint_cpu_s"] += process_time() - start
        counts["endpoint_calculations"] += 1
        if not matched:
            identity, snapshot = metadata, tuple(array.copy() for array in raw)
        if reuse:
            saved = result
        return result

    problem.calculate = calculate

    def restore():
        if vars(problem).get("calculate") is calculate:
            if instance_value is MISSING:
                del problem.calculate
            else:
                problem.calculate = instance_value

    return restore


def eligible(problem):
    if (
        type(problem) not in (NormalPosition, PositionNormal)
        or "calculate" in vars(problem)
        or hasattr(problem, "events")
        or getattr(problem, "scale_labels", ())
    ):
        return False
    operation = problem.calculate
    return getattr(operation, "__func__", None) in (NormalPosition.calculate, PositionNormal.calculate)


@contextmanager
def measured_readout(port, *, reuse):
    original = port.bounded_secant
    counts = dict(models=0, endpoint_calculations=0, repeated_endpoint_calls=0,
                  other_coordinate_calls=0, context_rebuilds=0, unsupported_context_calls=0,
                  endpoint_cpu_s=0.0)
    release = None

    def solve(residual, *args, **kwargs):
        nonlocal release
        if release is not None:
            release()
            release = None
        result = original(residual, *args, **kwargs)
        problem = getattr(residual, "__self__", None)
        if eligible(problem):
            release = readout(problem, result["parameters"], counts, reuse=reuse)
            counts["models"] += 1
        return result

    try:
        with patch.object(port, "bounded_secant", solve):
            yield counts
    finally:
        if release is not None:
            release()
