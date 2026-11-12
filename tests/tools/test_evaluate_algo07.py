"""Evaluation orchestration tests use tiny inputs and never launch radio inference."""

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOL = Path(__file__).resolve().parents[2] / 'tools/evaluate_algo07.py'
spec = importlib.util.spec_from_file_location('evaluate_algo07', TOOL)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'inputs').mkdir()
    config = snapshot / 'inputs/config.json'
    config.write_text('{}')
    members = []
    for index, case in enumerate((*evaluation.QUICK, 'DS26-0172')):
        row = dict(dataset_label=case, availability='no_native_run', recording_id='recording')
        if index < 3:
            folder = snapshot / 'inputs' / case
            folder.mkdir()
            (folder / 'tle/archive/space-track').mkdir(parents=True)
            (folder / 'tle/archive/space-track/causal.tle').write_text('causal')
            (folder / 'native.json').write_text('{}')
            row.update(availability='available', session_id=f'session-{index}',
                       input_sha256=evaluation.file_digest(folder / 'native.json'),
                       causal_snapshots={'causal.tle': evaluation.file_digest(
                           folder / 'tle/archive/space-track/causal.tle').removeprefix('sha256:')})
        members.append(row)
    evaluation.write(snapshot / 'inventory.json', dict(
        members=members, config_sha256=evaluation.file_digest(config).removeprefix('sha256:')))
    evaluation.write(snapshot / 'template-request.json', dict(
        schema_version=1, execution_policy='validation-all-work',
        evaluation_reference=dict(latitude_deg=37, longitude_deg=-122),
        search_center=[37.906, -122.545], screen_center=[37.5, -122], runtime={'python': 'test'}))
    source = tmp_path / 'source'
    (source / 'leo').mkdir(parents=True)
    (source / 'leo/__init__.py').write_text('')
    return snapshot, source, tmp_path / 'output'


def plan(frozen, *extra):
    snapshot, source, output = frozen
    result = evaluation.main(['plan', '--version', 'algo07v3', '--snapshot', str(snapshot),
                              '--source-root', str(source), '--output', str(output), *extra])
    assert result == 0
    saved = evaluation.read(output / 'plan.json')
    saved.pop('plan_sha256')
    return saved


def test_full_members_missing_source_and_no_gps_in_request(frozen):
    result = plan(frozen, '--profile', 'full')
    assert len(result['members']) == len(result['jobs']) == 4
    assert result['missing'] == ['DS26-0172']
    assert result['jobs'][-1]['status'] == 'missing'
    assert result['jobs'][-1]['request'] is None
    assert result['source']['root'] == str(frozen[1])
    for row in result['jobs'][:-1]:
        request = row['request']
        assert request['evaluation_reference'] is None
        assert request['identity']['run_id'].startswith('algo07v3-')
        assert row['case'] in request['native_input']['path']
        assert request['native_input']['sha256'] == row['input_sha256']
        assert row['reference'] == dict(latitude_deg=37, longitude_deg=-122)
    assert result['inference_requested'] is False
    assert not (frozen[2] / 'report.json').exists()


def test_quick_defaults_and_explicit_missing_override(frozen):
    result = plan(frozen)
    assert result['selected'] == list(evaluation.QUICK)
    assert len(result['members']) == 4
    assert [r['status'] for r in result['jobs']] == ['planned'] * 3
    snapshot, source, output = frozen
    assert evaluation.main(['--version', 'algo07v3', '--snapshot', str(snapshot),
                            '--source-root', str(source), '--output', str(output / 'override'),
                            '--cases', 'DS26-0172']) == 0
    override = evaluation.read(output / 'override/plan.json')
    assert override['jobs'][0]['status'] == 'missing'


def test_quick_supports_repeated_subset_without_full_campaign(frozen):
    result = plan(frozen, '--repeats', '5', '--cases', 'DS26-0002')
    assert len(result['jobs']) == 5
    assert {j['repetition'] for j in result['jobs']} == set(range(5))
    assert len({j['request']['identity']['run_id'] for j in result['jobs']}) == 5


def test_inventory_mutation_fails_before_launch(frozen, monkeypatch):
    result = plan(frozen, '--cases', 'DS26-0002')
    (frozen[0] / 'inventory.json').write_text('{}')
    def forbidden(*args, **kwargs):
        pytest.fail('Mutated inventory must never launch a worker')
    monkeypatch.setattr(evaluation, 'supervise', forbidden)
    report = evaluation.run_plan(result, sys.executable)
    assert report['statuses'] == {'failed': 1}
    assert 'inventory changed' in report['results'][0]['error']


def test_v4_plan_is_explicitly_unbound_without_backend(frozen):
    snapshot, source, output = frozen
    assert evaluation.main(['plan', '--snapshot', str(snapshot), '--source-root', str(source),
                            '--output', str(output)]) == 0
    result = evaluation.read(output / 'plan.json')
    assert result['version'] == 'algo07v4'
    assert result['backend_bound'] is False
    with pytest.raises(ValueError, match='requires --native-manifest'):
        evaluation.run_plan(result, sys.executable)


def test_v5_plan_is_opt_in_and_requires_backend_before_run(frozen):
    snapshot, source, output = frozen
    assert evaluation.main(['plan', '--version', 'algo07v5', '--snapshot', str(snapshot),
        '--source-root', str(source), '--output', str(output)]) == 0
    result = evaluation.read(output / 'plan.json')
    assert result['version'] == 'algo07v5'
    assert result['module'] == 'leo.cli.algo07v5'
    assert result['backend_bound'] is False
    assert evaluation.VERSIONS['algo07v5'][1:] == (
        'leo.storage.localization_v5', 'LocalizationV5Store')
    with pytest.raises(ValueError, match='Running v5 requires --native-manifest'):
        evaluation.run_plan(result, sys.executable)


def test_v5_bound_plan_wraps_requests_and_run_supplies_manifest(frozen, monkeypatch):
    snapshot, source, output = frozen
    native = snapshot / 'manifest.json'
    evaluation.write(native, {'algorithm': 'algo07v4-native-v1'})
    imports, wrapped = [], []

    def wrap(request, manifest):
        wrapped.append(copy.deepcopy(request))
        return dict(job=request, backend_manifest=manifest,
                    initial_control_policy='winner-arm-phase0-fit-v1')

    def owned(module, binding):
        imports.append(module)
        assert binding['root'] == str(source)
        return SimpleNamespace(make_request=wrap)

    monkeypatch.setattr(evaluation, 'owned_import', owned)
    assert evaluation.main(['plan', '--version', 'algo07v5', '--snapshot', str(snapshot),
        '--source-root', str(source), '--output', str(output), '--native-manifest', str(native),
        '--cases', 'DS26-0002']) == 0
    result = evaluation.read(output / 'plan.json')
    assert imports == ['leo.operations.localization_v5_job']
    assert len(wrapped) == 1 and wrapped[0]['evaluation_reference'] is None
    assert result['backend_bound'] is True

    def supervise(command, log_path, timeout, environment):
        assert command[command.index('-m') + 1] == 'leo.cli.algo07v5'
        manifest_path = Path(command[command.index('--native-manifest') + 1])
        assert evaluation.read(manifest_path) == result['backend_manifest']
        Path(log_path).write_text('{"status":"exited","worker":{"status":"failed"}}\n')
        return dict(status='exited', returncode=1)

    monkeypatch.setattr(evaluation, 'supervise', supervise)
    report = evaluation.run_plan(result, sys.executable)
    assert report['statuses'] == {'failed': 1}
    assert '--native-manifest' in report['results'][0]['command']


@pytest.mark.parametrize('profile', ['quick', 'full'])
@pytest.mark.parametrize('action', ['plan', 'run'])
def test_explicit_v5_training_policy_binds_plan_and_requests(frozen, monkeypatch, profile, action):
    from leo.contracts import localization_v5

    snapshot, source, output = frozen
    manifest = snapshot / 'manifest.json'
    evaluation.write(manifest, {'synthetic': 'backend'})
    calls = []

    def wrap(request, manifest, *, annotation_training_policy):
        calls.append(annotation_training_policy)
        return dict(job=request, backend_manifest=manifest, schema_version=2,
                    annotation_training_policy=localization_v5.annotation_training_policy())

    def owned(module, binding):
        assert binding['root'] == str(source)
        return (localization_v5 if module == 'leo.contracts.localization_v5'
                else SimpleNamespace(make_request=wrap))

    monkeypatch.setattr(evaluation, 'owned_import', owned)
    if action == 'run':
        def run(plan, python):
            assert plan['annotation_training_policy'] == (
                localization_v5.annotation_training_policy())
            return dict(statuses={'complete': 3}, results=[dict(status='complete')])
        monkeypatch.setattr(evaluation, 'run_plan', run)
    assert evaluation.main([action, '--version', 'algo07v5', '--profile', profile,
        '--snapshot', str(snapshot), '--source-root', str(source), '--output', str(output),
        '--native-manifest', str(manifest), '--annotation-training-policy',
        localization_v5.ANNOTATION_TRAINING_POLICY]) == 0
    plan = evaluation.read(output / 'plan.json')
    assert plan['annotation_training_policy'] == localization_v5.annotation_training_policy()
    assert len(plan['jobs']) == (3 if profile == 'quick' else 4)
    assert calls == [localization_v5.ANNOTATION_TRAINING_POLICY] * 3
    for row in plan['jobs'][:3]:
        assert row['request']['annotation_training_policy'] == plan['annotation_training_policy']


@pytest.mark.parametrize('version', ['algo07v3', 'algo07v4'])
def test_training_policy_rejected_for_other_versions_before_reading_inputs(tmp_path, version):
    assert evaluation.main(['plan', '--version', version, '--snapshot', str(tmp_path / 'absent'),
        '--output', str(tmp_path / 'output'), '--annotation-training-policy',
        'lbfgsb-full5-625-v1']) == 1
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('change', ['duplicate', 'missing', 'changed'])
def test_nested_archive_mutation_never_launches_inference(frozen, monkeypatch, change):
    result = plan(frozen, '--cases', 'DS26-0002')
    root = frozen[0] / 'inputs/DS26-0002/tle'
    source = root / 'archive/space-track/causal.tle'
    if change == 'duplicate':
        (root / 'causal.tle').write_bytes(source.read_bytes())
    elif change == 'missing':
        source.unlink()
    else:
        source.write_text('different orbit')

    def forbidden(*args, **kwargs):
        pytest.fail('Changed archive must never launch inference')

    monkeypatch.setattr(evaluation, 'supervise', forbidden)
    report = evaluation.run_plan(result, sys.executable)
    assert report['statuses'] == {'failed': 1}
    assert 'Frozen causal TLE' in report['results'][0]['error']


def test_invalid_members_output_reuse_and_version(frozen):
    snapshot, source, output = frozen
    base = ['plan', '--snapshot', str(snapshot), '--source-root', str(source),
            '--output', str(output)]
    assert evaluation.main([*base, '--cases', 'DS26-9999']) == 1
    assert evaluation.main([*base, '--profile', 'full', '--cases', 'DS26-0002']) == 1
    assert evaluation.main([*base, '--module', 'leo.cli.algo07v3']) == 1
    plan(frozen)
    assert evaluation.main(base) == 1
    with pytest.raises(ValueError, match='QNAP'):
        evaluation.local_output('/mnt/qnap01/evaluation-must-not-exist')
    assert evaluation.local_output('/tmp/evaluation-local') == Path('/tmp/evaluation-local')


@pytest.mark.parametrize('status,returncode,expected', [
    ('exited', 2, 'failed'), ('timed_out', 124, 'timed_out')])
def test_failure_and_timeout_are_counted_alongside_missing(frozen, monkeypatch,
                                                         status, returncode, expected):
    result = plan(frozen, '--profile', 'full')
    def fake_supervise(command, log_path, timeout, environment):
        Path(log_path).write_text(json.dumps(dict(status=status, returncode=returncode,
                                                 worker=dict(status='failed'))) + '\n')
        work = Path(command[command.index('--work-dir') + 1])
        work.mkdir()
        (work / 'worker.log').write_text('{"stage":"test-stage"}\n')
        return dict(status=status, returncode=returncode, wall_seconds=1,
                    cpu_seconds=.1, cpu_complete=True)
    monkeypatch.setattr(evaluation, 'supervise', fake_supervise)
    report = evaluation.run_plan(result, sys.executable)
    assert report['statuses'] == {expected: 3, 'missing': 1}
    assert report['results'][0]['stage_events'] == [dict(stage='test-stage')]
    assert report['results'][0]['supervisor']['worker']['status'] == 'failed'
    assert not any('arms' in r for r in report['results'])
    assert evaluation.read(frozen[2] / 'report.json')['statuses'] == report['statuses']


def synthetic_report():
    jobs = [dict(case=f'DS26-{i:04}', repetition=0) for i in range(1, 6)]
    result = dict(plan=dict(inventory_sha256='inventory', selected=[j['case'] for j in jobs],
                            config_sha256='config', timeout_seconds=20,
                            source=dict(root='baseline', sha256='source'), jobs=jobs), results=[])
    for i, gps in enumerate((1, 3), start=1):
        arm = dict(gps_error_km=gps, residual_rms_hz=10 * i, frequency_score=100 * i,
                   associated_points=2, owners={'a': 1, 'b': 2})
        result['results'].append(dict(case=f'DS26-{i:04}', repetition=0, status='complete',
                                      input_sha256='native', tle_sha256='tle', reference='gps',
                                      workload_sha256='same-work',
                                      arms={a: copy.deepcopy(arm) for a in evaluation.ARMS},
                                      process=dict(cpu_complete=True, wall_seconds=10 * i,
                                                   cpu_seconds=5 * i)))
    result['results'].extend([dict(case='DS26-0003', repetition=0, status='failed'),
                              dict(case='DS26-0004', repetition=0, status='missing')])
    return result


def test_summary_arithmetic_and_rejected_work_never_becomes_speedup():
    left = synthetic_report()
    right = copy.deepcopy(left)
    right['plan']['source']['root'] = 'candidate'
    right['results'][2]['status'] = 'timed_out'
    for row, gps in zip(right['results'][:2], (2, 1), strict=True):
        row['process'].update(wall_seconds=5, cpu_seconds=3)
        for arm in row['arms'].values():
            arm.update(gps_error_km=gps, residual_rms_hz=1, frequency_score=20,
                       owners={'a': 7, 'c': 8})
    compared = evaluation.compare(left, right)
    gps = compared['arms']['c0']['gps_error_km']
    assert gps['baseline']['median'] == 2
    assert gps['candidate']['median'] == 1.5
    assert gps['delta']['median'] == -.5
    assert gps['delta']['p90'] == pytest.approx(.7)
    assert gps['delta']['p95'] == pytest.approx(.85)
    assert gps['delta']['max'] == 1
    assert compared['pairs'][0]['arms']['c0']['ownership_changes'] == 3
    assert compared['statuses']['candidate'] == dict(complete=2, timed_out=1, missing=1, absent=1)
    assert compared['timing']['wall_seconds']['delta']['median'] == -10
    assert compared['timing']['wall_seconds']['delta']['count'] == 2
    assert compared['timing']['wall_seconds']['speedup']['median'] == 3
    assert compared['timing']['wall_seconds']['aggregate']['speedup'] == 3
    assert compared['timing']['wall_seconds']['aggregate']['reduction_percent'] == pytest.approx(
        100 * 2 / 3)
    right['results'][0]['process']['cpu_complete'] = False
    assert evaluation.compare(left, right)['timing']['cpu_seconds']['delta']['count'] == 1
    right['results'][0]['workload_sha256'] = 'different-search-budget'
    with pytest.raises(ValueError, match='binding differs'):
        evaluation.compare(left, right)


def test_projection_keeps_both_arms_and_frequency_separate():
    evidence = dict(presentation=dict(arms={
        a: dict(endpoint_latlon=[0, 1], associated_points=1, residual_rms_hz=10)
        for a in evaluation.ARMS}), selected=dict(
            arms={a: dict(negative_twice_elbo=30) for a in evaluation.ARMS},
            owners={a: {'x': 123} for a in evaluation.ARMS}))
    result = evaluation.project(evidence, dict(latitude_deg=0, longitude_deg=0))
    assert set(result) == set(evaluation.ARMS)
    assert result['c0']['gps_error_km'] == pytest.approx(111.19508, rel=1e-6)
    assert result['c0']['frequency_score'] == 30
    assert evidence['presentation']['arms']['c0'].get('gps_error_km') is None


@pytest.mark.parametrize('identity_matches', [True, False])
def test_completed_jobs_load_public_store_and_check_identity(frozen, monkeypatch, identity_matches):
    result = plan(frozen, '--cases', 'DS26-0002')
    request = result['jobs'][0]['request']
    calls = []
    class Store:
        def __init__(self, root):
            assert root == request['output_root']
        def load(self, run_id):
            calls.append(run_id)
            identity = copy.deepcopy(request['identity'])
            if not identity_matches:
                identity['run_id'] = 'wrong-version-run'
            return dict(receipt=dict(result_sha256='result'), evidence=dict(
                identity=identity,
                presentation=dict(arms={a: dict(endpoint_latlon=[37, -122],
                                                associated_points=1, residual_rms_hz=10)
                                        for a in evaluation.ARMS}),
                selected=dict(arms={a: dict(negative_twice_elbo=30) for a in evaluation.ARMS},
                              owners={a: {'x': 123} for a in evaluation.ARMS})))
    def complete(command, log_path, timeout, environment):
        Path(log_path).write_text('{"status":"exited","worker":{"status":"complete"}}\n')
        return dict(returncode=0, status='exited', wall_seconds=1,
                    cpu_seconds=.1, cpu_complete=True)
    monkeypatch.setattr(evaluation, 'supervise', complete)
    monkeypatch.setattr(evaluation, 'owned_import',
                        lambda *a: SimpleNamespace(LocalizationV3Store=Store))
    report = evaluation.run_plan(result, sys.executable)
    assert calls == [request['identity']['run_id']]
    if identity_matches:
        assert report['results'][0]['arms']['c0']['gps_error_km'] == 0
        assert report['results'][0]['status'] == 'complete'
    else:
        assert report['results'][0]['status'] == 'failed'
        assert 'identity differs' in report['results'][0]['error']


def test_owned_cpu_includes_waited_child_and_real_failure(tmp_path):
    spin = 'import time\nt=time.process_time()\nwhile time.process_time()-t < .15: pass'
    program = ('import subprocess,sys\nsubprocess.run([sys.executable,"-c",'
               + repr(spin) + '],check=True)\nraise SystemExit(7)')
    result = evaluation.supervise([sys.executable, '-c', program], tmp_path / 'stdout', 2,
                                 dict(os.environ))
    assert result['returncode'] == 7
    assert result['cpu_seconds'] >= .15
    assert result['cpu_complete'] is True
    assert result['status'] == 'exited'


def test_outer_watchdog_kills_descendant_in_new_session(tmp_path):
    program = ('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c",'
               '"import time;time.sleep(60)"],start_new_session=True)\n'
               'print(p.pid,flush=True)\ntime.sleep(60)')
    log = tmp_path / 'stdout'
    result = evaluation.supervise([sys.executable, '-c', program], log, .01, dict(os.environ))
    assert result['status'] == 'timed_out'
    assert result['cpu_complete'] is False
    assert result['wall_seconds'] < 8
    pid = int(log.read_text().strip())
    stat = Path(f'/proc/{pid}/stat')
    assert not stat.exists() or stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z'


def test_real_cli_help():
    result = subprocess.run([sys.executable, str(TOOL), '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert '{plan,run,compare}' in result.stdout
    assert 'never inference' in result.stdout
