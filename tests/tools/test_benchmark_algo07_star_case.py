import fcntl
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import benchmark_algo07_star_case as bench
import pytest


def test_only_coordinator_window_changes():
    config = dict(python='/python', archive_view='/view', archive_manifest='/archive',
                  runtimes='/runtimes', manifest='/manifest', reference='/reference',
                  candidate='/candidate', candidate_terminal_read_reuse=True)
    for side in bench.SIDES:
        original = bench.replay_command(config, side, Path('/execution.json'))
        timed = bench.fresh_command(config, side, Path('/execution.json'))
        changed = [(a, b) for a, b in zip(original, timed, strict=True) if a != b]
        assert changed == [('1500', '1800')]
        assert timed[:4] == ['timeout', '--kill-after=15', '1785', '/python']


@pytest.mark.parametrize('state', ['complete', 'running', 'failed'])
def test_timing_rejects_reused_or_active_stages(monkeypatch, state):
    monkeypatch.setattr(bench, 'stage_status', lambda _: [dict(algorithm='ALGO02', state=state)])
    with pytest.raises(ValueError, match='fresh'):
        bench.require_fresh(dict(reference='/reference'), 'reference')


@pytest.mark.parametrize('failure',
                         [None, 'checkpoint', 'inference', 'publication', 'grid', 'pins'])
def test_only_complete_paths_get_timing_and_never_get_parity(tmp_path, monkeypatch, failure):
    case = tmp_path / 'case'
    case.mkdir()
    (case / bench.CONFIG).write_text('{}')
    config = dict(candidate_terminal_read_reuse=True, reference=str(tmp_path / 'reference'),
                  candidate=str(tmp_path / 'candidate'), run_id='native')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}')
    plan = tmp_path / 'publication-plan.json'
    plan.write_text(json.dumps(dict(driver_code='pass',
                                   driver_sha256=hashlib.sha256(b'pass').hexdigest(),
                                   manifest_sha256=bench.digest(manifest),
                                   renderer='/renderer', python='/python')))
    args = SimpleNamespace(case=case, side='candidate', output=tmp_path / 'trial',
                           publication_plan=plan, presentation_manifest=manifest)
    loads = []

    def load(_):
        loads.append(True)
        return dict(config, changed=True) if failure == 'pins' and len(loads) > 1 else config

    monkeypatch.setattr(bench, 'load', load)
    monkeypatch.setattr(bench, 'verify', lambda _: dict(verified=True))
    monkeypatch.setattr(bench, 'stage_status',
                        lambda _: [dict(algorithm='ALGO02', state='not_started')])
    monkeypatch.setattr(bench, 'fresh_command', lambda *args: ['inference'])
    calls = []

    def execute(command, environment, output):
        calls.append(command)
        if command == ['inference']:
            (args.output / 'inference.json').write_text(json.dumps(dict(
                state='checkpointed' if failure == 'checkpoint' else 'scientific_complete')))
            return dict(returncode=int(failure == 'inference'), wall_seconds=1)
        (args.output / 'publication-process.log').write_text(json.dumps(dict(
            artifacts=8, grid_complete=failure != 'grid', grid_evaluated=179, grid_planned=179)))
        return dict(returncode=int(failure == 'publication'), wall_seconds=1)

    monkeypatch.setattr(bench, 'execute', execute)
    assert bench.run(args) == int(failure is not None)
    summary = json.loads((args.output / 'summary.json').read_text())
    assert not summary['scientific_parity_verified']
    assert not summary['native_glrt_included']
    assert not summary['production_queue_included']
    if failure:
        assert summary['completed_path_seconds'] is None
        assert summary['state'] == 'incomplete'
    else:
        assert summary['completed_path_seconds'] >= 0
        assert summary['state'] == 'completed_unqualified'
    assert len(calls) == (1 if failure in ('inference', 'checkpoint') else 2)


def test_changed_publication_driver_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='hash'):
        bench.publication_command({}, 'reference',
                                  dict(driver_code='changed', driver_sha256='wrong'), tmp_path)


def test_existing_cli_lock_prevents_parallel_timing(tmp_path):
    with (tmp_path / 'verify-reference.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            bench.run(SimpleNamespace(case=tmp_path, side='reference'))


def test_remaining_bound_preserves_python_and_scientific_arguments():
    command = ['timeout', '--kill-after=15', '1785', '/python', '--maximum-seconds', '1800']
    assert bench.bound_outer_timeout(command, 900) == [
        'timeout', '--kill-after=15', '900', '/python', '--maximum-seconds', '1800']
    assert command[2] == '1785'
    assert bench.bound_outer_timeout(command, 1900) == command
    with pytest.raises(ValueError):
        bench.bound_outer_timeout(command, 0)


@pytest.mark.parametrize('failure', [None, 'process', 'no_progress', 'active', 'wrong_next'])
def test_only_verified_forward_checkpoints_resume(tmp_path, monkeypatch, failure):
    config = dict(reference=str(tmp_path / 'reference'))
    commands, states = [], []

    def fresh(config, side, output):
        return ['timeout', '--kill-after=15', '1785', '/python', str(output)]

    def execute(command, environment, output):
        commands.append(command)
        assert command[3] == '/python'
        complete = len(commands) == 2
        value = dict(state='scientific_complete' if complete else 'checkpointed',
                     next_stage='ALGO04' if failure == 'wrong_next' else 'ALGO03')
        Path(command[-1]).write_text(json.dumps(value))
        if complete:
            states[:] = [dict(algorithm=a, state='complete') for a in bench.ALGORITHMS]
        elif failure == 'no_progress':
            states[:] = [dict(algorithm='ALGO02', state='not_started')]
        else:
            states[:] = [dict(algorithm='ALGO02', state='complete'),
                         dict(algorithm='ALGO03', state=(
                             'running' if failure == 'active' else 'not_started'))]
        return dict(returncode=int(failure == 'process'), wall_seconds=1)

    monkeypatch.setattr(bench, 'fresh_command', fresh)
    monkeypatch.setattr(bench, 'execute', execute)
    monkeypatch.setattr(bench, 'stage_status', lambda _: states)
    deadline = bench.time.monotonic() + 1800
    if failure:
        with pytest.raises(ValueError):
            bench.checkpointed_inference(config, 'reference', tmp_path, {}, deadline)
        assert len(commands) == 1
    else:
        result, receipt = bench.checkpointed_inference(
            config, 'reference', tmp_path, {}, deadline)
        assert len(commands) == len(result['attempts']) == 2
        assert json.loads(receipt.read_text())['state'] == 'scientific_complete'


def test_expired_total_deadline_never_launches_work(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, 'execute', lambda *args: pytest.fail('Must not launch'))
    with pytest.raises(ValueError, match='deadline'):
        bench.checkpointed_inference({}, 'reference', tmp_path, {}, bench.time.monotonic() - 1)
