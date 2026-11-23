"""Use the exact quadratic slope gate without a second differentiation or root search."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np


POLYNOMIAL_PIN = "933b83ce5e414a8441c62d17f8e5eb75e07b79cada283bf681193f7316346922"


def endpoint_test(piece, t, cfg):
    """Match the binary64 derivative and endpoint operations in the released gate."""
    coeff = piece["coefficients_hz"]
    support = t[piece["indices"]]
    endpoints = (np.array([support.min(), support.max()]) - piece["reference_time_s"]) / piece["time_scale_s"]
    intercept = coeff[1] if len(coeff) >= 2 else 0.
    linear = 3 * coeff[2] if len(coeff) == 3 else 0.
    slope = (intercept + linear * endpoints) / piece["time_scale_s"]
    return bool(np.max(np.abs(slope)) <= cfg.max_slope_hz_s)


@contextmanager
def endpoint_slope():
    from leo.analysis import polynomial_tracklets as poly

    original = poly._bounded_slope
    counts = Counter()
    if sha256(Path(poly.__file__).read_bytes()).hexdigest() != POLYNOMIAL_PIN:
        counts["unsupported_module"] += 1
        yield counts
        return

    def bounded(piece, t, cfg):
        coeff = piece["coefficients_hz"]
        if type(coeff) is np.ndarray and coeff.dtype == np.float64 and coeff.ndim == 1 and 1 <= len(coeff) <= 3:
            counts["endpoint_checks"] += 1
            return endpoint_test(piece, t, cfg)
        counts["original_checks"] += 1
        return original(piece, t, cfg)

    with patch.object(poly, "_bounded_slope", bounded):
        yield counts
