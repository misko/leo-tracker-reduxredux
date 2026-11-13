from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import probe_weak_track_validation as probe
import pytest


def track(key, duration, count):
    return dict(key=key, times=np.linspace(0, duration, count),
                observation_ids=[f'{key}-{i}' for i in range(count)], pieces=[{}])


def initial():
    return dict(status='complete', selected_hypothesis=0, choices=[dict(
        hypothesis=0, arms={arm: dict(all_graph_associations=dict(tracks=[]))
                            for arm in probe.ARMS})])


def inventory_record(arm, row, index=0):
    return dict(arm=arm, track_id='physical-target', component=row['key'],
                track_index=index, current_large=True,
                observation_ids=row['observation_ids'].copy(),
                all_track_observation_ids=row['observation_ids'].copy())


def test_checkpoint_record_is_radio_selected_and_whole_in_both_arms():
    first, second = track('first', 24, 33), track('second', 20, 21)
    scan = SimpleNamespace(tracks=[first, second], curved=[])
    inv = dict(tracks=[inventory_record(arm, row, i)
                       for i, row in enumerate(scan.tracks) for arm in probe.ARMS])
    selection, record = probe.selected_recovery_record(scan, initial(), inv)
    assert [r['component'] for r in selection['targets']] == ['first', 'second']
    assert record['track_id'] == 'physical-target'
    assert record['track_index'] == 0
    inv['tracks'][1]['observation_ids'].pop()
    with pytest.raises(ValueError, match='whole and unowned'):
        probe.selected_recovery_record(scan, initial(), inv)


def test_checkpoint_record_rejects_new_owner_or_paired_identity_change():
    row = track('first', 24, 33)
    scan = SimpleNamespace(tracks=[row], curved=[])
    inv = dict(tracks=[inventory_record(arm, row) for arm in probe.ARMS])
    inv['tracks'][1]['track_id'] = 'different'
    with pytest.raises(ValueError, match='Paired checkpoint'):
        probe.selected_recovery_record(scan, initial(), inv)
    inv['tracks'][1]['track_id'] = 'physical-target'
    inv['tracks'][0]['current_large'] = False
    with pytest.raises(ValueError, match='whole and unowned'):
        probe.selected_recovery_record(scan, initial(), inv)


def annotation_fixture(monkeypatch):
    row = track('first', 24, 33)
    context = dict(scan=SimpleNamespace(tracks=[row], norads=np.array([68106, 65875])),
                   problems={'c0': (SimpleNamespace(flat_times=np.arange(4.)), None)},
                   keep=np.ones(4, bool))
    record = dict(track_index=0)

    def planned_split(full_times, focus, seed, plan):
        train = np.ones(4 + len(focus), bool)
        held = np.zeros(4 + len(focus), bool)
        offset = (seed - 1) * 4
        held[4+offset:8+offset] = True
        train[4+offset:8+offset] = False
        split = dict(seed=seed, held_blocks=[seed], block_s=12, guard_s=2)
        return train, held, split

    monkeypatch.setattr(probe, 'planned_split', planned_split)
    monkeypatch.setattr(probe, 'require_distinct_annotation', lambda result, protocol: None)
    folds, nominations = [], {}
    for seed in (1, 2, 3):
        split = planned_split(None, row['times'], seed, None)[2]
        offers = [dict(candidate_index=0, cost=1.)]
        score = dict(negative_twice_log_density=4., rms_hz=5.)
        proposal = dict(candidate_index=0, norad=68106, alias=0,
                        arms={arm: dict(training_objective=3.,
                                        target_enters_calibration_equations=False,
                                        scores=dict(conditional_target=score))
                              for arm in probe.ARMS})
        folds.append(dict(seed=seed, split=split, proposals=[proposal]))
        nominations[seed] = dict(selected=offers, split=split,
                                 nomination=dict(training_indices=np.array([20, 21]),
                                                 nomination_uses_held_points=False))
    annotation = dict(protocol=dict(seed_list=[1, 2, 3], partition_plan={},
                                    target_used_for_calibration=False, GPS_used=False,
                                    future_TLE=False, phase_rounds=5, position_steps=48,
                                    block_s=12, guard_s=2),
                      result=dict(folds=folds), nominations=nominations)
    return context, record, annotation


def test_fold_receipts_keep_focus_out_of_nominations_and_report_masks(monkeypatch):
    context, record, annotation = annotation_fixture(monkeypatch)
    a = probe.fold_receipts(context, record, annotation, focus_norad=68106)
    b = probe.fold_receipts(context, record, annotation, focus_norad=65875)
    assert len(a) == 3
    assert all(r['target_held_points'] == 4 and r['target_training_points'] == 29 for r in a)
    assert all(r['focus_proposals'][0]['norad'] == 68106 for r in a)
    assert all(r['focus_proposals'] == [] for r in b)
    assert [r['proposals'] for r in a] == [r['proposals'] for r in b]
    assert [r['seed'] for r in a] == [1, 2, 3]


def test_fold_receipts_reject_held_nomination_and_protocol_drift(monkeypatch):
    context, record, annotation = annotation_fixture(monkeypatch)
    annotation['nominations'][1]['nomination']['training_indices'] = np.array([1])
    with pytest.raises(ValueError, match='held support'):
        probe.fold_receipts(context, record, annotation, focus_norad=68106)
    annotation = deepcopy(annotation)
    annotation['nominations'][1]['nomination']['training_indices'] = np.array([20])
    annotation['protocol']['phase_rounds'] = 4
    with pytest.raises(ValueError, match='Original independent'):
        probe.fold_receipts(context, record, annotation, focus_norad=68106)


def test_request_training_fit_requires_exact_saved_policy(monkeypatch):
    from leo.analysis.localization_v5 import annotation_fallback

    fake = SimpleNamespace(policy=dict(id='lbfgsb-gn-fallback-full5-v1',
                                       phase_rounds=5, position_steps=48))
    monkeypatch.setattr(annotation_fallback, 'fit', fake)
    assert probe.request_training_fit({'annotation_training_policy': fake.policy}) is fake
    with pytest.raises(ValueError, match='differs from saved'):
        probe.request_training_fit({'annotation_training_policy': dict(fake.policy,
                                                                      position_steps=47)})
    with pytest.raises(ValueError, match='request-bound'):
        probe.request_training_fit({'annotation_training_policy': {'id': 'unknown'}})


def test_existing_or_qnap_output_rejected_before_request_loading(tmp_path):
    for output in (tmp_path, '/mnt/qnap01/probe'):
        with pytest.raises(SystemExit):
            probe.main(['--request', '/missing', '--native-manifest', '/missing',
                        '--source-root', '/missing', '--output', str(output)])
