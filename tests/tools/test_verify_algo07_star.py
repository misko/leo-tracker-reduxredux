import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import verify_algo07_star as cli


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def native_pair(tmp_path):
    config = dict(run_id='fast-example')
    for side in cli.SIDES:
        root = tmp_path / side
        root.mkdir()
        (root / 'native.json').write_text('{}')
        dump(root / 'algo07-star-input.json', dict(
            kind='algo07-star-native-evidence', run_id=config['run_id'],
            session_id='session', input_sha256='same', source_root='/production',
            files=[dict(path='native.json', sha256=cli.digest(root / 'native.json'))]))
        config[side] = str(root)
    return config


def test_observations_must_match_and_remain_intact(tmp_path):
    config = native_pair(tmp_path)
    assert cli.inputs(config)['session_id'] == 'session'
    (Path(config['candidate']) / 'native.json').write_text('{"changed": true}')
    with pytest.raises(ValueError, match='changed'):
        cli.inputs(config)


def test_independent_roots_and_matching_run_required(tmp_path):
    config = native_pair(tmp_path)
    with pytest.raises(ValueError, match='independent'):
        cli.inputs(dict(config, candidate=config['reference']))
    with pytest.raises(ValueError, match='Wrong native run'):
        cli.inputs(dict(config, run_id='another'))


@pytest.mark.parametrize(('science', 'publication', 'scope', 'code', 'full'), [
    (True, True, 'all', 0, True),
    (True, False, 'all', 1, False),
    (True, None, 'all', 2, False),
    (True, None, 'science', 0, False),
    (False, True, 'all', 1, False),
    (False, None, 'science', 1, False),
])
def test_missing_artifacts_never_become_full_pass(science, publication, scope, code, full):
    artifacts = None if publication is None else dict(publication_exact=publication)
    result = cli.verdict(dict(scientific_json_and_array_parity=science), artifacts, scope)
    assert result['exit_code'] == code
    assert result['case_full_parity'] is full
    assert result['ds26_equivalence_verified'] is False


def test_replay_uses_frozen_archive_original_workers_and_bounded_budget(tmp_path):
    config = {key: '/' + key for key in ('python', 'archive_view', 'archive_manifest',
                                        'runtimes', 'manifest', 'reference', 'candidate')}
    for side in cli.SIDES:
        command = cli.replay_command(config, side, tmp_path / 'receipt.json')
        assert command[:3] == ['timeout', '--kill-after=15', '1785']
        assert command[command.index('--maximum-seconds') + 1] == '1500'
        assert command.count('--manifest') == 2
        script = 'run_algo07_star_reference.py' if side == 'reference' else 'run_algo07_star.py'
        assert str(cli.REPO / 'tools' / script) in command
        assert '--evaluation-latitude' not in command


def test_reuse_option_cannot_change_reference_path(tmp_path):
    config = {key: '/' + key for key in ('python', 'archive_view', 'archive_manifest',
                                        'runtimes', 'manifest', 'reference', 'candidate')}
    config['candidate_terminal_read_reuse'] = True
    for side in cli.SIDES:
        command = cli.replay_command(config, side, tmp_path / 'receipt.json')
        driver = str(cli.REPO / 'tools/run_algo07_star_reuse.py')
        assert (driver in command) == (side == 'candidate')
        assert command[command.index('--maximum-seconds') + 1] == '1500'


def test_experimental_source_pin_rejects_edits_and_additions(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'REPO', tmp_path)
    tree = tmp_path / 'src'
    tree.mkdir()
    files = [tree / 'adapter.py', tmp_path / 'tools/run_algo07_star.py',
             tmp_path / 'tools/run_algo07_star_reuse.py']
    for p in files:
        p.parent.mkdir(exist_ok=True)
        p.write_text('original')
    config = dict(candidate_terminal_read_reuse=True, candidate_source_tree=str(tree),
                  candidate_source_pins={str(p): cli.digest(p) for p in files})
    cli.verify_candidate_sources(config)
    (tree / 'additional.py').write_text('new')
    with pytest.raises(ValueError, match='implementation changed'):
        cli.verify_candidate_sources(config)
    (tree / 'additional.py').unlink()
    files[0].write_text('changed')
    with pytest.raises(ValueError, match='implementation changed'):
        cli.verify_candidate_sources(config)


def test_unfinished_attempt_is_not_retried(tmp_path):
    (tmp_path / 'verify-run-reference-0001').mkdir()
    with pytest.raises(ValueError, match='unfinished or failed'):
        cli.replay(tmp_path, {}, 'reference')


def test_incomplete_pair_does_not_export_or_claim_pass(tmp_path):
    result = cli.check(tmp_path, {}, 'all')
    assert result['state'] == 'INCOMPLETE'
    assert result['exit_code'] == 2
    assert not list(tmp_path.glob('verify-check-*'))


def test_new_checkpoint_takes_precedence_over_old_complete_receipt(tmp_path):
    old = tmp_path / 'old.json'
    dump(old, dict(state='scientific_complete'))
    new = tmp_path / 'verify-run-reference-0001' / 'execution.json'
    dump(new, dict(state='checkpointed'))
    assert cli.execution(tmp_path, dict(reference_execution=str(old)), 'reference') == new


def test_check_writes_failure_receipt_for_invalid_export(tmp_path):
    config = native_pair(tmp_path)
    for side in cli.SIDES:
        receipt = tmp_path / f'{side}-chain-001.json'
        dump(receipt, dict(state='scientific_complete'))
        export = tmp_path / f'{side}-export'
        dump(export / 'ALGO02' / 'descriptor.json', dict(source_store_root='/wrong'))
        config[side + '_evidence'] = str(export)
    result = cli.check(tmp_path, config, 'science')
    assert result['state'] == 'FAIL'
    assert 'different private store' in result['error']
    assert cli.read(Path(result['evidence']) / 'summary.json') == result


def test_init_and_reload_pin_fixture_without_replaying(tmp_path):
    config = native_pair(tmp_path)
    fixture = tmp_path / 'fixture'
    for name in ('runtimes-r2.json', 'frozen-r2.json', 'frozen.json'):
        dump(fixture / name, {})
    dump(fixture / 'runtimes-r2.json',
         {a: dict(maximum_seconds=1200) for a in cli.ALGORITHMS})
    args = SimpleNamespace(case=tmp_path, fixture=fixture, run_id=config['run_id'],
                           source=Path('/production'), reference=Path(config['reference']),
                           candidate=Path(config['candidate']))
    assert cli.initialize(args)['state'] == 'initialized'
    assert cli.load(tmp_path)['run_id'] == config['run_id']
    dump(fixture / 'frozen-r2.json', dict(changed=True))
    with pytest.raises(ValueError, match='Changed configuration'):
        cli.load(tmp_path)


@pytest.mark.parametrize('code', [0, 1])
def test_bounded_run_records_checkpoint_or_failure(tmp_path, monkeypatch, code):
    config = {key: '/' + key for key in ('python', 'archive_view', 'archive_manifest',
                                        'runtimes', 'manifest', 'reference')}
    monkeypatch.setattr(cli, 'stage_status',
                        lambda root: [dict(algorithm='ALGO02', state='not_started')])
    monkeypatch.setattr(cli.os, 'geteuid', lambda: 0)
    commands = []

    def start(command, **kwargs):
        commands.append(command)
        assert kwargs['env']['OPENBLAS_NUM_THREADS'] == '1'
        dump(Path(command[-1]), dict(state='checkpointed', next_stage='ALGO03'))
        return SimpleNamespace(wait=lambda timeout: code)

    monkeypatch.setattr(cli.subprocess, 'Popen', start)
    if code:
        with pytest.raises(ValueError, match='Execution failed'):
            cli.replay(tmp_path, config, 'reference')
        with pytest.raises(ValueError, match='unfinished or failed'):
            cli.replay(tmp_path, config, 'reference')
    else:
        assert cli.replay(tmp_path, config, 'reference')['state'] == 'checkpointed'
    assert len(commands) == 1
    attempt = tmp_path / 'verify-run-reference-0001'
    assert cli.read(attempt / 'outcome.json')['exit_code'] == code
    assert (attempt / 'process.log').is_file()
