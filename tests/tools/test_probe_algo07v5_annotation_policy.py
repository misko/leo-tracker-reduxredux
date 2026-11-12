from copy import deepcopy
from types import SimpleNamespace

import probe_algo07v5_annotation_policy as probe
import pytest


def annotation():
    history = [dict(optimizer=dict(evaluations=7, converged=True, budget_exhausted=False,
                                   stationarity=dict(satisfied=False))) for _ in range(5)]
    proposal = dict(arms={a: dict(history=deepcopy(history)) for a in ('c0', 'fitted_c')})
    return dict(result=dict(folds=[dict(proposals=[deepcopy(proposal), deepcopy(proposal)])
                                   for _ in range(3)]))


def test_shared_proposal_metadata_counts_each_training_fit_once():
    result = probe.work_counts(annotation())
    assert result == dict(available=True, training_calls=6, phase_rounds=[5] * 6,
                         completed_rounds=30, recorded_optimizer_calls=30,
                         optimizer_work_available=True,
                         residual_evaluations=210, reported_convergences=30,
                         reference_fallbacks=0, completed_phase_results=30, optimizer_attempts=30,
                         budget_exhaustions=0, stationarity_satisfied=0)


def test_work_counts_preserves_budget_and_stationarity_diagnostics():
    value = annotation()
    for proposal in value['result']['folds'][0]['proposals']:
        record = proposal['arms']['c0']['history'][0]['optimizer']
        record.update(converged=False, budget_exhausted=True,
                      stationarity=dict(satisfied=True))
    result = probe.work_counts(value)
    assert result['reported_convergences'] == 29
    assert result['budget_exhaustions'] == result['stationarity_satisfied'] == 1


def test_missing_or_inconsistent_metadata_is_not_a_zero_work_claim():
    value = annotation()
    value['result']['folds'][0]['proposals'] = []
    assert probe.work_counts(value)['available'] is False
    value = annotation()
    value['result']['folds'][0]['proposals'][0]['arms']['c0']['history'].pop()
    with pytest.raises(ValueError, match='disagree'):
        probe.work_counts(value)


def scientific_result():
    return dict(metrics=dict(nominees={'1': [dict(candidate_index=2, arm='c0')]},
        proposals=[dict(seed=1, arm='c0', norad=123, alias=0)],
        consensus=dict(status='prediction_mismatch', norad=123,
            votes=[dict(seed=1, arm='c0', norad=123, runner_up=456, adequate=False)])))


@pytest.mark.parametrize('field', ['nominees', 'alias', 'vote', 'consensus'])
def test_discrete_science_changes_remain_visible(field):
    baseline = scientific_result()
    changed = deepcopy(baseline)
    if field == 'nominees':
        changed['metrics']['nominees']['1'][0]['candidate_index'] = 3
    elif field == 'alias':
        changed['metrics']['proposals'][0]['alias'] = 1
    elif field == 'vote':
        changed['metrics']['consensus']['votes'][0]['adequate'] = True
    else:
        changed['metrics']['consensus']['status'] = 'conditionally_supported_identity'
    assert all(probe.scientific_gate(baseline, baseline).values())
    assert not all(probe.scientific_gate(baseline, changed).values())


def test_queued_reference_keeps_inputs_bound_but_can_compare_execution_paths():
    receipt = dict(status='complete', optimizer='gn', execution='folds', target=1,
                   request_sha256='request', manifest_sha256='native', modules={'m': 'a'},
                   bindings={'b': 'a'})
    plan = dict(receipt, execution='queued', optimizer='lbfgsb', status='plan')
    probe.qualify_reference(receipt, plan)
    for field in ('target', 'request_sha256', 'manifest_sha256', 'modules', 'bindings'):
        changed = dict(plan, **{field: 'different'})
        with pytest.raises(ValueError, match='same source and inputs'):
            probe.qualify_reference(receipt, changed)
    with pytest.raises(ValueError, match='GN reference'):
        probe.qualify_reference(dict(receipt, optimizer='lbfgsb'), plan)


def test_uninstrumented_gn_work_is_not_reported_as_optimized_work():
    value = annotation()
    for fold in value['result']['folds']:
        for proposal in fold['proposals']:
            for arm in proposal['arms'].values():
                arm['history'] = [dict(endpoint=[0., 0.]) for _ in range(5)]
    result = probe.work_counts(value)
    assert result['completed_rounds'] == 30
    assert result['recorded_optimizer_calls'] == 0
    assert result['optimizer_work_available'] is False
    assert result['residual_evaluations'] is None
    assert result['reported_convergences'] is None
    assert result['budget_exhaustions'] is None


def test_partial_optimizer_telemetry_cannot_understate_work():
    value = annotation()
    for proposal in value['result']['folds'][0]['proposals']:
        proposal['arms']['c0']['history'][0].pop('optimizer')
    with pytest.raises(ValueError, match='Incomplete per-round'):
        probe.work_counts(value)


def test_completed_reference_fallback_is_separate_from_primary_success():
    value = annotation()
    for proposal in value['result']['folds'][0]['proposals']:
        record = proposal['arms']['c0']['history'][0]['optimizer']
        record.update(converged=None, reference_fit_completed=True,
                      attempts=[dict(optimizer='lbfgsb'), dict(optimizer='original_gn')])
    result = probe.work_counts(value)
    assert result['reported_convergences'] == 29
    assert result['reference_fallbacks'] == 1
    assert result['completed_phase_results'] == 30
    assert result['optimizer_attempts'] == 31


@pytest.mark.parametrize('optimizer', ['gn', 'lbfgsb'])
def test_runtime_path_binds_both_variants_before_loading_context(
    tmp_path, monkeypatch, optimizer
):
    request, manifest = tmp_path / 'request.json', tmp_path / 'manifest.json'
    request.write_text('{}')
    manifest.write_text('{}')
    monkeypatch.setattr(probe, 'request_inputs', lambda path: ({}, {}, object()))
    monkeypatch.setattr(probe, 'read_manifest', lambda path: {})
    monkeypatch.setattr(probe, 'validate_manifest', lambda value: value)
    bindings = []

    def bound(root):
        assert probe.annotation_fit.policy['id'] == 'lbfgsb-full5-625-v1'
        bindings.append(root)
        return {'root': str(root), 'files': {'annotation_training.py': 'bound'}}

    monkeypatch.setattr(probe, 'source_binding', bound)
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {0, 1, 2})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    backend = SimpleNamespace(provenance=lambda: {'native': True})
    monkeypatch.setattr(probe, 'ProcessBound', lambda *args: backend)
    scientific = {'context': 'same'}
    target = dict(track_id='track', inactive_fragment=False)
    monkeypatch.setattr(probe, 'load_context', lambda *args: (
        {}, dict(selected_targets=[target], inventory={}, publication_support={}), scientific))
    calls = []

    def annotate(*args, **options):
        calls.append(options)
        return annotation()

    monkeypatch.setattr(probe, 'annotate', annotate)
    monkeypatch.setattr(probe, 'metrics', lambda value: scientific_result()['metrics'])
    args = ['--request', str(request), '--native-manifest', str(manifest), '--target', '0',
            '--output', str(tmp_path / 'output'), '--optimizer', optimizer, '--run']
    if optimizer == 'lbfgsb':
        monkeypatch.setattr(probe, 'read_reference', lambda path: (
            dict(scientific_result(), scientific=scientific), annotation()))
        monkeypatch.setattr(probe, 'qualify_reference', lambda *args: None)
        monkeypatch.setattr(probe, 'compare', lambda *args: dict(exact=False))
        args += ['--reference', str(tmp_path / 'reference')]
    assert probe.main(args) == 0
    assert len(bindings) == 2 and bindings[0] == bindings[1]
    assert calls[0]['map_training'] is probe.map_annotation_training
    assert calls[0].get('training_fit') is (
        probe.annotation_fit if optimizer == 'lbfgsb' else None)
