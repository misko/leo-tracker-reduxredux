import hashlib
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
import replay_algo07_star_publication_budget as replay
from replay_algo07_star_publication_budget import budget_driver


def plan(code):
    return dict(driver_code=code, driver_sha256=hashlib.sha256(code.encode()).hexdigest())


@pytest.mark.parametrize('seconds', [0, 30, -1, 301, float('nan'), float('inf')])
def test_budget_is_explicit_and_bounded(seconds):
    with pytest.raises(ValueError, match='budget'):
        budget_driver(plan('pass'), seconds)


def test_changed_original_driver_is_rejected():
    with pytest.raises(ValueError, match='hash'):
        budget_driver(dict(driver_code='pass', driver_sha256='wrong'), 300)


def test_only_real_deadline_changes(monkeypatch):
    import leo.analysis

    module = ModuleType('leo.analysis.position_grid')
    real_clock = object()
    calls = []

    def sampler(score, endpoints, *, maximum_seconds=30, clock=real_clock):
        calls.append((score, endpoints, maximum_seconds, clock))
        return 'original-return'

    module.sample_position_grid = sampler
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(leo.analysis, 'position_grid', module, raising=False)
    driver = 'result = _grid.sample_position_grid(score, endpoints)\n'
    score, endpoints = object(), {'c0': [0, 0], 'fitted_c': [1, 1]}
    namespace = dict(score=score, endpoints=endpoints)
    exec(budget_driver(plan(driver), 300), namespace)
    assert calls == [(score, endpoints, 300, real_clock)]
    assert namespace['result'] == 'original-return'


def test_sampler_failures_are_not_hidden(monkeypatch):
    import leo.analysis

    module = ModuleType('leo.analysis.position_grid')

    def sampler(**kwargs):
        raise RuntimeError('scorer failed')

    module.sample_position_grid = sampler
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(leo.analysis, 'position_grid', module, raising=False)
    with pytest.raises(RuntimeError, match='scorer failed'):
        exec(budget_driver(plan('_grid.sample_position_grid()'), 300), {})


@pytest.mark.parametrize('failure', [None, 'process', 'mismatch', 'postflight'])
def test_paired_replay_retains_failures_and_never_retries(tmp_path, monkeypatch, failure):
    case = tmp_path / 'case'
    case.mkdir()
    (case / replay.CONFIG).write_text('{}')
    receipt = case / 'execution.json'
    receipt.write_text(json.dumps(dict(state='scientific_complete')))
    manifest = case / 'manifest.json'
    manifest.write_text('{}')
    publication_plan = case / 'original-plan.json'
    publication_plan.write_text(json.dumps(dict(
        **plan('pass'), manifest_sha256=replay.digest(manifest), renderer='/renderer',
        python='/python')))
    config = dict(reference=str(case / 'source-a'), candidate=str(case / 'source-b'),
                  run_id='native')
    monkeypatch.setattr(replay, 'load', lambda _: config)
    monkeypatch.setattr(replay, 'execution', lambda *args: receipt)
    checks = []

    def verify(_):
        checks.append(True)
        return dict(verified=not (failure == 'postflight' and len(checks) == 2))

    monkeypatch.setattr(replay, 'verify', verify)
    calls = []

    def subprocess_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=int(failure == 'process'))

    monkeypatch.setattr(replay.subprocess, 'run', subprocess_run)
    monkeypatch.setattr(replay, 'compare', lambda _: dict(
        publication_exact=failure != 'mismatch', png_bytes_equal={'plot': True},
        shared_grid_points=179, grid_differences=['different'] if failure == 'mismatch' else [],
        science_differences=[], path_differences=[]))
    args = SimpleNamespace(case=case, publication_plan=publication_plan,
                           presentation_manifest=manifest, output=case / 'new-publication',
                           grid_seconds=300)
    if failure in ('process', 'postflight'):
        with pytest.raises(ValueError):
            replay.run(args)
    else:
        assert replay.run(args) == int(failure == 'mismatch')
        summary = json.loads((args.output / 'summary.json').read_text())
        assert not summary['original_production_budget_qualified']
        assert not summary['speedup_established']
    assert len(calls) == (1 if failure == 'process' else 2)
    saved = json.loads((args.output / 'plan.json').read_text())
    assert not saved['inference_rerun']
    assert calls[0][6] == saved['driver_code']
    if len(calls) == 2:
        assert calls[0][6] == calls[1][6]
    assert (args.output / 'reference-execution.json').exists()
    with pytest.raises(FileExistsError):
        replay.run(args)
