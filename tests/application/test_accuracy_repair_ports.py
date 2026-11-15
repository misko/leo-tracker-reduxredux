"""Experimental selectors remain narrow, timed, and bound to owned evidence."""

from copy import deepcopy
from dataclasses import replace

import pytest

from leo.analysis.localization_v3 import gap_controller as gap
from leo.application import localization_v3 as application
from leo.application import localization_v3_engine as engine
from leo.contracts.localization_v5 import direct_gap_policy
from tests.application.test_localization_v3_engine import fixture as engine_fixture
from tests.analysis.test_localization_v3_direct_gap import case as gap_case


@pytest.mark.parametrize('port,method', [
    ('recovery_target_selector', 'prepare_track_recovery'),
    ('gap_target_filter', 'recover_gap_checkpoint'),
])
@pytest.mark.parametrize('enabled', [False, True])
def test_engine_scopes_experimental_callbacks(monkeypatch, port, method, enabled):
    prepared, region, catalogue, execution, calls, *_ = engine_fixture(monkeypatch)
    callback = object()
    if enabled:
        execution = replace(execution, **{port: callback})
    engine.infer_prepared(prepared, region, catalogue, identities=['scan'],
                          collect_history=object(), execution=execution)
    for name, _, kwargs in calls:
        assert (port in kwargs) is (enabled and name == method)
        if port in kwargs:
            assert kwargs[port] is callback


def recovery_evidence():
    rows = []
    for index in range(11):
        ids = [f'{index}-point-{i}' for i in range(30 - index)]
        rows.extend(dict(track_id=f'track-{index}', arm=arm, track_index=index,
                         observation_ids=list(ids), all_track_observation_ids=list(ids),
                         current_large=True, current=dict(wholly_unassociated=True))
                    for arm in ('c0', 'fitted_c'))
    return dict(inventory=dict(tracks=rows), owners={a: {'old': 1} for a in gap.ARMS},
                selected_targets=[], target_limit=0,
                original_selected_track_ids=[f'track-{i}' for i in range(8)],
                policy_omitted_track_ids=[f'track-{i}' for i in range(8)],
                publication_support={})


def prepare_with_selector(monkeypatch, evidence, selector):
    context = {'radio_context': object()}
    monkeypatch.setattr(application, 'prepare_recovery', lambda *args, **kwargs:
                        (context, evidence))
    result = application.prepare_track_recovery(
        {'tracks': {'observations': []}, 'evaluation_reference': object()},
        {'signed_context': {'scan': object()}}, {'cavity_fit': {'status': 'complete'}},
        identities=['scan'], recovery_target_limit=0, recovery_target_selector=selector)
    return result, context


def test_recovery_selection_uses_canonical_complete_inventory_and_copies_receipt(monkeypatch):
    evidence = recovery_evidence()
    original = deepcopy(evidence)
    receipt = dict(targets=[dict(track_id='track-10', observation_ids=['invented'])],
                   rows=[dict(radio_score=3)])
    seen = []

    def selector(context, supplied):
        seen.append((context, deepcopy(supplied)))
        supplied['inventory']['tracks'].clear()
        supplied['owners']['c0']['new'] = 99
        return receipt

    prepared, context = prepare_with_selector(monkeypatch, evidence, selector)
    result = prepared['inventory']
    target = result['selected_targets'][0]
    assert seen[0] == (context, original)
    assert evidence == original
    assert target == dict(original['inventory']['tracks'][-2], inactive_fragment=False)
    assert result['experimental_selection']['targets'] == [target]
    assert all(key not in result for key in (
        'target_limit', 'original_selected_track_ids', 'policy_omitted_track_ids'))
    receipt['rows'][0]['radio_score'] = 99
    target['observation_ids'].clear()
    assert result['experimental_selection']['rows'] == [dict(radio_score=3)]
    assert result['experimental_selection']['targets'][0]['observation_ids']
    assert evidence == original


@pytest.mark.parametrize('bad', [
    'unknown', 'duplicate', 'too_many', 'partial', 'owned', 'unmatched', 'not_large',
    'other_parent', 'non_dict_receipt', 'non_list_targets',
])
def test_recovery_selector_rejects_noncanonical_or_ineligible_ids(monkeypatch, bad):
    evidence = recovery_evidence()
    chosen = [dict(track_id='track-10')]
    if bad == 'unknown':
        chosen = [dict(track_id='unknown')]
    elif bad == 'duplicate':
        chosen *= 2
    elif bad == 'too_many':
        chosen = [dict(track_id=f'track-{i}') for i in range(3)]
    elif bad == 'partial':
        evidence['inventory']['tracks'][-2]['observation_ids'].pop()
    elif bad == 'owned':
        evidence['owners']['fitted_c'][evidence['inventory']['tracks'][-1]['observation_ids'][0]] = 2
    elif bad == 'unmatched':
        evidence['inventory']['tracks'].pop()
    elif bad == 'not_large':
        evidence['inventory']['tracks'][-1]['current_large'] = False
    elif bad == 'other_parent':
        evidence['inventory']['tracks'][-1]['all_track_observation_ids'].append('other')
    receipt = dict(targets=chosen)
    if bad == 'non_dict_receipt':
        receipt = None
    elif bad == 'non_list_targets':
        receipt = dict(targets=tuple(chosen))
    with pytest.raises(ValueError, match='Experimental recovery'):
        prepare_with_selector(monkeypatch, evidence, lambda context, evidence: receipt)


def test_experimental_targets_reach_numerical_checkpoint_without_old_limit(monkeypatch):
    prepared, _ = prepare_with_selector(monkeypatch, recovery_evidence(),
        lambda context, evidence: dict(targets=[dict(track_id='track-10')]))
    seen = []
    monkeypatch.setattr(application, 'recover_tracks', lambda context, evidence, **kwargs:
                        seen.append(deepcopy(evidence)) or {})
    predictive = application.recover_predictive_checkpoint(prepared,
        run_stage=lambda name, operation: (True, operation()), discovery_allowed=lambda: True,
        clock=lambda: 0., inventory_seconds=12.)
    monkeypatch.setattr(application, 'replay_recovery', lambda context, evidence, *args, **kwargs:
                        seen.append((deepcopy(evidence), kwargs)) or {})
    application.recover_numerical_checkpoint(prepared, predictive,
        run_stage=lambda name, operation: (True, operation()), discovery_allowed=lambda: True,
        clock=lambda: 0., charge_reused=lambda seconds: None)
    assert seen[0] == seen[1][0] == prepared['inventory']
    assert seen[1][0]['selected_targets'][0]['track_id'] == 'track-10'
    assert 'recovery_target_limit' not in predictive
    assert 'completed_target_limit' not in seen[1][1]


def test_gap_callback_is_forwarded_through_both_application_layers(monkeypatch):
    seen = []
    callback = object()
    monkeypatch.setattr(application, 'recover_gaps', lambda *args, **kwargs:
                        seen.append(kwargs) or dict(candidate=None))
    support = {arm: dict(owners={'old': 1}) for arm in gap.ARMS}
    numerical = dict(status='numerical_recovery_evaluated', completed_stages={},
        recovery=dict(candidate=dict(attempts=[]), retained=dict(source_support=support)))
    prepared = dict(recovery_context={}, inventory=dict(inventory={}, publication_support=support))
    application.recover_gap_checkpoint(prepared, numerical, [], run_stage=None, clock=None,
        direct_gap_policy=direct_gap_policy(), gap_target_filter=callback)
    assert seen[0]['gap_target_filter'] is callback


def run_gap(callback, *, direct=True, run_stage=None, clock=lambda: 0., maximum_seconds=1200):
    context, inventory, observations = gap_case()
    owners = {arm: {'old': 10} for arm in gap.ARMS}
    result = gap.recover_gaps(context, inventory, observations, dict(attempts=[]), {}, owners,
        run_stage=run_stage or (lambda name, operation, cap: (True, operation())), clock=clock,
        maximum_seconds=maximum_seconds, gap_target_filter=callback,
        **(dict(direct_gap_policy=direct_gap_policy()) if direct else {}))
    return result, context, inventory, observations, owners


def test_gap_filter_only_runs_for_explicit_direct_policy_and_records_timed_work(monkeypatch):
    ticks = [0.]
    receipt = dict(targets=[], rows=[dict(reason='predictive rejection')])
    supplied = []

    def callback(context, inventory, observations, owners, targets):
        supplied.append(deepcopy((inventory, observations, owners, targets)))
        inventory.clear()
        observations.clear()
        owners.clear()
        targets.clear()
        ticks[0] += 12.
        return receipt

    monkeypatch.setattr(gap, 'prepare_gap', lambda *args: pytest.fail('filtered target prepared'))
    result, context, inventory, observations, owners = run_gap(callback, clock=lambda: ticks[0])
    assert supplied[0][0:3] == (inventory, observations, owners)
    assert supplied[0][-1] == gap.direct_timing_targets(context, inventory, owners)
    assert result['experimental_selection'] == receipt
    assert result['targets'] == result['trials'] == []
    assert result['stages'] == [dict(name='experimental-target-filter', status='complete',
                                    seconds=12., timeout_s=1180)]
    receipt['rows'].clear()
    assert result['experimental_selection']['rows']
    legacy, *_ = run_gap(lambda *args: pytest.fail('legacy filter invoked'), direct=False)
    assert 'experimental_selection' not in legacy and legacy['stages'] == []


@pytest.mark.parametrize('changed', ['altered', 'duplicate', 'reordered', 'extra', 'invalid'])
def test_gap_filter_rejects_changed_or_reordered_subset(monkeypatch, changed):
    targets = [dict(track_id=str(index), branch_id=f'b{index}', points=12) for index in range(3)]
    monkeypatch.setattr(gap, 'direct_timing_targets', lambda *args: deepcopy(targets))
    retained = deepcopy(targets)
    if changed == 'altered':
        retained[0]['points'] = 13
    elif changed == 'duplicate':
        retained.insert(1, deepcopy(retained[0]))
    elif changed == 'reordered':
        retained.reverse()
    elif changed == 'extra':
        retained.append(dict(track_id='new'))
    else:
        retained = None
    with pytest.raises(ValueError, match='Experimental gap filter'):
        run_gap(lambda *args: dict(targets=retained))


@pytest.mark.parametrize('error', [ValueError('invalid predictive state'), TimeoutError('selector timeout')])
def test_gap_filter_failure_propagates_instead_of_successful_incumbent(error):
    def failed(*args):
        raise error

    with pytest.raises(type(error), match=str(error)):
        run_gap(failed)
    with pytest.raises(ValueError, match='did not complete'):
        run_gap(lambda *args: dict(targets=[]), run_stage=lambda *args: (False, None))


def test_gap_filter_work_reduces_remaining_stage_deadline():
    ticks, calls = [0.], []

    def callback(context, inventory, observations, owners, targets):
        ticks[0] += 40.
        return dict(targets=targets)

    def stage(name, operation, cap):
        calls.append((name, cap))
        return (True, operation()) if name == 'experimental-target-filter' else (False, None)

    result, *_ = run_gap(callback, run_stage=stage, clock=lambda: ticks[0], maximum_seconds=100)
    assert calls == [('experimental-target-filter', 80), ('gap-0-prepare', 40)]
    assert result['stages'][0]['seconds'] == 40.
