import ast
import copy
import hashlib
import json
import pickle
from types import SimpleNamespace

import numpy as np
import probe_algo07v5_annotation_rounds as probe
import pytest

from tests.operations.test_localization_v3_job import request_fixture

SYNTHETIC = '''def fit_training(d, node, keep, arm):
    history = []
    for _epoch in range(5):
        f = fit(None, iterations=48)
        history.append(f)
    return None, None, dict(history=history)
'''


def synthetic(rounds, source=SYNTHETIC, scope=None):
    return probe.transform(rounds, source, scope or dict(fit=lambda *a, **k: k),
                           hashlib.sha256(source.encode()).hexdigest())


@pytest.mark.parametrize('rounds', [1, 2, 3, 5])
def test_only_phase_round_literal_changes_and_full5_is_identity(rounds):
    operation, before, after = synthetic(rounds)
    old, new = ast.parse(before), ast.parse(after)
    assert len(operation(None, None, None, 'c0')[2]['history']) == rounds
    assert all(v['iterations'] == 48 for v in operation(None, None, None, 'c0')[2]['history'])
    if rounds == 5:
        assert ast.dump(old) == ast.dump(new)
    new.body[0].body[1].iter.args[0].value = 5
    assert ast.dump(old) == ast.dump(new)


def test_source_hash_and_unique_outer_pattern_are_guards():
    with pytest.raises(ValueError, match='source changed'):
        probe.transform(3, SYNTHETIC, {}, 'wrong')
    for bad in [SYNTHETIC.replace('_epoch', 'epoch'),
                SYNTHETIC.replace('history = []', 'history = list(range(5))'),
                SYNTHETIC.replace('range(5)', 'range(6)')]:
        with pytest.raises(ValueError, match='outer five-round'):
            synthetic(3, bad)
    with pytest.raises(ValueError):
        synthetic(4)


def test_namespace_instrumentation_counts_both_arms_without_mutation(tmp_path, monkeypatch):
    original_transform = probe.transform
    def transform(rounds):
        return original_transform(rounds, SYNTHETIC, {},
                                   hashlib.sha256(SYNTHETIC.encode()).hexdigest())
    monkeypatch.setattr(probe, 'transform', transform)
    monkeypatch.setattr(probe.prediction, 'fit',
                        lambda *args, **kwargs: dict(evaluations=7, stopped='fake'))
    original_fold = probe.predictive_annotation.annotate_fold
    original_training = original_fold.__globals__['fit_training']
    receipts = tmp_path / 'training-receipts'
    receipts.mkdir()
    operation, _, _ = probe.annotation_operation(3, receipts)
    training = operation.__globals__['annotate_fold'].__globals__['fit_training']
    for arm in probe.prediction.ARMS:
        assert len(training({}, {}, [], arm)[2]['history']) == 3
    assert original_fold.__globals__['fit_training'] is original_training
    assert probe.predictive_annotation.annotate.__globals__['annotate_fold'] is original_fold
    counts = probe.work_counts(tmp_path, 'clone')
    assert counts['training_calls_completed'] == counts['training_calls_started'] == 2
    assert counts['optimizer_calls_started'] == counts['completed_rounds'] == 6
    assert counts['optimizer_evaluations'] == 42
    assert probe.work_counts(tmp_path, 'oracle')['optimizer_evaluations'] is None


def annotation():
    arm = dict(scores=dict(conditional_target=dict(negative_twice_log_density=2., rms_hz=3.)),
               training_objective=4., final_phase_change_s=.01,
               minimum_target_elevation_deg=5., history=[dict(endpoint=np.array([1., 2.]))])
    proposals = [dict(candidate_index=1, norad=11, alias=-2,
                      arms={a: copy.deepcopy(arm) for a in probe.prediction.ARMS})]
    return dict(protocol=dict(phase_rounds=5),
                nominations={7: dict(selected=[dict(candidate_index=1, arm='fitted_c')])},
                result=dict(folds=[dict(seed=7, proposals=proposals)],
                            annotation=dict(status='prediction_mismatch', norad=11,
                                            votes=[dict(arm=a, adequate=False)
                                                   for a in probe.prediction.ARMS])))


def test_comparison_retains_both_arms_aliases_order_and_phase_decisions():
    before, after = annotation(), annotation()
    after['result']['folds'][0]['proposals'][0]['arms']['fitted_c']['final_phase_change_s'] = .02
    after['result']['annotation']['votes'][1]['adequate'] = True
    result = probe.compare(before, after)
    assert result['exact'] is False
    assert len(result['differences']) == 2
    assert {r['arm'] for r in result['actual']['proposals']} == set(probe.prediction.ARMS)
    assert all(r['alias'] == -2 for r in result['actual']['proposals'])
    assert result['actual']['nominees']['7'] == [dict(candidate_index=1, arm='fitted_c')]
    assert result['actual']['consensus']['votes'][1]['adequate'] is True
    assert result['inclusion_decisions_evaluated'] is False


@pytest.mark.parametrize('value', [{}, [], None, dict(job={}), dict(not_a_request=True)])
def test_empty_or_malformed_request_cannot_load_store(tmp_path, value):
    path = tmp_path / 'request.json'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        probe.request_inputs(path)


def test_valid_v3_request_uses_public_store_and_never_evaluation_reference(tmp_path):
    request = request_fixture(tmp_path)
    request['evaluation_reference'] = dict(latitude_deg=0., longitude_deg=0.)
    path = tmp_path / 'request.json'
    path.write_text(json.dumps(request))
    parsed, job, store = probe.request_inputs(path)
    assert parsed == job == request
    assert store.__name__ == 'LocalizationV3Store'


@pytest.mark.parametrize('version', [4, 5])
def test_wrapped_request_chooses_its_public_store(tmp_path, monkeypatch, version):
    from leo.analysis.localization_v4 import backend
    from leo.operations import localization_v5_job
    monkeypatch.setattr(backend, 'validate_manifest', lambda m, **kw: m)
    job = request_fixture(tmp_path)
    job['identity']['run_id'] = f'v{version}-' + 'a' * 40
    request = dict(schema_version=1, algorithm=f'algo07v{version}-native-v1',
                   backend_manifest={}, job=job)
    if version == 5:
        request['initial_control_policy'] = localization_v5_job.POLICY
    path = tmp_path / 'request.json'
    path.write_text(json.dumps(request))
    parsed, selected_job, store = probe.request_inputs(path)
    assert parsed == request and selected_job == job
    assert store.__name__ == f'LocalizationV{version}Store'


def test_context_uses_explicit_native_bound_and_verified_public_evidence(monkeypatch):
    request = dict(test='request')
    job = dict(output_root='/local', identity=dict(run_id='run'), search_center=[37., -122.],
               evaluation_reference=dict(latitude_deg=0., longitude_deg=0.))
    receipt = dict(run_id='run')
    cavity = dict(status='complete')
    prepared = dict(noise=dict(sigma=1.))
    evidence = dict(identity=job['identity'], preparation=prepared,
                    provenance=dict(request_sha256=probe.canonical_digest(request),
                                    configuration=dict(request=job)),
                    audit=dict(cavity_policy=cavity, recovery_inventory=dict(target='target')))
    saved = dict(evidence=evidence, receipt=receipt, sha256=probe.canonical_digest(receipt))
    seen = []
    def store(root):
        assert root == '/local'
        return SimpleNamespace(load=lambda run: saved if run == 'run' else None)
    bound = object()
    scan = object()
    def context(values, region, digest, **kwargs):
        assert values is prepared and kwargs == dict(genuine=True, bound=bound)
        assert len(digest) == 64
        seen.append(region)
        return scan
    def recovery(value, selected):
        assert value is scan and selected is cavity
        return dict(replay=dict(c0=0., fitted_c=0.))
    monkeypatch.setattr(probe, '_context', context)
    monkeypatch.setattr(probe, 'recovery_context', recovery)
    result, inventory, binding = probe.load_context(request, job, store, bound)
    assert inventory == dict(target='target') and len(seen) == 1
    assert binding['replay_objective_deltas'] == result['replay']
    evidence['provenance']['request_sha256'] = 'changed'
    with pytest.raises(ValueError, match='binding mismatch'):
        probe.load_context(request, job, store, bound)
    assert len(seen) == 1


def cli_inputs(tmp_path, monkeypatch):
    request = tmp_path / 'request.json'
    manifest = tmp_path / 'manifest.json'
    request.write_text('{}')
    manifest.write_text('{}')
    monkeypatch.setattr(probe, 'request_inputs', lambda p: ({}, {}, None))
    monkeypatch.setattr(probe, 'read_manifest', lambda p: {})
    monkeypatch.setattr(probe, 'validate_manifest', lambda m: m)
    monkeypatch.setattr(probe, 'source_bindings', lambda: {})
    return ['--request', str(request), '--native-manifest', str(manifest),
            '--target', '0', '--rounds', '5', '--output', str(tmp_path / 'out')]


def test_default_plan_never_loads_context_or_fits(tmp_path, monkeypatch):
    args = cli_inputs(tmp_path, monkeypatch)
    def forbidden(*a, **k):
        pytest.fail('Plan attempted inference or native activation')
    monkeypatch.setattr(probe, 'load_context', forbidden)
    monkeypatch.setattr(probe, 'ProcessBound', forbidden)
    monkeypatch.setattr(probe.prediction, 'fit', forbidden)
    assert probe.main(args) == 0
    plan = json.loads((tmp_path / 'out' / 'plan.json').read_bytes())
    assert plan['status'] == 'plan'
    assert plan['folds'] == 3 and plan['candidates'] == 12 and plan['position_steps'] == 48
    assert not (tmp_path / 'out' / 'result.json').exists()


@pytest.mark.parametrize('extra', [['--timeout', '121'], ['--target', '-1'],
                                  ['--run'], ['--mode', 'oracle', '--rounds', '2']])
def test_cli_budget_and_reference_guards(tmp_path, monkeypatch, extra):
    with pytest.raises(SystemExit):
        probe.main(cli_inputs(tmp_path, monkeypatch) + extra)
    assert not (tmp_path / 'out').exists()


def test_deadline_failure_is_never_completed(tmp_path, monkeypatch):
    args = cli_inputs(tmp_path, monkeypatch) + ['--mode', 'oracle', '--run']
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda p: {1, 2, 3})
    monkeypatch.setattr(probe, 'ProcessBound', lambda *a: None)
    monkeypatch.setattr(probe, 'load_context', lambda *a: ({}, dict(
        selected_targets=[dict(track_id='track', inactive_fragment=False)],
        inventory={}, publication_support={}), {}))
    from leo.operations.localization_v3_job import StageDeadline
    def expired(*args, **kwargs):
        raise StageDeadline('fake timeout')
    monkeypatch.setattr(probe.predictive_annotation, 'annotate', expired)
    with pytest.raises(StageDeadline):
        probe.main(args)
    assert json.loads((tmp_path / 'out' / 'failure.json').read_bytes())['status'] == 'failed'
    assert not (tmp_path / 'out' / 'result.json').exists()


def test_reference_pickle_is_bound_to_complete_annotation(tmp_path):
    value = annotation()
    raw = pickle.dumps(value, protocol=5)
    (tmp_path / 'annotation.pickle').write_bytes(raw)
    receipt = dict(status='complete', pickle_sha256=hashlib.sha256(raw).hexdigest(),
                   annotation_sha256=probe.fingerprint(value))
    (tmp_path / 'result.json').write_text(json.dumps(receipt))
    assert probe.fingerprint(probe.read_reference(tmp_path)[1]) == probe.fingerprint(value)
    (tmp_path / 'annotation.pickle').write_bytes(raw + b'changed')
    with pytest.raises(ValueError, match='content-bound'):
        probe.read_reference(tmp_path)


def test_complete_fake_annotation_requires_oracle_then_clone5(tmp_path, monkeypatch):
    args = cli_inputs(tmp_path, monkeypatch)
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda p: {1, 2, 3})
    monkeypatch.setattr(probe, 'ProcessBound',
                        lambda *a: SimpleNamespace(provenance=lambda: dict(receipts=[])))
    monkeypatch.setattr(probe, 'load_context', lambda *a: ({}, dict(
        selected_targets=[dict(track_id='track', inactive_fragment=False)],
        inventory={}, publication_support={}), dict(replay_objective_deltas={})))
    monkeypatch.setattr(probe.predictive_annotation, 'annotate', lambda *a, **k: annotation())
    def run(mode, rounds, name, reference=None):
        call = args + ['--run', '--mode', mode, '--rounds', str(rounds),
                       '--output', str(tmp_path / name)]
        if reference:
            call += ['--reference', str(tmp_path / reference)]
        return probe.main(call)
    assert run('oracle', 5, 'oracle') == 0
    with pytest.raises(ValueError, match='full5 oracle proof'):
        run('clone', 1, 'unqualified', 'oracle')
    assert not (tmp_path / 'unqualified' / 'result.json').exists()
    assert run('clone', 5, 'clone5', 'oracle') == 0
    receipt = json.loads((tmp_path / 'clone5' / 'result.json').read_bytes())
    assert receipt['full5_oracle_exact'] is True and receipt['exact'] is True
    assert run('clone', 1, 'clone1', 'clone5') == 0
    receipt, value = probe.read_reference(tmp_path / 'clone1')
    assert receipt['approximation'] is True and receipt['full5_oracle_exact'] is False
    assert value['protocol']['phase_rounds'] == 1
    assert (tmp_path / 'clone1' / 'comparison.json').exists()
