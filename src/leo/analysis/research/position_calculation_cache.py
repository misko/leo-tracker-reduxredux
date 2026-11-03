"""Bounded reuse of a fixed problem's calculation, with independent results."""

from copy import deepcopy
from functools import lru_cache

import numpy as np


def copying_position_cache(calculate, *, maxsize=1):
    """Cache exact coordinate arrays, never round or share mutable outputs.

    The function belongs to one fixed problem. A different model, mask, phase
    reference or prior needs a new problem/cache, as in the existing builders.
    Callers that explicitly change a problem must clear the cache first.
    """
    if type(maxsize) is not int or maxsize < 1:
        raise ValueError("positive bounded cache size required")

    @lru_cache(maxsize=maxsize)
    def stored(dtype, shape, data):
        position = np.frombuffer(data, dtype=np.dtype(dtype)).reshape(shape).copy()
        return deepcopy(calculate(position))

    def evaluate(position):
        values = np.asarray(position)
        if values.dtype.hasobject:
            # Object arrays cannot be reconstructed from their pointer bytes.
            return calculate(position)
        result = stored(values.dtype.str, values.shape, values.tobytes())
        return deepcopy(result)

    evaluate.cache_clear = stored.cache_clear
    evaluate.cache_info = stored.cache_info
    return evaluate
