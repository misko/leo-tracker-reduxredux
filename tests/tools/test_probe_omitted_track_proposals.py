import json

import probe_omitted_track_proposals as probe
import pytest


def stored_requests(tmp_path, monkeypatch, count=1):
    paths = [tmp_path / f'request-{i}.json' for i in range(count)]
    for i, path in enumerate(paths):
        path.write_text(json.dumps(dict(index=i)))
    monkeypatch.setattr(probe, 'request_inputs', lambda path: (
        json.loads(path.read_text()), dict(identity=dict(run_id=path.stem)), None))
    return paths


def test_default_only_writes_plan_and_never_loads_saved_context(tmp_path, monkeypatch):
    request = stored_requests(tmp_path, monkeypatch)[0]
    monkeypatch.setattr(probe, 'load_context', lambda *a: pytest.fail('Archive loaded'))
    output = tmp_path / 'plan'
    assert probe.main(['--request', str(request), '--output', str(output)]) == 0
    plan = json.loads((output / 'plan.json').read_text())
    assert plan['policy'] == 'omitted_uncurved_calibrated_v1'
    assert not plan['GPS_used'] and not plan['position_fit_performed']
    assert not plan['position_inclusion_authorized']
    assert not (output / 'result.json').exists()


def test_verified_context_runs_selector_with_explicit_cap_and_records_no_admission(
    tmp_path, monkeypatch,
):
    request = stored_requests(tmp_path, monkeypatch)[0]
    context, evidence = object(), dict(original=True)
    monkeypatch.setattr(probe, 'load_context', lambda *a: (
        context, evidence, dict(replay_objective_deltas=dict(c0=0.0, fitted_c=0.0))))
    calls = []

    def select(c, e, *, max_proposals):
        calls.append((c, e, max_proposals))
        return dict(targets=[dict(track_id='omitted')])

    monkeypatch.setattr(probe.omitted_track_proposals, 'rank_omitted_tracks', select)
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {19})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    output = tmp_path / 'run'
    assert probe.main(['--request', str(request), '--output', str(output),
                       '--max-proposals', '1', '--run']) == 0
    assert calls == [(context, evidence, 1)]
    result = json.loads((output / 'context-0.json').read_text())
    assert result['status'] == 'complete'
    assert result['selector']['targets'] == [dict(track_id='omitted')]
    assert result['binding']['replay_objective_deltas'] == dict(c0=0.0, fitted_c=0.0)
    assert result['selector_seconds'] >= 0
    assert not result['position_fit_performed'] and not result['predictive_qualification_performed']


def test_saved_context_failure_is_a_failed_probe_and_never_a_successful_fallback(
    tmp_path, monkeypatch,
):
    request = stored_requests(tmp_path, monkeypatch)[0]

    def fail(*args):
        raise ValueError('saved objective differs')

    monkeypatch.setattr(probe, 'load_context', fail)
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {19})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    output = tmp_path / 'failure'
    assert probe.main(['--request', str(request), '--output', str(output), '--run']) == 1
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'failed'
    assert result['cases'][0]['error'] == 'saved objective differs'
    assert 'selector' not in result['cases'][0]


def test_changed_source_request_invalidates_completed_selector(tmp_path, monkeypatch):
    request = stored_requests(tmp_path, monkeypatch)[0]
    monkeypatch.setattr(probe, 'load_context', lambda *a: (None, {}, {}))

    def changed(*args, **kwargs):
        request.write_text('changed')
        return dict(targets=[])

    monkeypatch.setattr(probe.omitted_track_proposals, 'rank_omitted_tracks', changed)
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {19})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    output = tmp_path / 'changed'
    assert probe.main(['--request', str(request), '--output', str(output), '--run']) == 1
    result = json.loads((output / 'context-0.json').read_text())
    assert result['status'] == 'failed'
    assert result['error'] == 'Probe source or saved request changed during execution'


def test_duplicate_request_and_existing_output_are_rejected(tmp_path, monkeypatch):
    request = stored_requests(tmp_path, monkeypatch)[0]
    with pytest.raises(SystemExit):
        probe.main(['--request', str(request), '--request', str(request),
                    '--output', str(tmp_path / 'duplicate')])
    with pytest.raises(SystemExit):
        probe.main(['--request', str(request), '--output', str(tmp_path)])
