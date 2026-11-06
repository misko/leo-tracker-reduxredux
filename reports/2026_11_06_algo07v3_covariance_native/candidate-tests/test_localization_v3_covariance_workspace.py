"""Private covariance storage preserves the complete original likelihood."""

import ast
import hashlib
import inspect
from pathlib import Path

import algo07v3_precovariance_hierarchical_oracle as original
import numpy as np
import pytest
from probe_algo07v3_covariance import candidate

from leo.analysis.localization_v3 import hierarchical


def test_owned_implementation_matches_previously_measured_prototype():
    assert hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest() == (
        'c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e')
    _, _, expected = candidate('workspace')
    assert ast.dump(ast.parse(inspect.getsource(hierarchical.hierarchical_bound))) == (
        ast.dump(ast.parse(expected)))


@pytest.mark.parametrize('width', [0, 1, 17, 176])
def test_reused_covariance_is_private_per_likelihood_and_exact(monkeypatch, width):
    rng = np.random.default_rng(115)
    args = (rng.normal(size=72), rng.normal(size=(72, width)),
            rng.uniform(1, 3, size=72), np.arange(72) % 6)
    kwargs = dict(prior_groups=np.arange(width) % 4, iterations=12)
    before = [a.copy() for a in args]
    expected = original.hierarchical_bound(*args, **kwargs)
    buffers = []
    multiply = np.matmul

    def observed(a, b, *, out):
        buffers.append(out)
        return multiply(a, b, out=out)

    monkeypatch.setattr(hierarchical.np, 'matmul', observed)
    first = hierarchical.hierarchical_bound(*args, **kwargs)
    count = len(buffers)
    second = hierarchical.hierarchical_bound(*args, **kwargs)
    assert count == expected['precision_iterations']
    assert len(buffers) == 2 * count
    assert all(v is buffers[0] for v in buffers[:count])
    assert all(v is buffers[count] for v in buffers[count:])
    assert buffers[0] is not buffers[count]
    for result in (first, second):
        assert result.keys() == expected.keys()
        for name in result:
            np.testing.assert_array_equal(result[name], expected[name])
    for value, snapshot in zip(args, before, strict=True):
        np.testing.assert_array_equal(value, snapshot)
