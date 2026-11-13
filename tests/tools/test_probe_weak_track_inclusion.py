import hashlib
import json
import pickle
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import probe_weak_track_inclusion as probe
import pytest


def candidate():
    old = {'incumbent': 10}
    target = [f'target-{i}' for i in range(33)]
    owners = dict(old, **{oid: 68106 for oid in target})
    return (dict(kind='new_family', targets=[dict(norad=68106, observation_ids=target)],
                 arms={arm: dict(owners=deepcopy(owners), associated_ids=sorted(owners),
                                 added_points=33, endpoint_east_north_km=[0., 1.],
                                 endpoint_latlon=[1., 2.], negative_twice_elbo=5.)
                       for arm in probe.ARMS}),
            dict(publication_support={arm: dict(owners=old.copy()) for arm in probe.ARMS}),
            set(target))


def test_exact_candidate_requires_all_original_and_exact_new_owners():
    selected, inventory, ids = candidate()
    assert probe.exact_qualified_target(selected, inventory, ids, 68106)['qualified']
    assert not probe.exact_qualified_target(None, inventory, ids, 68106)['qualified']
    selected['arms']['fitted_c']['owners']['target-0'] = 65875
    with pytest.raises(ValueError, match='incumbent or target'):
        probe.exact_qualified_target(selected, inventory, ids, 68106)
    selected, inventory, ids = candidate()
    selected['arms']['c0']['owners']['incumbent'] = 99999
    with pytest.raises(ValueError, match='incumbent or target'):
        probe.exact_qualified_target(selected, inventory, ids, 68106)


def test_metrics_keep_control_and_target_scores_separate_even_on_rejection():
    trial = {name: dict(paired_valid=False, arms={arm: dict(
        endpoint_east_north_km=[0., 1.], endpoint_latlon=[1., 2.],
        negative_twice_elbo=100. if name == 'control' else 150.,
        incumbent_objective=120. if name == 'new_family' else None,
        family=dict(negative_twice_log_density=30.) if name == 'new_family' else None,
        RMS_hz=40., added_points=33 if name == 'new_family' else 0,
        lost_points=0, final_phase_change_s=0.) for arm in probe.ARMS})
             for name in ('control', 'new_family')}
    audit = dict(rows=[dict(role=name, arm=arm, verified=False,
                            owners={'old': 10}) for name in ('control', 'new_family')
                       for arm in probe.ARMS])
    result = probe.arm_metrics(trial, audit, False)
    assert result['control']['arms']['c0']['negative_twice_elbo'] == 100.
    assert result['new_family']['arms']['c0']['incumbent_objective'] == 120.
    assert result['new_family']['arms']['c0']['target_negative_twice_log_density'] == 30.
    assert result['new_family']['arms']['fitted_c']['audit_verified'] is False


def test_checkpoint_requires_same_validation_target_and_both_unowned_arms():
    ids = [f'target-{i}' for i in range(33)]
    track = dict(key='weak', observation_ids=ids)
    context = dict(scan=SimpleNamespace(tracks=[track], norads=np.array([68106]),
                                        sky=dict(bank='causal')),
                   replay={'c0': 0., 'fitted_c': 0.})
    row = dict(track_id='target', component='weak', track_index=0,
               observation_ids=ids, all_track_observation_ids=ids, current_large=True)
    evidence = dict(inventory=dict(tracks=[dict(row, arm=arm) for arm in probe.ARMS]),
                    publication_support={arm: dict(owners={'incumbent': 10})
                                         for arm in probe.ARMS})
    request = dict(annotation_training_policy=dict(id='fit'))
    scientific = dict(receipt_sha256='saved')
    receipt = dict(request_sha256=probe.canonical_digest(request), scientific=scientific,
                   checkpoint_context_replay=context['replay'],
                   causal_bank_sha256=probe.fingerprint(context['scan'].sky),
                   actual_causal_bank_candidates=1, orbit_prior='genuine_previous',
                   original_training_policy=request['annotation_training_policy'],
                   selected_radio_target=dict(component='weak', track_index=0),
                   checkpoint_record=dict(track_id='target', observation_ids=ids))
    annotation = dict(protocol=dict(target=dict(row),
                                    training_optimizer_policy=request['annotation_training_policy']))
    inventory, matched = probe.match_checkpoint(
        context, evidence, scientific, receipt, annotation, request)
    assert matched == set(ids)
    evidence['publication_support']['fitted_c']['owners']['target-0'] = 68106
    with pytest.raises(ValueError, match='whole and unowned'):
        probe.match_checkpoint(context, evidence, scientific, receipt, annotation, request)


def test_raw_validation_hash_and_recomputed_vote_are_required(tmp_path, monkeypatch):
    annotation = dict(result=dict(annotation=dict(status='conditionally_supported_identity',
                                              norad=68106), folds=[dict(seed=i) for i in range(3)]),
                      protocol=dict(target_used_for_calibration=False, GPS_used=False,
                                    future_TLE=False, phase_rounds=5, position_steps=48))
    raw = pickle.dumps(annotation, protocol=5)
    (tmp_path / 'annotation.pickle').write_bytes(raw)
    receipt = dict(status='complete',
                   policy='weak-track-genuine-previous-independent-annotation-v1',
                   annotation_pickle_sha256=hashlib.sha256(raw).hexdigest(),
                   annotation_sha256=probe.fingerprint(annotation),
                   identity_consensus=annotation['result']['annotation'],
                   original_context_unchanged=True, position_inclusion_authorized=False,
                   checkpoint_context_replay={'c0': 0., 'fitted_c': 0.},
                   actual_causal_bank_candidates=1420)
    (tmp_path / 'result.json').write_text(json.dumps(receipt))
    monkeypatch.setattr(probe, 'identity_consensus', lambda *args, **kwargs:
                        annotation['result']['annotation'])
    monkeypatch.setattr(probe, 'require_distinct_annotation', lambda *args: None)
    assert probe.read_validation(tmp_path)[0] == receipt
    (tmp_path / 'annotation.pickle').write_bytes(raw+b'change')
    with pytest.raises(ValueError, match='Complete bound'):
        probe.read_validation(tmp_path)


def orchestration(tmp_path, monkeypatch):
    request_path = tmp_path / 'request.json'
    manifest_path = tmp_path / 'native.json'
    validation = tmp_path / 'validation'
    validation.mkdir()
    for path in (request_path, manifest_path, validation / 'result.json',
                 validation / 'annotation.pickle'):
        path.write_bytes(b'{}')
    request = dict(backend_manifest=dict(native='same'),
                   inclusion_control_policy=dict(id='cache'))
    job = dict(identity=dict(run_id='run'), evaluation_reference=None)
    monkeypatch.setattr(probe, 'request_inputs', lambda path: (request, job, object()))
    monkeypatch.setattr(probe, 'validate_manifest', lambda value: value)
    monkeypatch.setattr(probe, 'read_manifest', lambda path: dict(native='same'))
    monkeypatch.setattr(probe, 'native_equivalence', lambda *args: dict(equal=True))
    monkeypatch.setattr(probe, 'bound_sources', lambda root: {})
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {20})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    output = tmp_path / 'output'
    args = ['--request', str(request_path), '--native-manifest', str(manifest_path),
            '--source-root', str(tmp_path), '--validation', str(validation),
            '--output', str(output)]
    return args, output


def test_plan_does_not_load_archive_or_raw_annotation(tmp_path, monkeypatch):
    args, output = orchestration(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'read_validation', lambda path: pytest.fail('Raw validation read'))
    monkeypatch.setattr(probe, 'load_context', lambda *args: pytest.fail('Archive loaded'))
    assert probe.main(args) == 0
    assert json.loads((output / 'plan.json').read_text())['no_annotation_rerun']
    assert not (output / 'result.json').exists()


def test_raw_trial_and_audit_survive_report_failure(tmp_path, monkeypatch):
    args, output = orchestration(tmp_path, monkeypatch)
    annotation = dict(result=dict(folds=[dict(seed=i) for i in range(3)], track_id='target'))
    receipt = dict(request_sha256=probe.canonical_digest(dict(
        backend_manifest=dict(native='same'), inclusion_control_policy=dict(id='cache'))))
    binding = dict(result_sha256=hashlib.sha256(b'{}').hexdigest(),
                   annotation_pickle_sha256=hashlib.sha256(b'{}').hexdigest())
    monkeypatch.setattr(probe, 'read_validation', lambda path: (receipt, annotation, binding))
    monkeypatch.setattr(probe, 'ProcessBound', lambda *args: object())
    context = dict(problems={arm: (None, np.array([0., 0.])) for arm in probe.ARMS},
                   scan=SimpleNamespace(search_region=SimpleNamespace(latlon=lambda x: [0., 0.])),
                   replay={'c0': 0., 'fitted_c': 0.})
    evidence = dict(publication_support={arm: dict(owners={'old': 10}) for arm in probe.ARMS})
    monkeypatch.setattr(probe, 'load_context', lambda *args: (context, evidence, {}))
    inventory = dict(publication_support=evidence['publication_support'])
    monkeypatch.setattr(probe, 'match_checkpoint',
                        lambda *args: (inventory, {'target'}))
    monkeypatch.setattr(probe, 'identity_consensus',
                        lambda *args, **kwargs: dict(norad=68106))
    monkeypatch.setattr(probe, 'shared_family_route', lambda *args: False)
    monkeypatch.setattr(probe, 'ControlCacheFactory', lambda *args: lambda: object())
    monkeypatch.setattr(probe, 'fit_new', lambda *args, **kwargs: dict(control={}, new_family={}))
    monkeypatch.setattr(probe, 'audit_inclusion',
                        lambda *args, **kwargs: dict(all_verified=False))
    monkeypatch.setattr(probe, 'single_candidate', lambda *args: None)
    monkeypatch.setattr(probe, 'arm_metrics',
                        lambda *args: (_ for _ in ()).throw(ValueError('report bug')))
    monkeypatch.setattr(probe, 'native_counts', lambda backend: {})
    with pytest.raises(ValueError, match='report bug'):
        probe.main(args + ['--run'])
    assert set(p.name for p in output.glob('*.pickle')) == {
        'primary-fit.pickle', 'primary-audit.pickle'}
    assert json.loads((output / 'failure.json').read_text())['status'] == 'failed'
    assert not (output / 'result.json').exists()


def test_existing_and_qnap_outputs_rejected_before_request_loading(tmp_path):
    for output in (tmp_path, Path('/mnt/qnap01/probe')):
        with pytest.raises(SystemExit):
            probe.main(['--request', '/missing', '--native-manifest', '/missing',
                        '--source-root', '/missing', '--validation', '/missing',
                        '--output', str(output)])
