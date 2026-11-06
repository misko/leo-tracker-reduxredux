import copy

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import inclusion_controls as controls
from leo.analysis.localization_v3 import recovery_inclusion as inclusion
from leo.analysis.localization_v3.scan import ScanLikelihood
from tests.analysis.test_localization_v3_recovery_execution import fixture


def data():
    scan = object.__new__(ScanLikelihood)
    scan.tracks = [dict(rf_hz=11.5e9, values=np.array([1., 2.]))]
    scan.white, scan.rx_basis = [np.eye(2)], [np.ones((2, 2))]
    scan.sky = {'position_km': np.ones((1, 2, 3))}
    scan.search_center = [1., 2.]
    scan.cache = {('a', 0): {1, 2}}
    d = dict(scan=scan, node={}, keep=np.array([True, True]), powers=np.ones(1),
             means=np.zeros(1), model={'nu': 4}, entries=[])
    return d, dict(policy={'c0': {}, 'fitted_c': {}}), 1


@pytest.mark.parametrize('field', ['node', 'keep', 'powers', 'means', 'model', 'entries'])
def test_key_invalidates_changed_scientific_context(field):
    d, inv, n = data()
    before = controls.control_key('fit_shared', d, inv, n, False)
    if field == 'entries':
        d[field] = [{'track_index': 0, 'alias': 1}]
    else:
        d[field] = {'changed': 1}
    assert controls.control_key('fit_shared', d, inv, n, False) != before


@pytest.mark.parametrize('change', ['rf', 'orbit', 'policy', 'center', 'cache'])
def test_key_invalidates_radio_orbit_prior_and_ownership_changes(change):
    d, inv, n = data()
    before = controls.control_key('fit_shared', d, inv, n, False)
    if change == 'rf':
        d['scan'].tracks[0]['rf_hz'] += 1
    elif change == 'orbit':
        d['scan'].sky['position_km'][0, 0, 0] += 1
    elif change == 'policy':
        inv['policy']['c0']['owners'] = {'point': 1}
    elif change == 'center':
        d['scan'].search_center[0] += 1
    else:
        d['scan'].cache[('a', 0)].add(3)
    assert controls.control_key('fit_shared', d, inv, n, False) != before


def test_only_unused_appended_target_lists_are_normalized():
    d, inv, n = data()
    before = controls.control_key('fit_shared', d, inv, n, False)
    for name in ('tracks', 'white', 'rx_basis'):
        getattr(d['scan'], name).append('unused target')
    assert controls.control_key('fit_shared', d, inv, n, False) == before
    d['entries'] = [{'track_index': 1}]
    assert controls.control_key('fit_shared', d, inv, n, False) is None


def test_custom_or_stateful_behavior_bypasses_cache():
    d, inv, n = data()
    assert controls.control_key('fit_shared', d, inv, n, True) is None
    for key in ('numerical_policy', 'problem_factory'):
        changed = dict(d, **{key: object()})
        assert controls.control_key('fit_new', changed, inv, n, 'lbfgsb') is None
    d['scan'].unexpected = lambda: None
    assert controls.control_key('fit_new', d, inv, n, 'lbfgsb') is None


def test_variants_and_optimizers_do_not_share_keys():
    d, inv, n = data()
    assert len({controls.control_key(kind, d, inv, n, option) for kind, option in (
        ('fit_shared', False), ('fit_new', 'lbfgsb'), ('fit_new', 'powell'))}) == 3


def test_returned_results_do_not_mutate_private_cache_and_failures_are_not_cached():
    d, inv, n = data()
    cache = controls.InclusionControlCache()
    calls = []
    def compute():
        calls.append(1)
        return {'c0': np.ones(2), 'fitted_c': np.zeros(2)}
    args = (True, 'fit_shared', d, inv, n, False)
    first = cache.pair(compute, *args)
    first['c0'][:] = 99
    second = cache.pair(compute, *args)
    assert np.array_equal(second['c0'], np.ones(2)) and len(calls) == 1
    second['c0'][:] = -1
    assert np.array_equal(cache.pair(compute, *args)['c0'], np.ones(2))
    cache.pair(compute, False, *args[1:])
    assert len(calls) == 2
    def failed():
        raise RuntimeError('worker failed')
    with pytest.raises(RuntimeError, match='worker failed'):
        cache.pair(failed, True, 'fit_new', d, inv, n, 'powell')
    assert len(cache._pairs) == 1


@pytest.mark.parametrize('kind,kwargs', [
    ('fit_shared', {}), ('fit_new', {}), ('fit_new', {'optimizer': 'powell'}),
])
def test_complete_cached_control_and_uncached_target_outputs_match(monkeypatch, kind, kwargs):
    args = fixture(monkeypatch)
    expected = getattr(inclusion, kind)(*copy.deepcopy(args), **kwargs)
    monkeypatch.setattr(controls, 'control_key', lambda *args: 'same fixture inputs')
    cache = controls.InclusionControlCache()
    for _ in range(2):
        actual = getattr(inclusion, kind)(*args, control_cache=cache, **kwargs)
        assert fingerprint(actual) == fingerprint(expected)
    assert len(cache._pairs) == 1


def test_control_context_excludes_geometry_without_mutating_source():
    d, inv, n = data()
    d['scan'].geometry = {'discovery': np.ones(20)}
    cache = controls.InclusionControlCache()
    assert controls.control_key('fit_shared', d, inv, n, False) is None
    view = cache.context(d, 'fit_shared', False)
    assert view is not d and view['scan'] is not d['scan']
    assert not hasattr(view['scan'], 'geometry') and hasattr(d['scan'], 'geometry')
    assert controls.control_key('fit_shared', view, inv, n, False) is not None
    for field in ('numerical_policy', 'problem_factory'):
        custom = dict(d, **{field: object()})
        assert cache.context(custom, 'fit_shared', False) is custom
    assert cache.context(d, 'fit_shared', True) is d
    d['scan'].hardware = lambda *args: None
    assert cache.context(d, 'fit_shared', False) is d


@pytest.mark.parametrize('a,b', [({1: 'x'}, {'1': 'x'}), ([1], (1,)),
                                 (0., -0.), (np.ones(2), np.ones(2, dtype='f4'))])
def test_fingerprints_distinguish_typed_state(a, b):
    assert controls._fingerprint(a) != controls._fingerprint(b)


def test_complete_control_uses_view_but_target_keeps_original(monkeypatch):
    d, inv, annotations = fixture(monkeypatch)
    base_problem = inclusion._problem
    scan = object.__new__(ScanLikelihood)
    scan.tracks, scan.white, scan.rx_basis = ['original'], [np.eye(1)], [np.ones((1, 1))]
    scan.geometry = {'discovery only': 1}
    d.update(scan=scan, node={})
    targets = [dict(component='new', candidate_index=1, norad=20,
                    observation_ids=['new'], track_index=0)]
    monkeypatch.setattr(inclusion, '_targets', lambda *args, **kw: (d, targets, [], [], 1))
    seen = []

    def problem(context, arm, reference, entries, **kwargs):
        seen.append((bool(entries), hasattr(context['scan'], 'geometry')))
        return base_problem(context, arm, reference, entries, **kwargs)

    monkeypatch.setattr(inclusion, '_problem', problem)
    cache = controls.InclusionControlCache()
    first = inclusion.fit_shared(d, inv, annotations, control_cache=cache)
    second = inclusion.fit_shared(d, inv, annotations, control_cache=cache)
    assert fingerprint(first) == fingerprint(second)
    assert seen.count((False, False)) == 10
    assert seen.count((True, True)) == 20
    assert len(seen) == 30 and hasattr(scan, 'geometry')
