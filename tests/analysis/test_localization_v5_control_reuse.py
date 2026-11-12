import numpy as np
import pytest
from probe_algo07v5_control_census import prospective_key

from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.analysis.localization_v5.control_reuse import CompleteControlCache, control_key
from leo.contracts.digests import canonical_digest


class Bound:
    def __init__(self):
        self.manifest = {'version': 'tiny'}

    def __call__(self):
        raise AssertionError('Synthetic cache tests must not call a numerical backend')


def fixture():
    bound = Bound()
    scan = object.__new__(ScanLikelihood)
    scan.bound = bound
    scan.tracks, scan.white, scan.rx_basis = [[1], [2]], [1, 2], [3, 4]
    scan.geometry = {'position': np.array([1., 2.])}
    scan.previous_shape_cache = {'calibration': [3.]}
    context = dict(scan=scan, node={}, keep=[True], powers=[1.], means=[0.],
                   model={}, entries=[])
    return context, {'policy': {}}, bound


def value():
    return {'c0': {'x': np.array([1.])}, 'fitted_c': {'x': np.array([2.])}}


def test_runtime_key_matches_independently_validated_census():
    context, inventory, bound = fixture()
    binding = canonical_digest(bound.manifest)
    expected = prospective_key('fit_shared', context, inventory, 2, False, bound, binding)
    assert control_key('fit_shared', context, inventory, 2, False, bound, binding) == expected
    for name in ('tracks', 'white', 'rx_basis'):
        getattr(context['scan'], name).append('target only')
    assert control_key('fit_shared', context, inventory, 2, False, bound, binding) == expected
    context['scan'].geometry['position'][0] += 1.
    assert control_key('fit_shared', context, inventory, 2, False, bound, binding) != expected


def test_reuse_keeps_both_arms_isolated_and_counts_only_actual_computations():
    context, inventory, bound = fixture()
    cache = CompleteControlCache(bound, lambda: canonical_digest(bound.manifest))
    calls = []

    def compute():
        calls.append(1)
        return value()

    args = (True, 'fit_shared', context, inventory, 2, False)
    cache.pair(compute, *args)['c0']['x'][0] = 99
    cache.pair(compute, *args)['fitted_c']['x'][0] = 99
    assert cache.pair(compute, *args)['fitted_c']['x'][0] == 2
    assert calls == [1]
    assert cache.counts() == dict(requests=3, computed=1, reused=2, failed=0,
                                 unkeyable=0, in_progress=0)
    assert cache.context(context, 'fit_shared', False) is context
    assert 'geometry' in vars(context['scan'])


@pytest.mark.parametrize('change', ['callback', 'bound', 'numerical', 'factory', 'unknown',
                                   'geometry', 'mutable', 'context', 'inventory'])
def test_unsafe_or_changed_scientific_state_never_reuses_an_old_result(change):
    context, inventory, bound = fixture()
    cache = CompleteControlCache(bound, lambda: canonical_digest(bound.manifest))
    calls = []

    def compute():
        calls.append(1)
        return value()

    args = (True, 'fit_shared', context, inventory, 2, False)
    cache.pair(compute, *args)
    if change == 'callback':
        context['scan'].extra = lambda: None
    elif change == 'bound':
        context['scan'].bound = Bound()
    elif change == 'numerical':
        context['numerical_policy'] = object()
    elif change == 'factory':
        context['problem_factory'] = lambda: None
    elif change == 'unknown':
        context['scan'].extra = object()
    elif change == 'geometry':
        context['scan'].geometry['position'][0] += 1
    elif change == 'mutable':
        context['scan'].previous_shape_cache['calibration'][0] += 1
    elif change == 'context':
        context['powers'][0] += 1
    else:
        inventory['policy']['changed'] = True
    cache.pair(compute, *args)
    assert calls == [1, 1]
    assert cache.counts()['reused'] == 0


def test_noncontrols_and_unrecognized_kinds_are_never_cached():
    context, inventory, bound = fixture()
    cache = CompleteControlCache(bound, lambda: canonical_digest(bound.manifest))
    arbitrary = object()
    assert (cache.pair(lambda: arbitrary, False, 'fit_new', context, inventory, 2, 'lbfgsb')
            is arbitrary)
    assert cache.counts()['requests'] == 0
    for kind, option in (('other', False), ('fit_shared', True), ('fit_new', 'other')):
        assert control_key(kind, context, inventory, 2, option, bound, 'identity') is None


def test_changed_identity_and_incomplete_pairs_fail_without_poisoning_cache():
    context, inventory, bound = fixture()
    cache = CompleteControlCache(bound, lambda: canonical_digest(bound.manifest))
    args = (True, 'fit_shared', context, inventory, 2, False)
    with pytest.raises(RuntimeError, match='Complete matched'):
        cache.pair(lambda: {'c0': {}}, *args)
    assert cache.pair(value, *args) == value()
    bound.manifest['changed'] = True
    with pytest.raises(RuntimeError, match='identity changed'):
        cache.pair(value, *args)
    assert cache.counts() == dict(requests=3, computed=1, reused=0, failed=2,
                                 unkeyable=0, in_progress=0)


def test_failed_computations_are_counted_and_do_not_create_hits():
    context, inventory, bound = fixture()
    cache = CompleteControlCache(bound, lambda: canonical_digest(bound.manifest))
    args = (True, 'fit_shared', context, inventory, 2, False)

    def fails():
        assert cache.counts()['in_progress'] == 1
        raise ArithmeticError('tiny failure')

    with pytest.raises(ArithmeticError):
        cache.pair(fails, *args)
    cache.pair(value, *args)
    policy = cache.policy
    policy['normalized_lists'].clear()
    assert cache.policy['normalized_lists'] == ['tracks', 'white', 'rx_basis']
    assert cache.counts()['failed'] == cache.counts()['computed'] == 1
    assert cache.counts()['reused'] == cache.counts()['in_progress'] == 0
