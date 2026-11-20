"""Reuse the exact native conditional solve at one fitted v5 model endpoint."""

import struct
import sys
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from functools import partial
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import orbit_projector, v5_lean


def exact_value(value):
    kind = type(value)
    if kind is np.ndarray and not value.dtype.hasobject:
        return kind, value.shape, value.dtype, value.tobytes(order="C")
    if isinstance(value, np.generic) and not value.dtype.hasobject:
        return kind, value.dtype, value.tobytes()
    if kind is float:
        return kind, struct.pack("=d", value)
    if kind in (type(None), int, bool, bytes, str):
        return kind, value
    raise TypeError("The native endpoint cache requires arrays and scalar parameters")


class EndpointReuse:
    """A single endpoint and private result, replaced when the next model is fitted."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.installed = None
        self.previous = None
        self.statistics = {}

    def clear(self):
        if self.installed is not None:
            self.installed.stop()
            self.installed = None
        self.previous = None

    def bind(self, problem, endpoint, stage):
        self.clear()
        original = problem.calculate
        statistics = self.statistics.setdefault(
            stage,
            dict(
                models=0,
                calls=0,
                solves=0,
                hits=0,
                wall_s=0.0,
                cpu_s=0.0,
            ),
        )
        statistics["models"] += 1
        coordinate = exact_value(np.asarray(endpoint))

        def calculate(x):
            try:
                at_endpoint = exact_value(np.asarray(x)) == coordinate
            except TypeError:
                at_endpoint = False
            if not at_endpoint:
                return original(x)
            scan = problem.scan
            operation = scan.bound

            def bound(*args, **kwargs):
                wall, cpu = perf_counter(), process_time()
                statistics["calls"] += 1
                try:
                    return self.bound(statistics, operation, *args, **kwargs)
                finally:
                    statistics["wall_s"] += perf_counter() - wall
                    statistics["cpu_s"] += process_time() - cpu

            with patch.object(scan, "bound", bound):
                return original(x)

        self.installed = patch.object(problem, "calculate", calculate)
        self.installed.start()

    def bound(self, statistics, operation, *args, **kwargs):
        key = None
        if self.enabled:
            try:
                key = (
                    tuple(map(exact_value, args)),
                    tuple((k, exact_value(v)) for k, v in sorted(kwargs.items())),
                )
            except TypeError:
                self.previous = None
        previous = self.previous
        if (
            key is not None
            and previous is not None
            and operation is previous[0]
            and key == previous[1]
        ):
            statistics["hits"] += 1
            return deepcopy(previous[2])
        self.previous = None
        statistics["solves"] += 1
        result = operation(*args, **kwargs)
        if key is not None:
            self.previous = operation, key, deepcopy(result)
        return result


@contextmanager
def endpoint_reuse(*, enabled=True):
    from leo.analysis.localization_v3 import (
        history_position,
        position,
        predictive_linear,
        retained_position,
    )

    endpoint = EndpointReuse(enabled)
    optimize = position.bounded_gauss_newton

    def fit(stage, original, problem, *args, **kwargs):
        endpoint.clear()

        def fit_and_bind(*a, **kw):
            result = optimize(*a, **kw)
            endpoint.bind(problem, result["parameters"], stage)
            return result

        with patch.object(position, "bounded_gauss_newton", fit_and_bind):
            return original(problem, *args, **kwargs)

    with ExitStack() as stack:
        stack.callback(endpoint.clear)
        for name, module in (
            ("conservative", retained_position),
            ("history", history_position),
            ("predictive", predictive_linear),
        ):
            stack.enter_context(patch.object(module, "fit", partial(fit, name, module.fit)))
        yield endpoint.statistics


def worker(request, result, library):
    with endpoint_reuse():
        orbit_projector.worker(request, result, library)


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))
    result["boundary"] = orbit_projector.BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
