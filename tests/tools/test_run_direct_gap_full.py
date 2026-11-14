"""Coordinator contract tests with no numerical worker or systemd launch."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'tools' / 'run_direct_gap_full.py'
SPEC = importlib.util.spec_from_file_location('direct_gap_full_tests', SOURCE)
coordinator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coordinator)


def fixture(tmp_path):
    runner = tmp_path / 'runner.py'
    collector = tmp_path / 'collector.py'
    runner.write_text('frozen runner\n')
    collector.write_text('frozen collector\n')
    manifests = []
    for cohort in ('DS26', 'DS29'):
        case = cohort + '-0001'
        historical = tmp_path / (cohort + '-historical')
        historical.mkdir()
        (historical / 'protocol.json').write_text(json.dumps({'cases': [case]}))
        manifest = dict(profile='full', repeats=1,
                        fast_flags={'--recovery-target-limit': '0'},
                        roles={'baseline': {'initial': None},
                               'candidate': {'initial': None,
                                             'direct_gap': {'id': 'direct-timing-gap-v1'}}},
                        historical_baseline_root=str(historical),
                        members=[{'dataset_label': case}],
                        selection={'cases': [case]},
                        schedule=[{'case': case, 'repetition': 0}],
                        output=str(tmp_path / (cohort + '-staging')), archive_root=None)
        path = tmp_path / (cohort + '.json')
        path.write_text(json.dumps(manifest))
        manifests.append(path)
    output = tmp_path / 'coord'
    argv = ['--runner', str(runner), '--collector', str(collector),
            '--manifest', str(manifests[0]), '--manifest', str(manifests[1]),
            '--output', str(output)]
    return runner, collector, manifests, output, argv


def fake_process(monkeypatch, output, *, pending=False, service='inactive', fail_at=None,
                 scientific_failures=None):
    calls = []
    scientific_failures = scientific_failures or []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[0] == 'systemctl':
            assert argv == ['systemctl', '--user', 'show',
                            'leo-ds26-ds29-evaluation-20261113.service',
                            '--property=LoadState,ActiveState,SubState,Result']
            assert kwargs['timeout'] == 15
            return SimpleNamespace(
                stdout=f'LoadState=loaded\nActiveState={service}\nSubState=running\nResult=success\n',
                stderr='', returncode=3 if service == 'mystery' else 0)
        cohort = 'DS26' if 'DS26' in ' '.join(argv) else 'DS29'
        phase = 'run' if 'run' in argv else 'refresh' if 'refresh' in argv else 'collect'
        if fail_at == (cohort, phase):
            return SimpleNamespace(returncode=17)
        if phase == 'run':
            manifest = json.loads(Path(argv[argv.index('--manifest') + 1]).read_text())
            staging = Path(manifest['output'])
            staging.mkdir()
            (staging / 'terminal.json').write_text(json.dumps(
                {'candidate_coverage_complete': True,
                 'paired_coverage_complete': not pending, 'failures': scientific_failures}))
        if phase == 'collect':
            report = Path(argv[argv.index('--output') + 1])
            report.mkdir(parents=True, exist_ok=True)
            (report / 'summary.json').write_text(json.dumps(
                {'candidate_coverage_complete': True,
                 'paired_coverage_complete': not pending,
                 'expected_count': 1,
                 'statuses': {'candidate': {'complete': 1}, 'baseline': {'pending': int(pending)}},
                 'scientific_failures': scientific_failures}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(coordinator.subprocess, 'run', run)
    return calls


def actions(calls):
    return [next((action for action in ('run', 'refresh') if action in argv), 'collect')
            for argv in calls if argv[0] != 'systemctl']


def test_sequential_candidates_then_reports_and_scientific_failure_retained(tmp_path, monkeypatch):
    _, _, _, output, argv = fixture(tmp_path)
    failure = {'case': 'DS26-0001', 'side': 'candidate', 'status': 'failed'}
    calls = fake_process(monkeypatch, output, scientific_failures=[failure])
    assert coordinator.main(argv) == 0
    assert actions(calls) == ['run', 'refresh', 'collect', 'run', 'refresh', 'collect']
    status = json.loads((output / 'status.json').read_text())
    assert status['status'] == 'complete'
    assert status['coverage']['DS26']['scientific_failures'] == [failure]
    assert status['coverage']['DS29']['paired_coverage_complete']
    assert all('returncode' in row for row in map(json.loads,
               (output / 'commands.jsonl').read_text().splitlines()) if 'finished_utc' in row)
    assert coordinator.main(argv) == 0
    assert actions(calls) == ['run', 'refresh', 'collect', 'run', 'refresh', 'collect']


def test_waits_for_historical_controls_without_rerunning_candidates(tmp_path, monkeypatch):
    _, _, _, output, argv = fixture(tmp_path)
    calls = fake_process(monkeypatch, output, pending=True, service='active')
    intervals = []

    def sleep(seconds):
        intervals.append(seconds)
        if len(intervals) == 1:
            original_run = coordinator.subprocess.run

            def completed(args, **kwargs):
                if '--output' in args:
                    result = original_run(args, **kwargs)
                    path = Path(args[args.index('--output') + 1]) / 'summary.json'
                    report = json.loads(path.read_text())
                    report['paired_coverage_complete'] = True
                    path.write_text(json.dumps(report))
                    return result
                return original_run(args, **kwargs)

            monkeypatch.setattr(coordinator.subprocess, 'run', completed)

    monkeypatch.setattr(coordinator.time, 'sleep', sleep)
    assert coordinator.main(argv) == 0
    assert intervals == [300]
    assert actions(calls).count('run') == 2
    assert actions(calls).count('refresh') == 6
    assert json.loads((output / 'status.json').read_text())['status'] == 'complete'


@pytest.mark.parametrize('service', ['inactive', 'failed', 'mystery'])
def test_pending_controls_do_not_claim_completion(tmp_path, monkeypatch, service):
    _, _, _, output, argv = fixture(tmp_path)
    calls = fake_process(monkeypatch, output, pending=True, service=service)
    if service == 'mystery':
        def stop_wait(seconds):
            assert seconds >= 300
            raise KeyboardInterrupt
        monkeypatch.setattr(coordinator.time, 'sleep', stop_wait)
        with pytest.raises(KeyboardInterrupt):
            coordinator.main(argv)
        assert json.loads((output / 'status.json').read_text())['status'] == 'waiting_historical'
    else:
        assert coordinator.main(argv) == 1
        assert json.loads((output / 'status.json').read_text())['status'] == 'incomplete'
    assert actions(calls).count('run') == 2


def test_nonzero_command_stops_without_retry(tmp_path, monkeypatch):
    _, _, _, output, argv = fixture(tmp_path)
    calls = fake_process(monkeypatch, output, fail_at=('DS26', 'run'))
    with pytest.raises(RuntimeError, match='returned 17'):
        coordinator.main(argv)
    assert actions(calls) == ['run']
    status = json.loads((output / 'status.json').read_text())
    assert status['status'] == 'failed'
    assert status['last_command']['returncode'] == 17
    assert coordinator.main(argv) == 1
    assert actions(calls) == ['run']


@pytest.mark.parametrize('phase', ['refresh', 'collect'])
def test_nonzero_refresh_or_report_never_retries(tmp_path, monkeypatch, phase):
    _, _, _, output, argv = fixture(tmp_path)
    calls = fake_process(monkeypatch, output, fail_at=('DS26', phase))
    with pytest.raises(RuntimeError, match='returned 17'):
        coordinator.main(argv)
    assert actions(calls) == (['run', 'refresh'] if phase == 'refresh'
                              else ['run', 'refresh', 'collect'])
    assert json.loads((output / 'status.json').read_text())['status'] == 'failed'
    assert coordinator.main(argv) == 1
    assert actions(calls).count(phase) == 1


def test_frozen_drift_stops_before_next_command(tmp_path, monkeypatch):
    runner, _, _, output, argv = fixture(tmp_path)
    calls = fake_process(monkeypatch, output, pending=True, service='active')

    def drift(seconds):
        runner.write_text('changed runner\n')

    monkeypatch.setattr(coordinator.time, 'sleep', drift)
    with pytest.raises(ValueError, match='Frozen input changed'):
        coordinator.main(argv)
    assert actions(calls) == ['run', 'refresh', 'collect', 'run', 'refresh', 'collect',
                              'refresh', 'collect', 'refresh', 'collect']
    assert json.loads((output / 'status.json').read_text())['status'] == 'failed'


def test_invalid_scope_or_qnap_output_never_starts_worker(tmp_path, monkeypatch):
    _, _, manifests, _, argv = fixture(tmp_path)
    calls = fake_process(monkeypatch, tmp_path)
    wrong = json.loads(manifests[1].read_text())
    wrong['members'] = [{'dataset_label': 'DS29-0002'}]
    manifests[1].write_text(json.dumps(wrong))
    with pytest.raises(ValueError, match='cover its frozen inventory'):
        coordinator.main(argv)
    assert calls == []
    wrong['members'] = [{'dataset_label': 'DS29-0001'}]
    wrong['output'] = '/mnt/qnap01/forbidden-output'
    manifests[1].write_text(json.dumps(wrong))
    with pytest.raises(ValueError, match='QNAP'):
        coordinator.main(argv)
    assert calls == []


def test_user_unit_not_found_is_stopped_and_manager_timeout_is_unknown(monkeypatch):
    def not_found(argv, **kwargs):
        return SimpleNamespace(stdout='LoadState=not-found\nActiveState=inactive\n',
                               stderr='', returncode=0)

    monkeypatch.setattr(coordinator.subprocess, 'run', not_found)
    assert coordinator.service_state('unit.service')['state'] == 'stopped'

    def timed_out(argv, **kwargs):
        raise coordinator.subprocess.TimeoutExpired(argv, 15)

    monkeypatch.setattr(coordinator.subprocess, 'run', timed_out)
    assert coordinator.service_state('unit.service')['state'] == 'unknown'
