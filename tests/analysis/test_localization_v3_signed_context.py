from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.localization_v3 import signed_context as module
from tests.analysis.test_localization_v3_history import history
from tests.analysis.test_localization_v3_position import prepared


def evidence():
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    raw, forecast = history()
    raw['origin_utc_ns'] = scan.origin_utc_ns
    forecast.update(transitions=[], temporal_split_boundary_ns=50,
                    prefix_distribution=dict(shrinkage=0., multiplier=1., nu=None))
    model = dict(shrinkage=0., multiplier=1., nu=None)
    pair = {a: dict(phase_reference=np.zeros(1), endpoint_east_north_km=np.zeros(2),
                   gates=dict(tracks=[dict(compatible=True)]), final_phase_change_s=0.)
            for a in ('c0', 'fitted_c')}
    old = dict(status='accepted', mask=np.ones(41, bool), weights=np.ones(1),
        hyperparameters_from_pre_RF_TLE_only=model, linear_entries=[],
        linear_paired_valid=False, policy_arms=pair)
    return scan, dict(final_node=node), old, raw, forecast


def run(args):
    return module.signed_context(*args, [], case='SCAN', cutoff_utc_ns=90,
                                 history_sha256='bound')


def test_signed_context_rejects_future_transition_even_if_no_signed_model_qualifies():
    args = evidence()
    args[-1]['transitions'] = [dict(validation_time_ns=91)]
    with pytest.raises(ValueError, match='post-scan target'):
        run(args)


def test_unqualified_context_keeps_means_and_normalizes_empty_predictive_without_mutation():
    args = evidence()
    result = run(args)
    assert not result['signed']['accepted'] and result['entries'] == []
    assert result['original_protected'] == {0}
    np.testing.assert_array_equal(result['all_means'], [0.])
    assert result['arms']['c0']['linear_gates'] == []
    assert 'linear_gates' not in args[2]['policy_arms']['c0']


@pytest.mark.parametrize('fail_arm', [None, 'fitted_c'])
def test_signed_change_requires_both_arms_and_updates_all_catalogue_means(monkeypatch, fail_arm):
    args = evidence()
    monkeypatch.setattr(module, 'qualify', lambda *a: dict(
        qualified=True, kind='seconds', coefficient=.4))
    calls = []
    def fit(scan, node, keep, arm, powers, means, model, events, entries):
        calls.append((arm, keep.copy(), means.copy(), events, entries))
        result = deepcopy(args[2]['policy_arms'][arm])
        result['gates']['tracks'][0]['compatible'] = arm != fail_arm
        result['linear_gates'] = []
        return result
    monkeypatch.setattr(module, 'refit', fit)
    result = run(args)
    assert result['signed']['accepted'] == (fail_arm is None)
    assert [r[0] for r in calls] == ['c0', 'fitted_c']
    np.testing.assert_array_equal(calls[0][1], calls[1][1])
    np.testing.assert_array_equal(calls[0][2], calls[1][2])
    np.testing.assert_array_equal(result['means'], [0. if fail_arm else .4])
    np.testing.assert_array_equal(result['all_means'], result['means'])
    assert all(r[3] == r[4] == [] for r in calls)
