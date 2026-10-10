"""Mocked staged publication; no numerical, recording or reference access."""

import json
from pathlib import Path

from PIL import Image
import pytest

import staged_report as staged


def fixture(tmp_path, monkeypatch):
    members = [dict(label=f'L{i}') for i in range(193)]
    plan = dict(runtime=dict(interpreter=staged.sys.executable), members=members)
    protocol = tmp_path / 'protocol.json'
    protocol.write_text(json.dumps(plan))
    monkeypatch.setattr(staged.report, 'NUMERICAL_SHA', staged.evaluation.sha(protocol))
    monkeypatch.setattr(staged.report, 'NUMERICAL_DIGEST', 'digest')
    frozen = dict(numerical_protocol_digest='digest', source_sha256={})
    (tmp_path / 'evaluation_protocol.json').write_text(json.dumps(frozen))
    monkeypatch.setattr(staged.report, 'prepare_evaluation', lambda: frozen)
    events = []
    receipts = {'L0/search/result.json': 'hash0'}
    summary = dict(all_terminal=True, rows=[dict(label=m['label']) for m in members],
                   receipt_sha256=receipts)
    metrics = dict(membership=193)

    def preflight(*args):
        events.append('preflight')
        return dict(counts=dict(members=193, phases=579), receipt_sha256=receipts)

    def evaluate(*args):
        events.append('evaluate')
        return summary

    def aggregate(*args):
        events.append('metrics')
        return metrics

    def render(_, __, stage):
        events.append('render')
        stage = Path(stage)
        (stage / 'METRICS.json').write_text(json.dumps(metrics))
        (stage / 'RESULTS.md').write_text(''.join(f'![{name}]({name})\n' for name in staged.IMAGES))
        for name in staged.IMAGES:
            Image.new('RGB', (2, 2), 'white').save(stage / name)
        return [stage / name for name in staged.IMAGES]

    monkeypatch.setattr(staged.postseal_preflight, 'preflight', preflight)
    monkeypatch.setattr(staged.evaluation, 'build', evaluate)
    monkeypatch.setattr(staged.report_metrics, 'aggregate', aggregate)
    monkeypatch.setattr(staged.publish, 'publish', render)
    return dict(plan=plan, frozen=frozen, events=events, receipts=receipts,
                summary=summary, metrics=metrics)


def test_full_stage_verification_and_atomic_publication(tmp_path, monkeypatch):
    state = fixture(tmp_path, monkeypatch)
    target = staged.run(here=tmp_path)
    assert target == tmp_path / staged.FINAL_NAME
    assert state['events'] == ['preflight', 'evaluate', 'metrics', 'render']
    assert {p.name for p in target.iterdir()} == set(staged.ARTIFACTS) | {'REPORT_INTEGRITY.json'}
    integrity = json.loads((target / 'REPORT_INTEGRITY.json').read_text())
    assert integrity == {name: staged.evaluation.sha(target / name) for name in staged.ARTIFACTS}
    provenance = json.loads((target / 'PROVENANCE.json').read_text())
    assert provenance['preflight_counts'] == dict(members=193, phases=579)
    assert provenance['runtime_interpreter'] == staged.sys.executable
    assert not list(tmp_path.glob('.sealed-full193-report-stage-*'))


def test_frozen_metadata_mismatch_stops_before_preflight(tmp_path, monkeypatch):
    state = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(staged.report, 'prepare_evaluation', lambda: {'different': True})
    with pytest.raises(ValueError, match='metadata differs'):
        staged.run(here=tmp_path)
    assert state['events'] == []
    assert not (tmp_path / staged.FINAL_NAME).exists()


def test_wrong_runtime_stops_before_preflight(tmp_path, monkeypatch):
    state = fixture(tmp_path, monkeypatch)
    plan = state['plan']
    plan['runtime']['interpreter'] = '/wrong/python'
    path = tmp_path / 'protocol.json'
    path.write_text(json.dumps(plan))
    monkeypatch.setattr(staged.report, 'NUMERICAL_SHA', staged.evaluation.sha(path))
    with pytest.raises(ValueError, match='pinned reporting interpreter'):
        staged.run(here=tmp_path)
    assert state['events'] == []


def test_preflight_failure_never_opens_evaluation(tmp_path, monkeypatch):
    state = fixture(tmp_path, monkeypatch)
    def fail(*args):
        state['events'].append('preflight')
        raise ValueError('unsealed')
    monkeypatch.setattr(staged.postseal_preflight, 'preflight', fail)
    with pytest.raises(ValueError, match='unsealed'):
        staged.run(here=tmp_path)
    assert state['events'] == ['preflight']
    assert not (tmp_path / staged.FINAL_NAME).exists()


def test_changed_receipts_block_rendering(tmp_path, monkeypatch):
    state = fixture(tmp_path, monkeypatch)
    state['summary']['receipt_sha256'] = {'different': 'hash'}
    with pytest.raises(ValueError, match='receipts changed'):
        staged.run(here=tmp_path)
    assert state['events'] == ['preflight', 'evaluate']
    assert not (tmp_path / staged.FINAL_NAME).exists()


@pytest.mark.parametrize('failure', ['render', 'png', 'markdown'])
def test_render_failure_or_bad_artifact_leaves_no_final(tmp_path, monkeypatch, failure):
    state = fixture(tmp_path, monkeypatch)
    original = staged.publish.publish
    def broken(summary, metrics, stage):
        if failure == 'render':
            raise RuntimeError('render unavailable')
        images = original(summary, metrics, stage)
        if failure == 'png':
            (Path(stage) / staged.IMAGES[0]).write_bytes(b'not a PNG')
        if failure == 'markdown':
            (Path(stage) / 'RESULTS.md').write_text('images omitted')
        return images
    monkeypatch.setattr(staged.publish, 'publish', broken)
    with pytest.raises((RuntimeError, ValueError, OSError)):
        staged.run(here=tmp_path)
    assert state['events'][:3] == ['preflight', 'evaluate', 'metrics']
    assert not (tmp_path / staged.FINAL_NAME).exists()
    assert not list(tmp_path.glob('.sealed-full193-report-stage-*'))


def test_existing_final_never_overwritten(tmp_path, monkeypatch):
    state = fixture(tmp_path, monkeypatch)
    target = tmp_path / staged.FINAL_NAME
    target.mkdir()
    (target / 'sentinel').write_text('keep')
    with pytest.raises(FileExistsError):
        staged.run(here=tmp_path)
    assert (target / 'sentinel').read_text() == 'keep'
    assert state['events'] == []
