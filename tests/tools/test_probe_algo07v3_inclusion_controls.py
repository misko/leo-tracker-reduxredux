import copy

import pytest
from probe_algo07v3_inclusion_controls import ControlPairs, control_key, transformed
from probe_algo07v3_native_recovery_queue import signature

from leo.analysis.localization_v3 import recovery_inclusion
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.operations.localization_v3_parallel import map_initial_arms
from tests.analysis.test_localization_v3_recovery_execution import fixture


def data():
    scan = object.__new__(ScanLikelihood)
    scan.tracks, scan.white, scan.rx_basis = ['a', 'b'], [1, 2], [3, 4]
    scan.sky = {'orbit': [1., 2.]}
    scan.previous_shape_cache = {'labels': {1, 3}}
    d = dict(scan=scan, node={}, keep=[True], powers=[1.], means=[0.], model={}, entries=[])
    return d, {'policy': {}}, 2


def test_key_covers_original_radio_orbit_and_model_state():
    d, inventory, count = data()
    original = control_key('fit_shared', d, inventory, count, False)
    for field in ('node', 'keep', 'powers', 'means', 'model', 'entries'):
        altered = copy.deepcopy(d)
        if field == 'entries':
            altered[field] = [{'track_index': 0, 'alias': 1}]
        else:
            altered[field] = {'changed': True}
        assert control_key('fit_shared', altered, inventory, count, False) != original
    d['scan'].sky['orbit'][0] += 1
    assert control_key('fit_shared', d, inventory, count, False) != original


def test_append_normalization_and_unsafe_paths():
    d, inventory, count = data()
    original = control_key('fit_shared', d, inventory, count, False)
    for attr in ('tracks', 'white', 'rx_basis'):
        getattr(d['scan'], attr).append('target only')
    assert control_key('fit_shared', d, inventory, count, False) == original
    assert control_key('fit_shared', d, inventory, count, True) is None
    d['numerical_policy'] = object()
    assert control_key('fit_shared', d, inventory, count, False) is None
    del d['numerical_policy']
    d['scan'].unexpected_callback = lambda: None
    assert control_key('fit_shared', d, inventory, count, False) is None


def test_cached_values_are_copied_and_census_recomputes():
    calls = []
    def calculate():
        calls.append(1)
        return {'c0': [1.], 'fitted_c': [2.]}
    pairs = ControlPairs(True, key=lambda *args: 'same')
    args = (True, 'fit_shared', None, None, 1, False)
    first = pairs(calculate, *args)
    first['c0'][0] = 99.
    assert pairs(calculate, *args)['c0'] == [1.]
    assert len(calls) == 1 and pairs.rows[-1]['reused']
    census = ControlPairs(False, key=lambda *args: 'same')
    census(calculate, *args)
    census(calculate, *args)
    assert len(calls) == 3 and census.rows[-1]['duplicate']
    with pytest.raises(ValueError, match='different complete outputs'):
        census(lambda: {'changed': True}, *args)


@pytest.mark.parametrize('kind,options', [
    ('fit_shared', {}), ('fit_new', {}), ('fit_new', {'optimizer': 'powell'}),
])
@pytest.mark.parametrize('mapper', [None, map_initial_arms])
def test_transformed_full_trials_preserve_both_arms(monkeypatch, kind, options, mapper):
    args = fixture(monkeypatch)
    expected = getattr(recovery_inclusion, kind)(*args, map_arms=mapper, **options)
    pairs = ControlPairs(True, key=lambda kind, d, inv, count, option: (kind, option))
    candidate, original_pair = transformed(kind, pairs)
    assert 'map_calibration_arms' in original_pair
    assert signature(candidate(*args, map_arms=mapper, **options)) == signature(expected)
    assert signature(candidate(*args, map_arms=mapper, **options)) == signature(expected)
    assert len(pairs.rows) == 2 and pairs.rows[-1]['reused']
