"""External experiment: precompute flattened covariance gather indices."""

import inspect

import algo07v3_preindex_hierarchical_oracle as hierarchical


def candidate_function():
    source = inspect.getsource(hierarchical.hierarchical_bound)
    before = '''        for group_indices, columns, variance_matrices in variance_blocks:
            products = covariance[columns[:, :, None], columns[:, None, :]] * variance_matrices'''
    setup = '    def posterior(weight, precision, covariance):'
    if source.count(before) != 1 or source.count(setup) != 1:
        raise ValueError('Review changed covariance gathering before probing')
    setup_code = '''    variance_blocks = [
        (group_indices, columns[:, :, None] * width + columns[:, None, :], matrices)
        for group_indices, columns, matrices in variance_blocks
    ]

'''
    replacement = '''        for group_indices, indices, variance_matrices in variance_blocks:
            products = covariance.ravel()[indices] * variance_matrices'''
    code = source.replace(setup, setup_code + setup).replace(before, replacement)
    scope = dict(vars(hierarchical))
    exec(compile(code, '<precomputed-covariance-indices>', 'exec'), scope)
    return scope['hierarchical_bound'], source, code
