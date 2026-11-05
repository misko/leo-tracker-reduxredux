from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import family_cavity as cavity


def test_complete_family_exchange_uses_original_identities_and_keeps_inputs():
    node = dict(seed=dict(rows=[dict(component='a', candidate_index=0),
                               dict(component='b', candidate_index=1)]), aliases=np.array([0, 0]))
    entries = [dict(component='a-linear', candidate_index=0),
               dict(component='b-linear', candidate_index=1)]
    d = dict(node=node, entries=entries, scan=SimpleNamespace(norads=np.array([100, 200])),
             all_means=np.array([1., 2.]))
    offers = [(dict(original_index=j, members=[dict(component=k), dict(component=k+'-linear')]),
               dict(candidate_index=1-j, aliases=[j+1, j+2])) for j,k in enumerate(('a', 'b'))]
    new, linear, means = cavity.configuration(d, offers)
    assert [r['candidate_index'] for r in new['seed']['rows']] == [1, 0]
    assert [e['candidate_index'] for e in linear] == [1, 0]
    np.testing.assert_array_equal(new['aliases'], [1, 2])
    np.testing.assert_array_equal(means, [1., 2.])
    assert [r['candidate_index'] for r in node['seed']['rows']] == [0, 1]
    assert [e['candidate_index'] for e in entries] == [0, 1]
    with pytest.raises(ValueError, match='only once'):
        cavity.configuration(d, [offers[0], offers[0]])


def test_equal_assignment_adoption_uses_valid_c0_loss_and_retains_sticky_control():
    def trial(loss, valid=True):
        return dict(paired_valid=valid, arms=dict(c0=dict(corrected_selection_loss=loss)))
    base = dict(status='complete', accepted=False, policy_arms={'original': True},
        baseline_arms={'original': True}, baseline_corrected_loss={'c0': 10.},
        trials=[trial(1., False), trial(9.), trial(9.5)])
    result = cavity.adopt_equal_assignment_prior(base)
    assert result['accepted'] and not result['sticky_control_accepted']
    assert result['selected'] is base['trials'][1]
    assert base['accepted'] is False and 'selected' not in base
    tied = deepcopy(base)
    tied['trials'] = [trial(10.)]
    assert cavity.adopt_equal_assignment_prior(tied)['selected'] is None
    assert cavity.adopt_equal_assignment_prior(result) is result


def test_cavity_acceptance_requires_both_arm_gates_and_all_satellite_phase_bounds():
    pair = {a: dict(gates=dict(tracks=[dict(compatible=True)]), linear_gates=[],
                   endpoint_east_north_km=np.zeros(2), final_phase_change_s=0.,
                   state=dict(phases=np.array([0., 15.]))) for a in ('c0', 'fitted_c')}
    assert cavity.valid(pair)
    pair['fitted_c']['state']['phases'][1] = 15.01
    assert not cavity.valid(pair)
    pair['fitted_c']['state']['phases'][1] = 15.
    pair['c0']['gates']['tracks'][0]['compatible'] = False
    assert not cavity.valid(pair)


def test_cavity_calibration_excludes_every_active_point_from_held_family(monkeypatch):
    tracks = [dict(times=np.arange(4.), values=np.arange(4.)+j, receiver=1,
                   channel=j+1, key=str(j), observation_ids=[f'{j}-{k}' for k in range(4)])
              for j in range(2)]
    rows = [dict(candidate_index=j) for j in range(2)]
    slices = [slice(0, 4), slice(4, 8)]
    keep = np.array([1, 0, 1, 1, 1, 1, 1, 1], bool)
    scan = SimpleNamespace(tracks=tracks)
    made = []
    def make(scan, node, mask, arm, reference, powers, means, model, events):
        made.append(mask.copy())
        return SimpleNamespace(scan=scan, members=[0, 1], slices=slices, labels=[0, 1],
            q=np.ones(8), hardware=np.ones((8, 1)), smooth=np.zeros((8, 0)),
            noise_groups=np.repeat([0, 1], 4), point_noise=np.ones(8),
            state=lambda x: dict(phases=np.zeros(2)),
            calculate=lambda x: dict(features=np.column_stack((np.ones(8), np.arange(8.))),
                coefficient=np.zeros(2), noise_precision=np.ones(2),
                coefficient_prior_precision=np.ones(2)))
    monkeypatch.setattr(cavity, 'make_event_problem', make)
    d = dict(base=SimpleNamespace(rows=rows, members=[0, 1], slices=slices), keep=keep,
             reference=np.zeros(2), scan=scan, node={}, powers=np.ones(2), means=np.zeros(2),
             model={}, x=np.zeros(2), entries=[])
    result = cavity.family_data(d, 0)
    assert result['held_ids'] == ['0-0', '0-2', '0-3']
    assert all(not mask[:4].any() and mask[4:].all() for mask in made)
    np.testing.assert_array_equal(keep, [1, 0, 1, 1, 1, 1, 1, 1])
    assert np.linalg.eigvalsh(result['base_covariance']).min() > 0


def test_failed_nomination_is_not_used_for_position_trials():
    failed = dict(status='failed', error='insufficient calibration')
    assert cavity.cavity_policy({}, failed) is failed


def test_unused_phase_correction_does_not_discount_predictive_only_families():
    p = SimpleNamespace(labels=[0, 1, 2], rows=[dict(candidate_index=0), dict(candidate_index=1)],
                        slices=[slice(0, 1), slice(1, 2)], keep=np.array([True, False]))
    assert cavity.unused_count(p, []) == 2
    assert cavity.unused_count(p, [dict(candidate_index=2)]) == 1


@pytest.mark.parametrize('slack,expected_refinement', [(-.25, True), (-.251, False)])
def test_refinement_only_for_near_feasible_pairs(monkeypatch, slack, expected_refinement):
    keep = np.array([True])
    d = dict(scan=SimpleNamespace(search_region=SimpleNamespace(half_width_km=12.5)),
             keep=keep, powers=np.ones(1), model=dict(nu=4.))
    def record(compatible):
        return dict(gates=dict(tracks=[dict(compatible=compatible)]), linear_gates=[],
            final_phase_change_s=0., endpoint_east_north_km=np.zeros(2),
            phase_reference=np.zeros(1), state=dict(phases=np.zeros(1)), negative_twice_elbo=10.)
    monkeypatch.setattr(cavity, 'refit', lambda *a: record(False))
    p = SimpleNamespace(labels=[0], rows=[dict(candidate_index=0)], slices=[slice(0, 1)],
        keep=keep, calculate=lambda x: dict(coefficient=np.zeros(1)))
    monkeypatch.setattr(cavity, 'make_event_problem', lambda *a: p)
    monkeypatch.setattr(cavity, 'attach_event_predictive', lambda *a: None)
    monkeypatch.setattr(cavity, 'gate_slacks', lambda *a: dict(minimum=slack))
    calls = []
    def refine(scan, node, mask, powers, means, model, entries, pair):
        assert mask is keep
        calls.append(True)
        return {a: record(True) for a in ('c0', 'fitted_c')}
    monkeypatch.setattr(cavity, 'constrained', refine)
    result = cavity.fit_configuration(d, {}, [], np.zeros(1))
    assert bool(calls) == expected_refinement
    assert result['paired_valid'] == expected_refinement
    assert result['constrained_refinement_attempted'] == expected_refinement
    assert all(r['corrected_selection_loss'] == 10. for r in result['arms'].values())
