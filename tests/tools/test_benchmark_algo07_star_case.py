import fcntl
import hashlib
import json
from types import SimpleNamespace

import benchmark_algo07_star_case as bench
import pytest


def test_only_coordinator_window_changes():
    config = dict(python='/python', archive_view='/view', archive_manifest='/archive',
                  runtimes='/runtimes', manifest='/manifest', reference='/reference',
                  candidate='/candidate', candidate_terminal_read_reuse=True)
    from pathlib import Path
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
