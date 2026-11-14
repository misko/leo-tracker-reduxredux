"""Independent runner checks; no numerical workers or frozen fixture changes."""

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2] / 'tools'
SPEC = importlib.util.spec_from_file_location('discovery_pairs_tests', ROOT / 'evaluate_initial_discovery.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
EVALUATOR = ROOT / 'evaluate_algo07.py'


def members():
    return [dict(dataset_label=case, recording_id=group, availability=availability)
            for case, group, availability in (
                ('A', 'one', 'available'), ('B', 'one', 'available'),
                ('C', 'two', 'available'), ('D', 'three', 'available'),
                ('E', 'four', 'missing'))]


def test_randomized_selection_preserves_recordings_and_is_reproducible():
    first = runner.assignments(members(), seed='fixed', profile='quick', quick_groups=2)
    assert first == runner.assignments(members(), seed='fixed', profile='quick', quick_groups=2)
    assert ('A' in first['cases']) == ('B' in first['cases'])
    assert 'E' not in first['cases']
    assert first['missing_cases'] == ['E']


def test_development_excludes_correlated_group():
    result = runner.assignments(members(), seed='fixed', profile='quick',
                                development=['A'], quick_groups=2)
    assert set(result['cases']) == {'C', 'D'}
    assert result['development_cases'] == ['A']


def test_full_retains_missing_and_all_groups():
    result = runner.assignments(members(), seed='fixed', profile='full')
    assert set(result['cases']) == {'A', 'B', 'C', 'D', 'E'}
    assert result['missing_cases'] == ['E']


@pytest.mark.parametrize('cases', ['A', 'A,A', 'Z'])
def test_invalid_or_split_explicit_groups_are_rejected(cases):
    with pytest.raises(ValueError):
        runner.assignments(members(), seed='fixed', profile='development', cases=cases)


def test_explicit_qualification_cannot_reuse_development():
    with pytest.raises(ValueError, match='development'):
        runner.assignments(members(), seed='fixed', profile='quick', cases='A,B', development=['A'])


def protocol(tmp_path):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    runner.write(snapshot / 'template-request.json', dict(
        schema_version=1, evaluation_reference={'latitude_deg': 1},
        execution_policy='validation-all-work', runtime=dict(python='example'),
        search_center=[1, 2], screen_center=[3, 4]))
    role = dict(source=dict(root='/source', files={}, sha256='source-sha'),
                evaluator=str(EVALUATOR), initial=None,
                native_manifest='/baseline-native.json', backend_manifest={'native': 'baseline'})
    candidate = dict(role, initial=dict(id='initial-discovery-v1', seed_policy='anchor-round-robin-v1',
                                       ranking_policy='legacy'), native_manifest='/candidate-native.json',
                     backend_manifest={'native': 'candidate'})
    return dict(roles=dict(baseline=role, candidate=candidate), snapshot=str(snapshot), output=str(tmp_path / 'staging'),
                references=None, timeout=1200, selection=dict(cases=['A', 'E'], missing_cases=['E']),
                fast_flags=runner.FAST_FLAGS, members=[dict(dataset_label='A', input_sha256='input', availability='available',
                                                           recording_id='recording', session_id='scan')],
                bindings={str(snapshot / 'inventory.json'): 'inventory-sha',
                          str(snapshot / 'inputs/config.json'): 'config-sha',
                          str(EVALUATOR): runner.sha(EVALUATOR)},
                schedule=[dict(case='A', repetition=0), dict(case='E', repetition=0)])


def worker_report(manifest, *, side='candidate', case='A', status='complete', repetition=0):
    role = manifest['roles'][side]
    plan = dict(source=role['source'], version='algo07v5', snapshot=manifest['snapshot'], module='leo.cli.algo07v5',
                output=str(Path(manifest['output']) / (case + '-r0') / side),
                selected=[case], timeout_seconds=1200, inventory_sha256='inventory-sha',
                config_sha256='config-sha', backend_manifest=role['backend_manifest'],
                evaluator=dict(path=role['evaluator'], sha256=manifest['bindings'][role['evaluator']]),
                jobs=[dict(case=case, repetition=0, reference={'latitude_deg': 1},
                           request=dict(job=dict(evaluation_reference=None),
                                        **({'initial_discovery_policy': role['initial']} if role['initial'] else {})))],
                annotation_training_policy=dict(id='lbfgsb-gn-fallback-full5-v1'),
                inclusion_control_policy=dict(id='native-complete-controls-v1'),
                joint_schedule_policy=dict(id='defer-factorized-unless-retry-v1'),
                recovery_target_policy=dict(id='rf-target-prefix-v1', maximum_targets=0))
    if role['initial']:
        plan['initial_discovery_policy'] = role['initial']
    if role.get('direct_gap'):
        plan['direct_gap_policy'] = role['direct_gap']
    requested_job = runner.read(Path(manifest['snapshot']) / 'template-request.json')
    requested_job.update(evaluation_reference=None,
                         native_input=dict(path=str(Path(manifest['snapshot']) / 'inputs' / case / 'native.json'), sha256='input'),
                         track_config=dict(path=str(Path(manifest['snapshot']) / 'inputs/config.json'), sha256='config-sha'),
                         tle_root=str(Path(manifest['snapshot']) / 'inputs' / case / 'tle'),
                         output_root=str(Path(plan['output']) / (case + '-r0') / 'algo07v5/publication'),
                         identity=dict(run_id='v5-example', session_id='scan', input_sha256='input'),
                         scan_identities=['scan'], title='recording')
    request = plan['jobs'][0]['request']
    request['job'] = requested_job
    request['backend_manifest'] = role['backend_manifest']
    for key in ('annotation_training_policy', 'inclusion_control_policy', 'joint_schedule_policy', 'recovery_target_policy'):
        request[key] = plan[key]
    if role.get('direct_gap'):
        request['direct_gap_policy'] = role['direct_gap']
    workload = runner.digest({key: value for key, value in requested_job.items()
                              if key not in ('identity', 'output_root', 'title')})
    plan['jobs'][0].update(availability='available', workload_sha256=workload)
    arms = {arm: dict(gps_error_km=1, residual_rms_hz=2, frequency_score=3,
                      associated_points=5, owners={'one': 'satellite'})
            for arm in ('c0', 'fitted_c')}
    return dict(plan=plan, plan_sha256=runner.digest(plan), results=[dict(
        case=case, repetition=repetition, status=status, input_sha256='input',
        tle_sha256=runner.digest({}), reference={'latitude_deg': 1}, workload_sha256=workload, availability='available',
        arms=arms, process=dict(cpu_complete=True, wall_seconds=3, cpu_seconds=2, returncode=0),
        stage_events=[dict(event='stage', stage='initial', seconds=1)])])


def test_direct_baseline_and_candidate_use_true_sources_evaluators_and_native_bindings(tmp_path):
    manifest = protocol(tmp_path)
    job = dict(case='A', repetition=0)
    baseline = runner.command(manifest, job, 'baseline', tmp_path / 'baseline', '12,13,14')
    candidate = runner.command(manifest, job, 'candidate', tmp_path / 'candidate', '12,13,14')
    assert '--initial-seed-policy' not in baseline
    assert candidate[candidate.index('--initial-seed-policy') + 1] == 'anchor-round-robin-v1'
    assert baseline[baseline.index('--native-manifest') + 1] == '/baseline-native.json'
    assert candidate[candidate.index('--native-manifest') + 1] == '/candidate-native.json'
    assert '--recovery-target-limit' in baseline and '--recovery-target-limit' in candidate


def test_direct_gap_command_and_report_bind_only_candidate_policy(tmp_path):
    from leo.contracts.localization_v5 import direct_gap_policy

    manifest = protocol(tmp_path)
    manifest['roles']['candidate']['initial'] = None
    manifest['roles']['candidate']['direct_gap'] = direct_gap_policy()
    assignment = dict(case='A', repetition=0)
    baseline = runner.command(manifest, assignment, 'baseline', tmp_path / 'baseline', '12')
    candidate = runner.command(manifest, assignment, 'candidate', tmp_path / 'candidate', '12')
    assert '--direct-gap-policy' not in baseline
    assert candidate[candidate.index('--direct-gap-policy') + 1] == 'direct-timing-gap-v1'
    assert '--initial-seed-policy' not in candidate
    assert runner.validate_report(worker_report(manifest), manifest, assignment, 'candidate')['status'] == 'complete'
    wrong = worker_report(manifest)
    wrong['plan']['jobs'][0]['request'].pop('direct_gap_policy')
    wrong['plan_sha256'] = runner.digest(wrong['plan'])
    with pytest.raises(ValueError, match='direct-gap policy'):
        runner.validate_report(wrong, manifest, assignment, 'candidate')


def test_default_plan_omits_direct_gap_role_binding(tmp_path, monkeypatch):
    snapshot = tmp_path / 'snapshot'
    (snapshot / 'inputs').mkdir(parents=True)
    runner.write(snapshot / 'inventory.json', dict(members=[dict(
        dataset_label='DS26-0002', recording_id='one', availability='available')]))
    runner.write(snapshot / 'template-request.json', {})
    runner.write(snapshot / 'inputs/config.json', {})
    native_file = tmp_path / 'native.bin'
    native_file.write_bytes(b'native')
    native = tmp_path / 'manifest.json'
    runner.write(native, dict(binary=str(native_file), source=str(native_file),
                              wrapper=str(native_file), provider=dict(path=str(native_file))))
    source = tmp_path / 'source'
    source.mkdir()
    evaluator_path = tmp_path / 'evaluator.py'
    evaluator_path.write_text('')
    ev = SimpleNamespace(source_binding=lambda path: dict(root=str(path.resolve()),
                                                        sha256='source', files={}),
                         owned_import=lambda name, source: pytest.fail('No direct policy import'))
    monkeypatch.setattr(runner, 'evaluator', lambda path: ev)
    args = SimpleNamespace(output=tmp_path / 'output', archive_root=None,
        reserve_gib=1, expected_gib=1, stage_free_gib=1, archive_free_gib=1,
        snapshot=snapshot, candidate_evaluator=evaluator_path, baseline_evaluator=evaluator_path,
        baseline_source=source, candidate_source=source,
        baseline_native_manifest=native, candidate_native_manifest=native,
        development_split=[], profile='development', cases='DS26-0002', quick_groups=1,
        seed='fixed', repeats=1, timeout=1200, references=None,
        historical_baseline_root=None, initial_seed_policy='anchor-round-robin-v1',
        initial_ranking_policy='legacy', direct_gap_policy=None)
    plan = runner.prepare(args)
    assert 'direct_gap' not in plan['roles']['baseline']
    assert 'direct_gap' not in plan['roles']['candidate']
    assert plan['schema_version'] == 2


def historical_gap_plan_fixture(tmp_path, monkeypatch):
    snapshot = tmp_path / 'snapshot'
    runner.write(snapshot / 'inventory.json', dict(members=[
        dict(dataset_label='A', recording_id='one', availability='available'),
        dict(dataset_label='E', recording_id='two', availability='missing')]))
    runner.write(snapshot / 'template-request.json', {})
    runner.write(snapshot / 'inputs/config.json', {})
    roots = [tmp_path / side for side in ('original-source', 'gap-source')]
    evaluators = [tmp_path / (side + '-evaluator.py') for side in ('original', 'gap')]
    manifests = [tmp_path / (side + '-native.json') for side in ('original', 'gap')]
    for root, evaluator_path, native_path in zip(roots, evaluators, manifests, strict=True):
        root.mkdir()
        evaluator_path.write_text(root.name)
        files = {}
        for key in ('binary', 'source', 'wrapper', 'provider'):
            path = root / key
            path.write_text(key)
            files[key] = str(path)
        runner.write(native_path, dict(
            binary=files['binary'], source=files['source'], wrapper=files['wrapper'],
            provider=dict(path=files['provider'])))
    policy = dict(id='direct-timing-gap-v1')
    ev = SimpleNamespace(
        source_binding=lambda path: dict(
            root=str(path.resolve()), sha256=path.resolve().name, files={}),
        owned_import=lambda name, source: SimpleNamespace(direct_gap_policy=lambda name: policy))
    monkeypatch.setattr(runner, 'evaluator', lambda path: ev)
    historical = tmp_path / 'original-cohort'
    runner.write(historical / 'protocol.json', dict(
        snapshot=str(snapshot), cases=['A', 'E'],
        sources=dict(candidate=ev.source_binding(roots[0])),
        candidate_limit=0, timeout=2400, references=None,
        bindings={str(path): runner.sha(path) for path in (
            snapshot / 'inventory.json', snapshot / 'inputs/config.json',
            snapshot / 'template-request.json', evaluators[0], manifests[0])}))
    args = SimpleNamespace(output=tmp_path / 'staging', archive_root=None,
        reserve_gib=20, expected_gib=10, stage_free_gib=10, archive_free_gib=10,
        snapshot=snapshot, candidate_evaluator=evaluators[1], baseline_evaluator=evaluators[0],
        baseline_source=roots[0], candidate_source=roots[1],
        baseline_native_manifest=manifests[0], candidate_native_manifest=manifests[1],
        development_split=[], profile='full', cases=None, quick_groups=1,
        seed='fixed', repeats=1, timeout=2400, references=None,
        historical_baseline_root=historical, initial_seed_policy='legacy',
        initial_ranking_policy='legacy', direct_gap_policy='direct-timing-gap-v1')
    return args


def test_full_historical_gap_plan_reuses_original_with_distinct_role_bindings(
        tmp_path, monkeypatch):
    args = historical_gap_plan_fixture(tmp_path, monkeypatch)
    plan = runner.prepare(args)
    assert plan['schema_version'] == 5
    assert plan['roles']['baseline']['source']['root'] == str(args.baseline_source)
    assert plan['roles']['candidate']['source']['root'] == str(args.candidate_source)
    assert plan['roles']['baseline']['evaluator'] == str(args.baseline_evaluator)
    assert plan['roles']['candidate']['evaluator'] == str(args.candidate_evaluator)
    assert plan['roles']['baseline']['native_manifest'] == str(args.baseline_native_manifest)
    assert plan['roles']['candidate']['native_manifest'] == str(args.candidate_native_manifest)
    assert plan['roles']['baseline']['initial'] is None
    assert plan['roles']['candidate']['initial'] is None
    assert 'direct_gap' not in plan['roles']['baseline']
    assert plan['roles']['candidate']['direct_gap'] == dict(id='direct-timing-gap-v1')
    assert plan['historical_baseline_root'] == str(args.historical_baseline_root)
    assert plan['selection']['cases'] == [a['case'] for a in plan['schedule']]
    assert 'accuracy/work only' in plan['performance']
    assert '--direct-gap-policy' in runner.command(
        plan, plan['schedule'][0], 'candidate', tmp_path / 'candidate', '1')
    assert '--direct-gap-policy' not in runner.command(
        plan, plan['schedule'][0], 'baseline', tmp_path / 'baseline', '1')
    args.historical_baseline_root = None
    assert runner.prepare(args)['schema_version'] == 4


@pytest.mark.parametrize('change', (
    'profile', 'repeats', 'source', 'snapshot', 'references', 'budget', 'timeout',
    'cohort_missing', 'cohort_duplicate', 'snapshot_content',
    'baseline_evaluator', 'baseline_native',
    'candidate_native'))
def test_full_historical_gap_plan_rejects_unmatched_cohort(tmp_path, monkeypatch, change):
    args = historical_gap_plan_fixture(tmp_path, monkeypatch)
    path = args.historical_baseline_root / 'protocol.json'
    protocol = runner.read(path)
    if change == 'profile':
        args.profile = 'quick'
        args.cases = 'A,E'
    elif change == 'repeats':
        args.repeats = 2
    elif change == 'source':
        args.baseline_source = args.candidate_source
    elif change == 'snapshot':
        protocol['snapshot'] = '/other/snapshot'
    elif change == 'references':
        protocol['references'] = '/other/references.json'
    elif change == 'budget':
        protocol['candidate_limit'] = 1
    elif change == 'timeout':
        args.timeout = 1200
    elif change == 'cohort_missing':
        protocol['cases'] = ['A']
    elif change == 'cohort_duplicate':
        protocol['cases'] = ['A', 'A']
    elif change == 'snapshot_content':
        inventory = runner.read(args.snapshot / 'inventory.json')
        inventory['changed'] = True
        runner.write(args.snapshot / 'inventory.json', inventory)
    elif change == 'baseline_evaluator':
        protocol['bindings'].pop(str(args.baseline_evaluator))
    elif change == 'baseline_native':
        protocol['bindings'].pop(str(args.baseline_native_manifest))
    else:
        (args.candidate_source / 'binary').write_text('different native binary')
    runner.write(path, protocol)
    with pytest.raises(ValueError):
        runner.prepare(args)


def test_historical_gap_rejects_equal_native_drift_after_original_protocol_freeze(
        tmp_path, monkeypatch):
    args = historical_gap_plan_fixture(tmp_path, monkeypatch)
    protocol_path = args.historical_baseline_root / 'protocol.json'
    protocol = runner.read(protocol_path)
    original_native = runner.read(args.baseline_native_manifest)
    candidate_native = runner.read(args.candidate_native_manifest)
    binary = original_native['binary']
    protocol['bindings'][binary] = runner.sha(binary)
    runner.write(protocol_path, protocol)
    Path(binary).write_text('same new native bytes')
    Path(candidate_native['binary']).write_text('same new native bytes')
    with pytest.raises(ValueError, match='Historical protocol binding changed'):
        runner.prepare(args)


def test_historical_gap_keeps_all_original_bindings_frozen_during_execution(
        tmp_path, monkeypatch):
    args = historical_gap_plan_fixture(tmp_path, monkeypatch)
    driver = args.historical_baseline_root / 'driver.py'
    driver.write_text('original cohort driver')
    protocol_path = args.historical_baseline_root / 'protocol.json'
    protocol = runner.read(protocol_path)
    protocol['bindings'][str(driver)] = runner.sha(driver)
    runner.write(protocol_path, protocol)
    plan = runner.prepare(args)
    assert plan['bindings'][str(driver)] == runner.sha(driver)
    driver.write_text('changed cohort driver')
    with pytest.raises(ValueError, match='Frozen bound file changed'):
        runner.check_bindings(plan)


def test_saved_report_binds_request_and_actual_policy(tmp_path):
    manifest = protocol(tmp_path)
    report = worker_report(manifest)
    assert runner.validate_report(report, manifest, dict(case='A'), 'candidate')['status'] == 'complete'
    report['plan']['jobs'][0]['request']['job']['evaluation_reference'] = {'gps': 1}
    report['plan_sha256'] = runner.digest(report['plan'])
    with pytest.raises(ValueError, match='GPS'):
        runner.validate_report(report, manifest, dict(case='A'), 'candidate')


@pytest.mark.parametrize('key,value', [
    ('source', {'wrong': True}), ('backend_manifest', {'wrong': True}),
    ('initial_discovery_policy', {'wrong': True}), ('timeout_seconds', 1),
])
def test_saved_binding_drift_is_rejected(tmp_path, key, value):
    manifest = protocol(tmp_path)
    report = worker_report(manifest)
    report['plan'][key] = value
    report['plan_sha256'] = runner.digest(report['plan'])
    with pytest.raises(ValueError):
        runner.validate_report(report, manifest, dict(case='A'), 'candidate')


def test_incomplete_failures_remain_visible_without_timing_claim(tmp_path):
    manifest = protocol(tmp_path)
    baseline = worker_report(manifest, side='baseline')
    candidate = worker_report(manifest, status='failed')
    result = runner.aggregate(manifest, {('A', 0): dict(baseline=baseline, candidate=candidate)})
    assert result['statuses'] == dict(baseline=dict(complete=1, absent=1), candidate=dict(failed=1, absent=1))
    assert not result['complete_coverage'] and not result['headline_timing_eligible']
    assert result['timing']['wall_seconds']['aggregate']['speedup'] is None


def test_repeated_rows_and_matched_arms_have_ownership_and_frequency_separate(tmp_path):
    manifest = protocol(tmp_path)
    manifest['schedule'] = [dict(case='A', repetition=0), dict(case='A', repetition=1)]
    reports = dict(baseline=worker_report(manifest, side='baseline'), candidate=worker_report(manifest))
    reports['candidate']['results'][0]['arms']['c0']['owners']['one'] = 'other'
    result = runner.aggregate(manifest, {('A', 0): reports, ('A', 1): copy.deepcopy(reports)})
    assert result['complete_coverage']
    assert [pair['repetition'] for pair in result['pairs']] == [0, 1]
    assert result['pairs'][0]['arms']['c0']['ownership_changes'] == 1
    assert set(result['pairs'][0]['arms']['c0']) >= {'gps_error_km', 'frequency_score'}
    assert result['pairs'][0]['stage_seconds']['candidate']['initial'] == 1
    assert not result['headline_timing_eligible']


def test_qnap_output_rejected():
    with pytest.raises(ValueError, match='QNAP'):
        runner.local('/mnt/qnap01/analysis-output')


def inspection_fixture(tmp_path, monkeypatch):
    manifest = protocol(tmp_path)
    report = worker_report(manifest)
    request = report['plan']['jobs'][0]['request']
    request['job'].update(identity=dict(run_id='v5-example'), output_root=str(tmp_path / 'public'))
    request['backend_manifest'] = manifest['roles']['candidate']['backend_manifest']
    request_path = tmp_path / 'request.json'
    report_path = tmp_path / 'report.json'
    row = report['results'][0]
    row.update(request_path=str(request_path), result_sha256='result-sha')
    evidence = dict(identity=request['job']['identity'], provenance=dict(modules={}, implementation_sha256=runner.digest({}),
        request_sha256=runner.digest(request), initial_discovery_policy=request['initial_discovery_policy'],
        native_backend=dict(manifest=request['backend_manifest'], receipts=[dict(counts=dict(calls=10))])),
        audit=dict(initial=dict(initial_discovery_policy=request['initial_discovery_policy']),
                   recovery_inventory=dict(original_selected_track_ids=['target'], policy_omitted_track_ids=['target'],
                                           selected_targets=[]), numerical_recovery=dict(completed_target_ids=[])))
    saved = dict(evidence=evidence, receipt=dict(result_sha256='result-sha'))
    for key in ('annotation_training_policy', 'inclusion_control_policy', 'joint_schedule_policy', 'recovery_target_policy'):
        evidence['provenance'][key] = request[key]
    ev = SimpleNamespace(
        source_binding=lambda path: manifest['roles']['candidate']['source'], digest=runner.digest,
        project=lambda evidence, reference: worker_report(manifest)['results'][0]['arms'])
    ev.owned_import = lambda name, source: (
        SimpleNamespace(canonical_digest=runner.digest) if name == 'leo.contracts.digests' else
        __import__('leo.contracts.localization_v5', fromlist=['localization_v5'])
        if name == 'leo.contracts.localization_v5' else
        SimpleNamespace(LocalizationV5Store=lambda path: SimpleNamespace(load=lambda identity: saved)))
    monkeypatch.setattr(runner, 'evaluator', lambda path: ev)
    args = SimpleNamespace(evaluator=EVALUATOR, source_root=Path('/source'), request=request_path,
                           report=report_path, result_sha256='result-sha', manifest_sha256='protocol-sha',
                           output=tmp_path / 'work.json')

    def persist():
        report['plan_sha256'] = runner.digest(report['plan'])
        runner.write(request_path, request)
        runner.write(report_path, report)

    persist()
    return args, report, request, evidence, persist


def test_direct_gap_public_inspection_accepts_no_trigger_and_rejects_missing_audit(
        tmp_path, monkeypatch):
    from leo.contracts import localization_v5
    import numpy as np

    args, report, request, evidence, persist = inspection_fixture(tmp_path, monkeypatch)
    policy = localization_v5.direct_gap_policy()
    request['direct_gap_policy'] = policy
    report['plan']['direct_gap_policy'] = policy
    evidence['provenance']['direct_gap_policy'] = policy
    evidence['audit']['gap_recovery'] = dict(policy=policy, targets=[], selected=None,
                                            trials=[], stages=[], numerical_receipts={},
                                            no_GPS_inference=True, causal_only=True)
    evidence['provenance']['request_sha256'] = runner.digest(request)
    persist()
    runner.inspect_publication(args)
    assert runner.read(args.output)['direct_gap_recovery']['targets'] == []
    assert runner.read(args.output)['direct_gap_recovery']['selected'] is None
    args.output.unlink()
    evidence['audit']['gap_recovery'].update(
        targets=[dict(track_id='track', branch_id='branch', points=12, parent_points=13)],
        selected=dict(track_id='track', branch_id='branch',
                      identity=dict(norad=123, status='conditionally_supported_identity',
                                    minimum_margin=42.0),
                      qualification=dict(qualified=True, internal=np.array([1, 2]))),
        trials=[dict(internal=np.array([3, 4]))])
    runner.inspect_publication(args)
    saved = runner.read(args.output)['direct_gap_recovery']
    assert saved['selected']['norad'] == 123 and saved['selected']['qualified'] is True
    assert saved['trial_count'] == 1 and 'internal' not in saved['selected']
    args.output.unlink()
    evidence['audit']['gap_recovery'].pop('policy')
    with pytest.raises(ValueError, match='Direct gap selection'):
        runner.inspect_publication(args)


def test_public_inspector_binds_work_and_validates_every_resume(tmp_path, monkeypatch):
    args, _, _, _, _ = inspection_fixture(tmp_path, monkeypatch)
    runner.inspect_publication(args)
    work = runner.read(args.output)
    assert work['public_store_validated'] and work['native_counts']['calls'] == 10
    assert work['manifest_sha256'] == 'protocol-sha'
    assert 'direct_gap_recovery' not in work
    runner.inspect_publication(args)
    work['native_counts']['calls'] = 1
    runner.write(args.output, work)
    with pytest.raises(ValueError, match='Saved work receipt differs'):
        runner.inspect_publication(args)


def test_public_inspector_resumes_tuple_ranking_through_json_contract(tmp_path, monkeypatch):
    args, _, _, evidence, _ = inspection_fixture(tmp_path, monkeypatch)
    evidence['audit']['initial']['initial_discovery_ranking'] = [dict(
        node_index=0, signature=(('track', 1, 2, 0),), ranking_score=1.0)]
    runner.inspect_publication(args)
    first = args.output.read_bytes()
    runner.inspect_publication(args)
    assert args.output.read_bytes() == first
    evidence['audit']['initial']['initial_discovery_ranking'][0]['ranking_score'] = 2.0
    with pytest.raises(ValueError, match='Saved work receipt differs'):
        runner.inspect_publication(args)


@pytest.mark.parametrize('tamper', ['request', 'request_digest', 'manifest', 'metrics'])
def test_public_inspector_rejects_tampered_request_native_or_metrics(tmp_path, monkeypatch, tamper):
    args, report, request, evidence, persist = inspection_fixture(tmp_path, monkeypatch)
    if tamper == 'request':
        request['job']['identity']['run_id'] = 'v5-other'
    elif tamper == 'request_digest':
        evidence['provenance']['request_sha256'] = 'wrong'
    elif tamper == 'manifest':
        evidence['provenance']['native_backend']['manifest'] = {'wrong': True}
    else:
        report['results'][0]['arms']['c0']['gps_error_km'] = 0
    persist()
    with pytest.raises(ValueError):
        runner.inspect_publication(args)


@pytest.mark.parametrize('field,replacement', [
    ('native_input', dict(path='/other/native.json', sha256='input')),
    ('search_center', [40, -100]), ('screen_center', [0, 0]),
    ('runtime', dict(python='other')), ('execution_policy', 'other'),
    ('tle_root', '/other/tles'), ('track_config', dict(path='/other/config', sha256='config-sha')),
])
def test_stale_metadata_cannot_mask_mutated_actual_request(tmp_path, field, replacement):
    manifest = protocol(tmp_path)
    report = worker_report(manifest)
    report['plan']['jobs'][0]['request']['job'][field] = replacement
    report['plan_sha256'] = runner.digest(report['plan'])
    with pytest.raises(ValueError, match='Actual requested job differs'):
        runner.validate_report(report, manifest, dict(case='A'), 'candidate')


def full_run_fixture(tmp_path, monkeypatch):
    manifest = protocol(tmp_path)
    manifest.update(output=str(tmp_path / 'staging'), archive_root=str(tmp_path / 'archive'),
                    schedule=[dict(case='A', repetition=0, order=['baseline', 'candidate'])],
                    resource_limits=dict(reserve_gib=20, expected_gib=10, stage_free_gib=10, archive_free_gib=10))
    manifest['selection']['cases'] = ['A']
    path = tmp_path / 'manifest.json'
    runner.write(path, manifest)
    (tmp_path / 'driver').mkdir()
    monkeypatch.setattr(runner, 'ROOT', tmp_path / 'driver')
    monkeypatch.setattr(runner, 'check_bindings', lambda manifest: None)
    monkeypatch.setattr(runner, 'validate_report', lambda report, *args: report['results'][0])
    return manifest, path


def test_full_worker_archives_after_timing_and_public_inspection(tmp_path, monkeypatch):
    manifest, path = full_run_fixture(tmp_path, monkeypatch)
    events = []
    monkeypatch.setattr(runner, 'resources_ready', lambda *args, **kwargs: dict(ready=True))

    def execute(command, **kwargs):
        if 'inspect' in command:
            events.append('inspect')
            destination = Path(command[command.index('--output') + 1])
            runner.write(destination, dict(public_store_validated=True))
        else:
            events.append('worker')
            destination = Path(command[command.index('--output') + 1])
            report = worker_report(manifest, side=destination.name)
            report['results'][0].update(request_path='request', result_sha256='result')
            runner.write(destination / 'report.json', report)
        return SimpleNamespace(returncode=0)

    def archive(*args, **kwargs):
        events.append('archive')

    monkeypatch.setattr(runner.subprocess, 'run', execute)
    monkeypatch.setattr(runner, 'archive_role', archive)
    assert runner.run(path, str(min(runner.os.sched_getaffinity(0)))) == 0
    assert events == ['worker', 'inspect', 'archive', 'worker', 'inspect', 'archive']


def test_low_resources_stop_admission_without_launch_or_deletion(tmp_path, monkeypatch):
    manifest, path = full_run_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, 'resources_ready', lambda *args, **kwargs: dict(ready=False, stage_free_gib=1))
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs: pytest.fail('No worker may launch'))
    with pytest.raises(RuntimeError, match='Resource guard'):
        runner.run(path, str(min(runner.os.sched_getaffinity(0))))
    marker = Path(manifest['output']) / 'resource-stop.json'
    assert runner.read(marker)['status'] == 'admission_stopped'


def test_run_resumes_verified_archive_before_testing_report_existence(tmp_path, monkeypatch):
    import shutil

    manifest, path = full_run_fixture(tmp_path, monkeypatch)
    manifest['schedule'][0]['order'] = ['baseline']
    runner.write(path, manifest)
    folder = Path(manifest['output']) / 'A-r0'
    stage = folder / 'baseline'
    report = worker_report(manifest, side='baseline')
    report['results'][0].update(request_path='request', result_sha256='result')
    runner.write(stage / 'report.json', report)
    receipt = folder / 'baseline-execution.json'
    cpus = str(min(runner.os.sched_getaffinity(0)))
    runner.write(receipt, dict(command=runner.command(manifest, manifest['schedule'][0], 'baseline', stage, cpus)))
    destination = Path(manifest['archive_root']) / 'A-r0/baseline'
    runner.archive_role(stage, destination, receipt,
                        staging_root=Path(manifest['output']), archive_root=Path(manifest['archive_root']))
    parked = stage.with_name('baseline.archive-parked')
    shutil.copytree(destination, parked)
    stage.unlink()

    def inspect(command, **kwargs):
        assert 'inspect' in command, 'An archived worker must never rerun'
        runner.write(command[command.index('--output') + 1], dict(public_store_validated=True))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, 'run', inspect)
    assert runner.run(path, cpus) == 1  # Candidate is deliberately absent in this one-role crash fixture.
    assert stage.is_symlink() and not parked.exists()


def historical_fixture(tmp_path, monkeypatch, *, status='complete'):
    manifest = protocol(tmp_path)
    manifest['historical_baseline_root'] = str(tmp_path / 'original-cohort')
    manifest['schedule'] = [dict(case='A', repetition=0, order=['baseline', 'candidate'])]
    manifest['selection']['cases'] = ['A']
    origin = Path(manifest['historical_baseline_root']) / 'A-r0'
    report_path = origin / 'candidate/report.json'
    report = worker_report(manifest, side='baseline', status=status)
    original_output = str(tmp_path / 'original-stage/A-r0/candidate')
    report['plan']['output'] = original_output
    request = report['plan']['jobs'][0]['request']
    request['job']['output_root'] = str(Path(original_output) / 'A-r0/algo07v5/publication')
    request_path = Path(original_output) / 'A-r0/algo07v5/request.json'
    report['results'][0].update(request_path=str(request_path), result_sha256='original-result')
    report['plan_sha256'] = runner.digest(report['plan'])
    runner.write(report_path, report)
    command = runner.command(manifest, manifest['schedule'][0], 'baseline', original_output, '0')
    execution = dict(command=command, execution_mode='bulk_contended')
    runner.write(origin / 'candidate-execution.json', execution)
    folder = Path(manifest['output']) / 'A-r0'
    folder.mkdir(parents=True)
    calls = []

    def inspect(command, **kwargs):
        assert 'inspect' in command
        calls.append(command)
        runner.write(command[command.index('--output') + 1], dict(public_store_validated=True))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, 'run', inspect)
    return manifest, folder, report_path, execution, calls


def bind_direct_gap_candidate(manifest):
    manifest['roles']['candidate']['initial'] = None
    manifest['roles']['candidate']['direct_gap'] = dict(id='direct-timing-gap-v1')


def test_historical_import_preserves_original_report_plan_and_request_paths(tmp_path, monkeypatch):
    manifest, folder, path, _, calls = historical_fixture(tmp_path, monkeypatch)
    original = path.read_bytes()
    imported = runner.import_historical(manifest, manifest['schedule'][0], folder)
    assert path.read_bytes() == original
    assert imported['plan']['output'].endswith('original-stage/A-r0/candidate')
    assert imported['results'][0]['request_path'].endswith('original-stage/A-r0/candidate/A-r0/algo07v5/request.json')
    assert calls[0][calls[0].index('--report') + 1] == str(path)
    receipt = runner.read(folder / 'baseline-historical-import.json')
    assert receipt['source_report_sha256'] == runner.sha(path) and not receipt['timing_eligible']


@pytest.mark.parametrize('mutation', (
    'none', 'request_policy', 'plan_policy', 'evaluator', 'native', 'request'))
def test_historical_gap_import_accepts_original_null_policies_and_rejects_drift(
        tmp_path, monkeypatch, mutation):
    manifest, folder, path, _, calls = historical_fixture(tmp_path, monkeypatch)
    bind_direct_gap_candidate(manifest)
    original = runner.read(path)
    changed = copy.deepcopy(original)
    if mutation == 'request_policy':
        changed['plan']['jobs'][0]['request']['direct_gap_policy'] = dict(id='direct-timing-gap-v1')
    elif mutation == 'plan_policy':
        changed['plan']['direct_gap_policy'] = dict(id='direct-timing-gap-v1')
    elif mutation == 'evaluator':
        changed['plan']['evaluator']['path'] = '/other/evaluator.py'
    elif mutation == 'native':
        changed['plan']['jobs'][0]['request']['backend_manifest'] = {'native': 'other'}
    elif mutation == 'request':
        changed['plan']['jobs'][0]['request']['job']['search_center'] = [99, 99]
    changed['plan_sha256'] = runner.digest(changed['plan'])
    runner.write(path, changed)
    if mutation == 'none':
        imported = runner.import_historical(manifest, manifest['schedule'][0], folder)
        assert imported['results'][0]['status'] == 'complete'
        assert runner.read(path) == original
        assert len(calls) == 1
    else:
        with pytest.raises(ValueError):
            runner.import_historical(manifest, manifest['schedule'][0], folder)
        assert not calls


def test_historical_missing_report_stays_pending_without_work(tmp_path, monkeypatch):
    manifest = protocol(tmp_path)
    manifest['historical_baseline_root'] = str(tmp_path / 'not-yet-published')
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs: pytest.fail('No numerical or inspection work'))
    assert runner.import_historical(manifest, dict(case='A'), tmp_path) is None


def test_historical_import_rejects_disappeared_or_changed_original(tmp_path, monkeypatch):
    manifest, folder, path, _, _ = historical_fixture(tmp_path, monkeypatch)
    runner.import_historical(manifest, manifest['schedule'][0], folder)
    original = path.read_bytes()
    path.unlink()
    with pytest.raises(ValueError, match='disappeared'):
        runner.import_historical(manifest, manifest['schedule'][0], folder)
    path.write_bytes(original)
    report = runner.read(path)
    report['results'][0]['error'] = 'changed origin'
    runner.write(path, report)
    with pytest.raises(ValueError, match='Historical import binding changed'):
        runner.import_historical(manifest, manifest['schedule'][0], folder)


def test_historical_execution_wrong_case_or_source_rejected(tmp_path, monkeypatch):
    manifest, folder, path, execution, _ = historical_fixture(tmp_path, monkeypatch)
    execution['command'][execution['command'].index('--source-root') + 1] = '/unrelated-source'
    runner.write(path.parent.parent / 'candidate-execution.json', execution)
    with pytest.raises(ValueError, match='Historical execution bindings differ'):
        runner.import_historical(manifest, manifest['schedule'][0], folder)


def test_historical_clock_updates_do_not_rebind_the_execution_command(tmp_path, monkeypatch):
    manifest, folder, path, execution, _ = historical_fixture(tmp_path, monkeypatch)
    runner.import_historical(manifest, manifest['schedule'][0], folder)
    execution['after'] = {'utc': 'archive clock added after import'}
    runner.write(path.parent.parent / 'candidate-execution.json', execution)
    assert runner.import_historical(manifest, manifest['schedule'][0], folder)['results'][0]['status'] == 'complete'


def test_historical_scientific_failure_is_retained_without_inspection(tmp_path, monkeypatch):
    manifest, folder, _, _, calls = historical_fixture(tmp_path, monkeypatch, status='failed')
    report = runner.import_historical(manifest, manifest['schedule'][0], folder)
    assert report['results'][0]['status'] == 'failed' and not calls
    result = runner.aggregate(manifest, {('A', 0): dict(baseline=report, candidate=worker_report(manifest))})
    assert result['statuses']['baseline'] == dict(failed=1)
    assert result['paired_coverage_complete'] and 'timing' not in result


def test_historical_missing_input_is_retained_without_inspection(tmp_path, monkeypatch):
    manifest, folder, path, _, calls = historical_fixture(tmp_path, monkeypatch, status='missing')
    manifest['members'][0].update(availability='missing', input_sha256=None)
    report = runner.read(path)
    report['plan']['jobs'][0].update(availability='missing', request=None)
    report['results'][0].update(availability='missing', input_sha256=None)
    report['plan_sha256'] = runner.digest(report['plan'])
    runner.write(path, report)
    imported = runner.import_historical(manifest, manifest['schedule'][0], folder)
    assert imported['results'][0]['status'] == 'missing' and not calls
    assert runner.read(folder / 'baseline-historical-import.json')['public_work_sha256'] is None


@pytest.mark.parametrize('direct_gap', (False, True))
def test_historical_comparison_never_computes_timing_or_mutates_original_rows(tmp_path, direct_gap):
    manifest = protocol(tmp_path)
    if direct_gap:
        bind_direct_gap_candidate(manifest)
    manifest['historical_baseline_root'] = '/original'
    manifest['schedule'] = [dict(case='A', repetition=0)]
    manifest['selection']['cases'] = ['A']
    left, right = worker_report(manifest, side='baseline'), worker_report(manifest)
    left['results'][0]['process'].update(cpu_seconds='must-never-enter-arithmetic', wall_seconds='same')
    result = runner.aggregate(manifest, {('A', 0): dict(baseline=left, candidate=right)})
    assert 'timing' not in result and 'timing' not in result['pairs'][0]
    assert 'stage_seconds' not in result['pairs'][0]
    assert left['results'][0]['process']['cpu_complete'] is True
    assert left['results'][0]['process']['cpu_seconds'] == 'must-never-enter-arithmetic'


@pytest.mark.parametrize('direct_gap', (False, True))
def test_candidate_full_finishes_while_historical_baseline_is_pending_and_refresh_never_infers(
        tmp_path, monkeypatch, direct_gap):
    manifest, path = full_run_fixture(tmp_path, monkeypatch)
    if direct_gap:
        bind_direct_gap_candidate(manifest)
    manifest['historical_baseline_root'] = str(tmp_path / 'original-pending')
    runner.write(path, manifest)
    events = []
    monkeypatch.setattr(runner, 'resources_ready', lambda *args, **kwargs: dict(ready=True))
    monkeypatch.setattr(runner, 'archive_role', lambda *args, **kwargs: None)

    def execute(command, **kwargs):
        if 'inspect' in command:
            events.append('inspect')
            runner.write(command[command.index('--output') + 1], dict(public_store_validated=True))
        else:
            events.append('candidate-worker')
            destination = Path(command[command.index('--output') + 1])
            assert destination.name == 'candidate'
            report = worker_report(manifest)
            report['results'][0].update(request_path='request', result_sha256='result')
            runner.write(destination / 'report.json', report)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, 'run', execute)
    assert runner.run(path, str(min(runner.os.sched_getaffinity(0)))) == 0
    terminal = runner.read(Path(manifest['output']) / 'terminal.json')
    assert terminal['status'] == 'candidate_complete'
    assert terminal['candidate_coverage_complete'] and not terminal['paired_coverage_complete']
    assert events == ['candidate-worker', 'inspect']
    runner.refresh(path)
    assert events == ['candidate-worker', 'inspect', 'inspect']
    summary = runner.read(Path(manifest['output']) / 'comparison.json')
    assert summary['historical_baseline_pending'] == ['A']
    assert summary['statuses']['baseline'] == dict(absent=1)
    assert 'timing' not in summary and all('timing' not in pair for pair in summary['pairs'])


@pytest.mark.parametrize('direct_gap', (False, True))
def test_refresh_completes_pair_when_original_arrives_without_relaunching_candidate(
        tmp_path, monkeypatch, direct_gap):
    manifest, folder, origin, _, calls = historical_fixture(tmp_path, monkeypatch)
    if direct_gap:
        bind_direct_gap_candidate(manifest)
    manifest['archive_root'] = None
    path = tmp_path / 'manifest.json'
    runner.write(path, manifest)
    driver = tmp_path / 'driver'
    driver.mkdir()
    monkeypatch.setattr(runner, 'ROOT', driver)
    monkeypatch.setattr(runner, 'check_bindings', lambda manifest: None)
    candidate = worker_report(manifest)
    candidate['results'][0].update(request_path='candidate-request', result_sha256='candidate-result')
    stage = folder / 'candidate'
    runner.write(stage / 'report.json', candidate)
    runner.write(folder / 'candidate-execution.json', dict(command=runner.command(
        manifest, manifest['schedule'][0], 'candidate', stage, '0')))
    pending = origin.with_suffix('.pending')
    origin.rename(pending)
    runner.refresh(path)
    assert not runner.read(folder.parent / 'refresh-status.json')['paired_coverage_complete']
    pending.rename(origin)
    runner.refresh(path)
    assert runner.read(folder.parent / 'refresh-status.json')['paired_coverage_complete']
    assert runner.read(folder.parent / 'terminal.json')['status'] == 'complete'
    assert len(calls) == 3 and all('inspect' in command for command in calls)
    comparison = runner.read(folder.parent / 'comparison.json')
    assert 'timing' not in comparison and 'timing' not in comparison['pairs'][0]
    assert set(comparison['pairs'][0]['arms']) == {'c0', 'fitted_c'}


def test_refresh_rejects_wrong_execution_before_archive_recovery(tmp_path, monkeypatch):
    manifest, path = full_run_fixture(tmp_path, monkeypatch)
    manifest['historical_baseline_root'] = str(tmp_path / 'original-pending')
    runner.write(path, manifest)
    folder = Path(manifest['output']) / 'A-r0'
    runner.write(folder / 'candidate-execution.json', dict(command=['wrong'], archive=dict(verified=True)))
    monkeypatch.setattr(runner, 'archive_role', lambda *args, **kwargs: pytest.fail('No recovery before command validation'))
    with pytest.raises(ValueError, match='execution command differs'):
        runner.refresh(path)
