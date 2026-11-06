"""Matching endpoints alone must not qualify a repeated solver core."""

from copy import deepcopy

import pytest
from profile_algo07v3_joint_controls import CORE_FIELDS, compare_cores


def stages():
    row = {key: [1., 2.] for key in CORE_FIELDS}
    return {
        'target-1-inclusion': dict(seconds=10., value=dict(
            protocol=dict(optimizer='lbfgsb normalized joint objective'),
            control=dict(arms={'c0': deepcopy(row), 'fitted_c': deepcopy(row)}), new_family={})),
        'control-c0': dict(seconds=2., value=dict(
            protocol=dict(method='control', arm='c0'), result=deepcopy(row))),
    }


def test_full_core_match_is_evidence_not_cache_authorization():
    actual = compare_cores(stages())
    assert actual['pairs'][0]['exact_core']
    assert not actual['sufficient_for_reuse'] and not actual['complete_fit_reused']


@pytest.mark.parametrize('field', ['history', 'phase_reference', 'state'])
def test_same_endpoint_different_trajectory_is_not_a_match(field):
    values = stages()
    values['control-c0']['value']['result'][field] = [1., 3.]
    actual = compare_cores(values)
    assert actual['pairs'][0]['differing_fields'] == [field]
    assert not actual['pairs'][0]['exact_core']


def test_different_optimizer_not_compared():
    values = stages()
    values['control-c0']['value']['protocol']['optimizer'] = 'Powell'
    assert compare_cores(values)['pairs'] == []


def test_missing_fields_are_not_silently_ignored():
    values = stages()
    del values['control-c0']['value']['result']['phase_reference']
    with pytest.raises(ValueError, match='fields missing'):
        compare_cores(values)
