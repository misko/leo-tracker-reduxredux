"""External exactness experiment: omit the identity-lower solve for the upper root."""

import inspect

import algo07v3_prescratch_hierarchical_oracle as reference
import numpy as np
from scipy.linalg.lapack import dtrtrs


def solve_upper(root, rhs):
    result, info = dtrtrs(root, rhs)
    if info:
        raise np.linalg.LinAlgError(f'DTRTRS failed: {info}')
    return result


def candidate_function():
    source = inspect.getsource(reference.hierarchical_bound)
    before = '_solve_factor(root.T, np.arange(width, dtype=np.int32),'
    if source.count(before) != 1:
        raise ValueError('Review changed posterior source before probing')
    code = source.replace(before, 'solve_upper(root.T,')
    scope = dict(vars(reference), solve_upper=solve_upper)
    exec(compile(code, '<upper-triangular-solve>', 'exec'), scope)
    return scope['hierarchical_bound'], source, code
