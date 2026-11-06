import ctypes

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_native_assembly import build as native_build
from probe_algo07v3_ordered_assembly import build, candidate, reference


@pytest.fixture(scope='module', params=['ctypes', 'native'])
def scatter(tmp_path_factory, request):
    builder = build if request.param == 'ctypes' else native_build
    return builder(tmp_path_factory.mktemp('ordered-scatter'))


@pytest.mark.parametrize('seed', range(15))
def test_ordered_scatter_preserves_duplicates_and_bits(scatter, seed):
    rng = np.random.default_rng(seed)
    output = rng.normal(size=35)
    expected = output.copy()
    indices, groups = rng.integers(0, 35, 1000), rng.integers(0, 9, 1000)
    weights, values = rng.normal(size=9), rng.normal(size=1000)
    np.add.at(expected, indices, weights[groups] * values)
    before = fingerprint((indices, groups, weights, values))
    scatter(output, indices, groups, weights, values)
    assert output.tobytes() == expected.tobytes()
    assert before == fingerprint((indices, groups, weights, values))


@pytest.mark.parametrize('values', [[0., -0., 0.], [1.e300, 1., -1.e300],
                                  [1.e-300, -1.e-300, -0.]])
def test_edge_arithmetic_and_input_order(scatter, values):
    index = np.zeros(3, dtype=np.intp)
    output = np.array([-0.])
    expected = output.copy()
    weights = np.ones(1)
    values = np.array(values)
    np.add.at(expected, index, weights[index] * values)
    scatter(output, index, index, weights, values)
    assert output.tobytes() == expected.tobytes()


def test_empty_input(scatter):
    output, values, indices = np.array([]), np.array([]), np.array([], dtype=np.intp)
    scatter(output, indices, indices, values, values)
    assert output.size == 0


def test_multiply_add_must_not_be_fused(scatter):
    output = np.array([-1.])
    indices = np.array([0], dtype=np.intp)
    scatter(output, indices, indices, np.array([1 + 2.**-27]), np.array([1 - 2.**-27]))
    assert output.tobytes() == np.array([0.]).tobytes()


@pytest.mark.parametrize('bad', ['bounds', 'negative', 'groups', 'length', 'dtype',
                               'strides', 'readonly', 'alias', 'byte_order'])
def test_invalid_inputs_fail_without_mutation(scatter, bad):
    output, weights, values = np.ones(2), np.ones(2), np.ones(2)
    indices, groups = np.arange(2), np.arange(2)
    if bad == 'bounds':
        indices[1] = 2
    elif bad == 'negative':
        indices[1] = -1
    elif bad == 'groups':
        groups[1] = 2
    elif bad == 'length':
        values = values[:1]
    elif bad == 'dtype':
        weights = weights.astype(np.float32)
    elif bad == 'strides':
        output = np.ones(4)[::2]
    elif bad == 'readonly':
        output.setflags(write=False)
    elif bad == 'alias':
        values = output
    elif bad == 'byte_order':
        weights = weights.astype(weights.dtype.newbyteorder('S'))
    before = output.tobytes()
    with pytest.raises((ValueError, ctypes.ArgumentError)):
        scatter(output, indices, groups, weights, values)
    assert output.tobytes() == before


@pytest.mark.parametrize('width', [0, 1, 7, 35])
@pytest.mark.parametrize('seed', range(4))
def test_complete_likelihood_exact(scatter, width, seed):
    rng = np.random.default_rng(seed)
    y = rng.normal(size=80)
    u = rng.normal(size=(80, width))
    u[rng.uniform(size=u.shape) < .6] = 0
    g = np.arange(80) % 5
    prior = np.arange(width) % 3 - 1
    kwargs = dict(prior_groups=prior, powers=.8, iterations=12)
    function, _, _ = candidate(scatter)
    before = fingerprint((y, u, g, kwargs))
    expected = fingerprint(reference.hierarchical_bound(y, u, 1.3, g, **kwargs))
    assert fingerprint(function(y, u, 1.3, g, **kwargs)) == expected
    assert before == fingerprint((y, u, g, kwargs))
