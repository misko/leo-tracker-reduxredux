"""Reuse identical trial evaluations inside one fixed regional optimizer invocation."""
from contextlib import ExitStack, contextmanager
from functools import lru_cache
from unittest.mock import patch

import numpy as np


@contextmanager
def repeated_fit_points(counters):
    from leo.analysis.localization_v3 import history_position, position, retained_position

    original_fit = position.fit

    def fit(problem, *args, **kwargs):
        # Each fit has fixed geometry, phase reference, track mask and calibration.
        # The outer phase-refresh or mask change begins a separate fit.
        calculate, residual = problem.calculate, problem.residual
        previous, result = None, None

        def last(point):
            nonlocal previous, result
            key = np.asarray(point, dtype=np.float64).tobytes()
            if key != previous:
                result = calculate(point)
                previous = key
            else:
                counters["last_result_hits"] += 1
            return result

        @lru_cache(maxsize=16)
        def evaluate(key):
            return residual(np.frombuffer(key, dtype=np.float64))

        with patch.object(problem, "calculate", last), patch.object(
                problem, "residual", lambda x: evaluate(np.asarray(x, dtype=np.float64).tobytes())):
            try:
                return original_fit(problem, *args, **kwargs)
            finally:
                info = evaluate.cache_info()
                counters["fits"] += 1
                counters["residual_hits"] += info.hits
                counters["residual_misses"] += info.misses
                evaluate.cache_clear()

    with ExitStack() as stack:
        for module in (position, retained_position, history_position):
            stack.enter_context(patch.object(module, "fit", fit))
        yield
