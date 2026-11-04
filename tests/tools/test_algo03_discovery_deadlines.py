"""Actual recovery control flow with a logical clock and stubbed child science.

These are cancellation/fallback policy tests, not numerical equivalence tests.
The worker source is unchanged. Each stubbed successful inclusion supplies the
same two-arm candidate so that timing is the only variable in these tests.
"""

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import algo03_shadow_worker as worker
import pytest


def recovery(tmp_path, monkeypatch, *, boundary, inventory_seconds=1., fail_annotation=False,
             maximum_seconds=1169, controlled=None):
    clock = SimpleNamespace(now=0.)
    monkeypatch.setattr(worker, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    baseline = dict(state='complete', marker='unchanged incumbent')
    worker.write(tmp_path / 'snapshot/descriptor.json', dict(
        terminal=baseline, root=str(tmp_path), files={}, job_id='fixture', session_id='fixture'))
    tracks = [dict(arm=arm, track_id=tid, current_large=True,
                   observation_ids=ids, all_track_observation_ids=ids)
              for arm in worker.ARMS for tid, ids in [('first', ['a', 'b', 'c']),
                                                      ('second', ['d', 'e'])]]
    support = {arm: dict(owners=dict(old=1)) for arm in worker.ARMS}
    candidate = dict(kind='shared_family', targets=[dict(norad=2)],
                     arms={arm: dict(owners=dict(old=1, a=2, b=2, c=2), added_points=3)
                           for arm in worker.ARMS})
    # The target ordering, admission checks, stage exception handling and final
    # selection are the real worker. Numerical child outputs are explicit stubs.
    monkeypatch.setattr(worker, 'single_candidate', lambda *_: copy.deepcopy(candidate))
    monkeypatch.setitem(sys.modules, 'annotation_partition_plan', SimpleNamespace(
        require_distinct_annotation=lambda *_: None))
    monkeypatch.setitem(sys.modules, 'leo.analysis.research.grouped_prediction', SimpleNamespace(
        identity_consensus=lambda *_args, **_kwargs:
        dict(status='conditionally_supported_identity', norad=2)))
    monkeypatch.setitem(sys.modules, 'test_predictive_graph_transfer', SimpleNamespace(
        shared_family_route=lambda *_: True))
    launched = []

    def execute(command, *, log, timeout):
        script = Path(command[2]).name
        launched.append(script)
        assert timeout > 0
        if script == 'algo03_inventory.py':
            folder = Path(command[command.index('--output') + 1])
            worker.write(folder / 'inventory.json', dict(tracks=tracks, summary={}))
            worker.write(folder / 'publication_support.json', dict(all_verified=True, arms=support))
            clock.now += inventory_seconds
        elif script == 'annotate_predictive_only.py':
            if fail_annotation:
                raise TimeoutError('injected logical cancellation')
            folder = Path(command[command.index('--output') + 1])
            worker.write(folder / 'result.json', dict(folds=[]))
            worker.write(folder / 'protocol.json', {})
            clock.now += 10.
        elif script == 'include_predictive_annotations.py':
            clock.now += 2.
        elif script == 'audit_shared_predictive_inclusion.py':
            trial = Path(command[command.index('--trial') + 1])
            clock.now = boundary if trial.parent.name == 'first' else clock.now + 2.
        else:
            raise AssertionError('Unexpected child: ' + script)
        return 0

    monkeypatch.setattr(worker, 'execute', execute)
    if controlled is not None:
        from algo03_stage_clock_fixture import run_controlled

        before = worker.time, worker.execute
        result, receipt = run_controlled(worker, tmp_path, maximum_seconds,
                                         controlled['schedule'],
                                         stop_after=controlled.get('stop_after'))
        assert (worker.time, worker.execute) == before
        controlled['receipt'] = receipt
        return result, launched, candidate, baseline
    return worker.run(tmp_path, maximum_seconds), launched, candidate, baseline


def logical_schedule(targets):
    rows = [dict(name='inventory', script='algo03_inventory.py', seconds=1.)]
    for index in range(targets):
        for stage, script, seconds in (
                ('annotation', 'annotate_predictive_only.py', 10.),
                ('inclusion', 'include_predictive_annotations.py', 2.),
                ('audit', 'audit_shared_predictive_inclusion.py', 2.)):
            rows.append(dict(name=f'target-{index}-{stage}', script=script, seconds=seconds))
    return rows


@pytest.mark.parametrize('cancel', [False, True])
def test_controlled_clock_drives_actual_admission_and_retains_qualified_recovery(
        tmp_path, monkeypatch, cancel):
    controlled = dict(schedule=logical_schedule(1 if cancel else 2))
    if cancel:
        controlled['stop_after'] = 'target-0-audit'
    result, launched, candidate, _ = recovery(
        tmp_path, monkeypatch, boundary=10000., controlled=controlled)
    assert result['selected'] == candidate
    assert result['attempts'][0]['status'] == 'RF_qualified'
    assert result['attempts'][1]['status'] == (
        'discovery_budget_exhausted' if cancel else 'RF_qualified')
    assert len(launched) == len(controlled['schedule'])
    receipt = controlled['receipt']
    assert receipt['clock_elapsed_seconds_is_synthetic'] is True
    assert receipt['production_deadline_behavior_qualified'] is False
    assert receipt['synthetic_elapsed_seconds'] == (600.001 if cancel else 29.)
    assert all(r['real_wall_seconds'] >= 0 and r['returncode'] == 0
               for r in receipt['children'])


def test_controlled_clock_cannot_turn_child_failure_into_equivalence(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='declared complete work'):
        recovery(tmp_path, monkeypatch, boundary=0., fail_annotation=True,
                 controlled=dict(schedule=logical_schedule(2)))


def test_controlled_clock_rejects_changed_child_order(tmp_path, monkeypatch):
    schedule = logical_schedule(2)
    schedule[1]['script'] = 'different.py'
    with pytest.raises(ValueError, match='declared complete work'):
        recovery(tmp_path, monkeypatch, boundary=0., controlled=dict(schedule=schedule))


@pytest.mark.parametrize('maximum_seconds,threshold', [(1169, 600.), (200, 140.)])
@pytest.mark.parametrize('delta,admitted', [(-.001, True), (0., True), (.001, False)])
def test_discovery_boundary_preserves_previously_qualified_recovery(
        tmp_path, monkeypatch, maximum_seconds, threshold, delta, admitted):
    result, launched, candidate, baseline = recovery(
        tmp_path, monkeypatch, boundary=threshold + delta, maximum_seconds=maximum_seconds)
    assert result['attempts'][0]['status'] == 'RF_qualified'
    assert result['attempts'][1]['status'] == (
        'RF_qualified' if admitted else 'discovery_budget_exhausted')
    assert launched.count('annotate_predictive_only.py') == (2 if admitted else 1)
    assert result['decision'] == 'ALGO03_single'
    assert result['selected'] == candidate
    assert result['baseline'] == baseline
    assert result['matched_c_arms'] is True
    assert 'failure' not in result
    if admitted:
        assert result['seconds'] > threshold  # Admission is not a completion deadline.


def test_discovery_expired_before_first_target_retains_baseline(tmp_path, monkeypatch):
    result, launched, _, baseline = recovery(
        tmp_path, monkeypatch, boundary=601., inventory_seconds=601.)
    assert launched == ['algo03_inventory.py']
    assert [a['status'] for a in result['attempts']] == ['discovery_budget_exhausted'] * 2
    assert result['decision'] == 'ALGO02_fallback'
    assert result['selected'] is None and result['baseline'] == baseline
    assert 'failure' not in result


def test_annotation_cancellation_is_recorded_and_cannot_publish_candidate(tmp_path, monkeypatch):
    result, _, _, baseline = recovery(tmp_path, monkeypatch, boundary=599., fail_annotation=True)
    assert [a['status'] for a in result['attempts']] == ['annotation_execution_failed'] * 2
    assert result['decision'] == 'ALGO02_fallback'
    assert result['selected'] is None and result['baseline'] == baseline
    annotations = [s for s in result['stages'] if s['name'].endswith('-annotation')]
    assert all(s['status'] == 'failed' and 'TimeoutError' in s['error'] for s in annotations)
