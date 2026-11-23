"""Use the reduced predictive factor only during standard grid evaluation."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from grid_predictive_reduction import reduced_predictive


HANDOFF_SHA256 = "aa5d7ab17ce82e4bd64e463de0fddf710275634cf48675cf6076eeba6c184831"


@contextmanager
def reduced_grid():
    from leo.presentation import localization_v3 as presentation
    from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

    counts = Counter()
    if sha256(Path(handoff.__file__).read_bytes()).hexdigest() != HANDOFF_SHA256:
        counts["unsupported_binding"] += 1
        yield counts
        return
    stock = handoff.predictive_factor
    sample = presentation.sample_position_grid

    def candidate(*args):
        try:
            start = process_time_ns()
            reduced, sizes = reduced_predictive(*args, include_residual=True)
        except (ValueError, ArithmeticError, np.linalg.LinAlgError):
            counts["original_fallback_calls"] += 1
            return stock(*args)
        counts["reduced_cpu_ns"] += process_time_ns() - start
        counts["reduced_calls"] += 1
        counts["omitted_zero_columns"] += sizes["prefix"]
        counts["collapsed_biases"] += sizes["biases"]
        return reduced

    def grid(*args, **kwargs):
        counts["grid_calls"] += 1
        with patch.object(handoff, "predictive_factor", candidate):
            return sample(*args, **kwargs)

    with patch.object(presentation, "sample_position_grid", grid):
        yield counts
