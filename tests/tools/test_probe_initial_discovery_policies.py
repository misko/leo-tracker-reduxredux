import copy
import hashlib
import json
import pickle

import numpy as np
import probe_initial_discovery_policies as probe
import pytest


def result():
    fit = dict(parameters=np.array([1., 2.]), score=5., residual_rms_hz=2.,
               evaluations=12, stopped='converged')
    arms = {arm: dict(fit=copy.deepcopy(fit), metrics=dict(tracks=[]),
                all_graph_associations=dict(tracks=[dict(component='curve', norad=10,
                    candidate_index=0, compatible=True, association_source='nominated')]),
                phase_rounds=[dict(epoch=i, fit=copy.deepcopy(fit)) for i in range(5)])
            for arm in probe.ARMS}
    return dict(status='complete', selected_hypothesis=0, unique_RF_hypotheses=4,
                fully_fitted_hypotheses=3, zero_phase_control={a: copy.deepcopy(fit)
                    for a in probe.ARMS}, choices=[dict(hypothesis=i, center_score=float(i),
                    node=dict(seed=dict(rows=[dict(component='curve', candidate_index=0,
                                                  candidate_norad=10)]), aliases=[i]),
                    arms=copy.deepcopy(arms)) for i in range(3)])


def test_complete_budget_counts_and_reused_control_are_required():
    value = result()
    counts = probe.work_counts(value)
    assert counts['optimizer_calls'] == 30
    assert counts['branch_arm_fits'] == 6
    assert counts['residual_evaluations'] == 360
    assert counts['additional_control_optimizer_calls'] == 0
    value['choices'][0]['arms']['c0']['phase_rounds'].pop()
    with pytest.raises(ValueError, match='five-round'):
        probe.work_counts(value)
    value = result()
    value['zero_phase_control']['c0']['parameters'][0] += .1
    with pytest.raises(ValueError, match='control reuse'):
        probe.work_counts(value)


def test_policy_audit_does_not_hide_endpoint_or_owner_changes():
    value = result()
    candidate = copy.deepcopy(value)
    candidate['initial_discovery_policy'] = probe.POLICIES['seed']
    candidate['initial_discovery_ranking'] = [dict(score=12.)]
    report = probe.compare(value, candidate)
    assert report['full_exact'] is False
    assert report['scientific_exact'] is True
    assert report['selected_signature_equal'] is True
    candidate['choices'][0]['arms']['c0']['fit']['parameters'][0] += 3.
    candidate['choices'][0]['arms']['c0']['all_graph_associations']['tracks'][0]['norad'] = 20
    report = probe.compare(value, candidate)
    assert report['scientific_exact'] is False
    assert report['arms']['c0']['endpoint_shift_km'] == 3.
    assert report['arms']['c0']['graph_owners_equal'] is False
    assert report['position_accuracy_evaluated'] is False
    assert report['whole_worker_speedup'] is None


def test_deduplicated_hypotheses_keep_full_original_budget_semantics():
    value = result()
    value['choices'] = value['choices'][:2]
    value['unique_RF_hypotheses'] = 2
    counts = probe.work_counts(value)
    assert counts['branch_arm_fits'] == 4
    assert counts['optimizer_calls'] == 20


def test_reference_requires_exact_saved_reproduction_and_same_source(tmp_path):
    value = result()
    raw = pickle.dumps(value)
    (tmp_path / 'initial.pickle').write_bytes(raw)
    plan = dict(request_sha256='request', manifest_sha256='manifest', sources={'x': 'hash'},
                tool_bindings={'y': 'hash'}, budgets=probe.BUDGETS)
    receipt = dict(plan, status='complete', policy='legacy', saved_initial_exact=True,
                   pickle_sha256=hashlib.sha256(raw).hexdigest(),
                   initial_sha256=probe.fingerprint(value))
    (tmp_path / 'result.json').write_text(json.dumps(receipt))
    assert probe.fingerprint(probe.read_reference(tmp_path, plan)) == probe.fingerprint(value)
    with pytest.raises(ValueError, match='matched bindings'):
        probe.read_reference(tmp_path, dict(plan, sources={'x': 'different'}))
    receipt['saved_initial_exact'] = False
    (tmp_path / 'result.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='Exact saved-initial'):
        probe.read_reference(tmp_path, plan)


def test_bound_sources_rejects_import_from_live_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'source_bindings', lambda: {
        'leo.analysis.example': dict(path=str(tmp_path / 'live/x.py'), sha256='hash')})
    with pytest.raises(ValueError, match='bound source root'):
        probe.bound_sources(tmp_path / 'frozen')


def test_native_paths_may_change_but_content_and_options_must_match():
    saved = {key: key for key in ('source_sha256', 'wrapper_sha256', 'binary_sha256',
        'provider', 'flags', 'original_sha256', 'ABI', 'sanitized')}
    assert probe.native_equivalence(dict(saved, binary='/old'), dict(saved, binary='/new'))['equal']
    with pytest.raises(ValueError, match='numerical provider'):
        probe.native_equivalence(saved, dict(saved, binary_sha256='changed'))


def test_legacy_has_no_policy_overrides_and_candidates_require_reference(tmp_path):
    assert probe.POLICIES['legacy'] == {}
    with pytest.raises(SystemExit):
        probe.main(['--request', '/missing', '--native-manifest', '/missing',
                    '--source-root', '/missing', '--output', str(tmp_path / 'new'),
                    '--policy', 'seed'])
