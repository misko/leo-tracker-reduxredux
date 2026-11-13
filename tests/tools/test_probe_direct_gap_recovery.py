import json
import pickle
from copy import deepcopy
from types import SimpleNamespace

import probe_direct_gap_recovery as probe
import pytest


def rows():
    targets = [dict(track_id='gap', component='curve', current_large=True,
                    observation_ids=['new', 'isolated'],
                    all_track_observation_ids=['new', 'isolated'], arm=arm)
               for arm in probe.ARMS]
    return dict(inventory=dict(tracks=targets),
                owners={arm: {'old': 10} for arm in probe.ARMS}, publication_support={})


def annotation():
    return dict(result=dict(annotation=dict(status='conditionally_supported_identity', norad=20),
                            folds=[dict(seed=seed) for seed in [1, 2, 3]]),
                protocol=dict(target=dict(observation_ids=['new'])))


def trial():
    return dict(protocol=dict(
        matched_c_arms=True, phase_rounds=5, steps=48, target_calibrates_receiver=False,
        target_updates_unobserved_satellite_parameters=False,
        original_noise_weights_and_priors=True,
        conditional_satellite_refresh=True, targets=[dict(observation_ids=['new'], norad=20)]),
        target_0=dict(paired_valid=True, arms={arm: dict(
            proposed_owners={'old': 10, 'new': 20}, proposed_associated_ids=['old', 'new'],
            final_phase_change_s=0., endpoint_latlon=[1., 2.], added_points=1,
            negative_twice_elbo=100.) for arm in probe.ARMS}))


def test_timing_selector_uses_matched_wholly_unowned_tracks_and_proper_components(monkeypatch):
    evidence = rows()
    monkeypatch.setattr(probe, 'prepare_gap', lambda *args: dict(branches=[
        dict(branch_id='whole', observation_ids=['new', 'isolated'], times_s=[0., 20.]),
        dict(branch_id='branch', observation_ids=['new'], times_s=[0., 10.])]))
    selected = probe.timing_candidates({}, evidence, [])
    assert selected == [dict(track_id='gap', component='curve', branch_id='branch',
                             points=1, parent_points=2, start_s=0., end_s=10.)]
    evidence['owners']['fitted_c']['new'] = 20
    assert probe.timing_candidates({}, evidence, []) == []
    evidence = rows()
    evidence['inventory']['tracks'][1]['observation_ids'] = ['new']
    assert probe.timing_candidates({}, evidence, []) == []


def test_independent_identity_requires_distinct_holdouts_and_existing_family(monkeypatch):
    calls = []
    monkeypatch.setattr(probe, 'require_distinct_annotation',
                        lambda result, protocol: calls.append(result['folds']))
    monkeypatch.setattr(probe, 'shared_family_route', lambda folds, norad: norad == 20)
    saved = annotation()
    assert probe.supported_shared_identity(saved)
    saved['result']['annotation']['norad'] = 30
    assert not probe.supported_shared_identity(saved)
    saved['result']['annotation']['status'] = 'ambiguous_identity'
    assert not probe.supported_shared_identity(saved)
    assert len(calls) == 3


def test_full_qualification_requires_matched_native_additions_and_original_protocol():
    observations = [dict(observation_id=oid) for oid in ['old', 'new', 'isolated']]
    audit = dict(all_verified=True)
    assert probe.acceptance(trial(), audit, rows(), observations, annotation())['qualified']
    altered = trial()
    altered['target_0']['arms']['fitted_c']['proposed_owners']['new'] = 30
    assert not probe.acceptance(altered, audit, rows(), observations, annotation())['qualified']
    altered = trial()
    altered['protocol']['steps'] = 1
    with pytest.raises(ValueError, match='Original paired'):
        probe.acceptance(altered, audit, rows(), observations, annotation())
    altered = trial()
    for arm in probe.ARMS:
        altered['target_0']['arms'][arm]['proposed_owners'].pop('new')
        altered['target_0']['arms'][arm]['proposed_associated_ids'].remove('new')
    with pytest.raises(ValueError, match='exactly the annotated'):
        probe.acceptance(altered, audit, rows(), observations, annotation())


def job():
    return dict(identity=dict(input_sha256='input'), native_input='native', track_config='config',
                runtime='runtime', scan_identities=['scan'], search_center=[1., 2.],
                screen_center=[1., 2.], tle_root='causal')


def test_unmatched_reference_cannot_be_compared():
    reference = job()
    reference['identity']['input_sha256'] = 'unrelated'
    with pytest.raises(ValueError, match='Matched input'):
        probe.matched_jobs(job(), reference)


def orchestration(tmp_path, monkeypatch):
    paths = [tmp_path / name for name in ['candidate.json', 'reference.json']]
    for path in paths:
        path.write_text('{}\n')
    request, reference = dict(backend_manifest={}, side='candidate'), dict(side='reference')
    monkeypatch.setattr(probe, 'request_inputs', lambda path: (
        request if path == paths[0] else reference, job(), None))
    monkeypatch.setattr(probe, 'runtime_bindings', lambda root: {})
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {20})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    monkeypatch.setattr(probe, 'validate_manifest', lambda manifest: manifest)
    monkeypatch.setattr(probe, 'ProcessBound', lambda *args: object())
    context = dict(scan=SimpleNamespace(tracks=[]), unpickleable=lambda: None)
    monkeypatch.setattr(probe, 'load_context', lambda *args: (context, rows(), dict(replay=True)))
    prepared = dict(tracks=dict(observations=[dict(observation_id=oid)
                                            for oid in ['old', 'new', 'isolated']]))
    reference_gap = dict(selected=dict(branch_id='branch', identity=dict(norad=20)),
                         candidate=dict(trial=dict(arms={arm: dict(endpoint_latlon=[1., 2.])
                                                        for arm in probe.ARMS})))
    monkeypatch.setattr(probe, 'load_saved', lambda *args: dict(
        sha256='receipt', evidence=dict(preparation=deepcopy(prepared),
                                       audit=dict(gap_recovery=reference_gap))))
    monkeypatch.setattr(probe, 'timing_candidates', lambda *args: [dict(
        track_id='gap', branch_id='branch')])
    monkeypatch.setattr(probe, 'prepare_gap', lambda *args: {})
    monkeypatch.setattr(probe, 'annotate_gap',
                        lambda *args: (annotation(), dict(stage='annotation')))
    monkeypatch.setattr(probe, 'supported_shared_identity', lambda value: True)
    monkeypatch.setattr(probe, 'fit_gap', lambda *args: (trial(), dict(stage='fit')))
    monkeypatch.setattr(probe, 'audit_gap',
                        lambda *args: (dict(all_verified=True), dict(stage='audit')))
    output = tmp_path / 'output'
    args = ['--request', str(paths[0]), '--reference-request', str(paths[1]),
            '--runtime-root', str(tmp_path), '--output', str(output), '--run']
    return args, output


def test_mocked_complete_run_preserves_wrapper_schema_and_portable_stage_outputs(
        tmp_path, monkeypatch):
    args, output = orchestration(tmp_path, monkeypatch)
    assert probe.main(args) == 0
    result = json.loads((output / 'result.json').read_text())
    assert result['policy'] == 'direct-timing-gap-v1'
    assert result['qualification']['qualified']
    assert result['original_eligibility_equivalence'] is False
    assert result['published_result_changed'] is False
    assert result['reference_comparison']['same_selected_branch']
    raw = pickle.loads((output / 'trial.pickle').read_bytes())
    assert set(raw) == {'annotation', 'inclusion', 'audit'}
    assert [stage['status'] for stage in result['stages']] == ['complete'] * 4


def test_default_plan_does_not_load_scientific_evidence(tmp_path, monkeypatch):
    args, output = orchestration(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'load_context', lambda *args: pytest.fail('Context loaded'))
    monkeypatch.setattr(probe, 'load_saved', lambda *args: pytest.fail('Archive loaded'))
    assert probe.main(args[:-1]) == 0
    assert not (output / 'result.json').exists()
    plan = json.loads((output / 'plan.json').read_text())
    assert plan['maximum_components'] == 1
    assert plan['original_eligibility_equivalence'] is False


def test_deadline_retains_failure_and_completed_portable_stages(tmp_path, monkeypatch):
    from leo.operations.localization_v3_job import StageDeadline

    args, output = orchestration(tmp_path, monkeypatch)

    def expired(*args):
        raise StageDeadline('bounded test deadline')

    monkeypatch.setattr(probe, 'fit_gap', expired)
    with pytest.raises(StageDeadline):
        probe.main(args)
    failure = json.loads((output / 'failure.json').read_text())
    assert failure['error_type'] == 'StageDeadline'
    assert failure['stages'][-1]['name'] == 'inclusion'
    assert failure['stages'][-1]['status'] == 'failed'
    assert set(pickle.loads((output / 'partial-trial.pickle').read_bytes())) == {'annotation'}
    assert not (output / 'result.json').exists()
