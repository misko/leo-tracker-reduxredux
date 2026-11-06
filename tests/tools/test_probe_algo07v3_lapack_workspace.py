import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_inverse_layout import layout_candidate
from probe_algo07v3_lapack_workspace import candidate as workspace_candidate
from probe_algo07v3_lapack_workspace import reference


def candidate(variant):
    return layout_candidate() if variant == 'fortran' else workspace_candidate(variant)


@pytest.mark.parametrize('variant', ['lu', 'inverse', 'both', 'fortran'])
@pytest.mark.parametrize('width', [0, 1, 9, 32, 175])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('learned', [False, True])
def test_complete_likelihood_and_input_bytes_survive_buffer_reuse(variant, width, layout, learned):
    rng = np.random.default_rng(20261106 + width)
    features = rng.normal(size=(96, width))
    features[rng.random(features.shape) < .7] = 0
    features = np.array(features, order=layout)
    raw, sigma = rng.normal(size=96)*150, rng.uniform(60, 200, size=96)
    groups = np.arange(96) % 6
    prior = np.arange(width) % 4 if learned else None
    if learned:
        prior[::3] = -1
    kwargs = dict(prior_groups=prior, powers=rng.uniform(.5, 1, 6), iterations=16)
    before = fingerprint((raw, features, sigma, groups, kwargs))
    operation, _, _ = candidate(variant)
    expected = reference.hierarchical_bound(raw, features, sigma, groups, **kwargs)
    assert fingerprint(operation(raw, features, sigma, groups, **kwargs)) == fingerprint(expected)
    # A second call with different values must not retain scratch state.
    other = raw[::-1]
    assert fingerprint(operation(other, features, sigma, groups, **kwargs)) == fingerprint(
        reference.hierarchical_bound(other, features, sigma, groups, **kwargs))
    assert before == fingerprint((raw, features, sigma, groups, kwargs))


@pytest.mark.parametrize('variant', ['lu', 'inverse', 'both', 'fortran'])
@pytest.mark.parametrize('value', [0., -0., 1e-200])
def test_degenerate_and_signed_zero_cases(variant, value):
    operation, _, _ = candidate(variant)
    args = (np.full(30, value), np.zeros((30, 5)), 150., np.arange(30) % 3)
    assert fingerprint(operation(*args)) == fingerprint(reference.hierarchical_bound(*args))


@pytest.mark.parametrize('variant,name', [('lu', 'dgetrf'), ('inverse', 'dgetrs')])
def test_buffered_lapack_failure_propagates(variant, name):
    operation, _, _ = candidate(variant)
    operation.__globals__[name] = lambda *a, **k: ((None, None, -1) if name == 'dgetrf'
                                                  else (None, -1))
    with pytest.raises(np.linalg.LinAlgError, match=name.upper()):
        operation(np.ones(4), np.ones((4, 1)), 1., np.zeros(4, int))


@pytest.mark.parametrize('variant,name,flag', [('lu', 'dgetrf', 'overwrite_a'),
                                             ('inverse', 'dgetrs', 'overwrite_b')])
def test_lapack_overwrites_private_contiguous_storage(variant, name, flag):
    operation, _, _ = candidate(variant)
    original = operation.__globals__[name]
    pointers = []
    def observed(*args, **kwargs):
        array = args[0] if name == 'dgetrf' else args[2]
        assert array.flags.f_contiguous and kwargs[flag] == 1
        values = original(*args, **kwargs)
        assert np.shares_memory(values[0], array)
        pointers.append(array.ctypes.data)
        return values
    operation.__globals__[name] = observed
    operation(np.arange(30.), np.ones((30, 5)), 1., np.arange(30) % 3, iterations=4)
    assert len(pointers) >= 4 and len(set(pointers)) == 1


@pytest.mark.parametrize('arm', ['c0', 'fitted_c'])
@pytest.mark.parametrize('variant', ['inverse', 'fortran'])
def test_complete_training_history_remains_exact(arm, variant):
    from benchmark_algo07v3_training_kernel import trial

    from tests.analysis.test_localization_v3_training_records import context
    operation, _, _ = candidate(variant)
    first, second = context(4.), context(4.)
    expected = trial(first, first['keep'], arm, reference.hierarchical_bound)
    actual = trial(second, second['keep'], arm, operation)
    assert actual['signature'] == expected['signature']


def test_temporary_kernel_is_restored_on_failure():
    from benchmark_algo07v3_training_kernel import kernel

    from leo.analysis.localization_v3 import event_position, history_position
    originals = event_position.hierarchical_bound, history_position.hierarchical_bound
    with pytest.raises(RuntimeError, match='deliberate interruption'), kernel(object()):
        raise RuntimeError('deliberate interruption')
    assert (event_position.hierarchical_bound, history_position.hierarchical_bound) == originals
