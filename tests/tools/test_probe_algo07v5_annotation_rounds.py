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


class QuadraticProblem:
    def __init__(self, target):
        self.target = np.array(target)
        self.lower, self.upper = np.array([-1., -2.]), np.array([2., 1.])
        self.keep = np.array([True, False, True])
        self.calls, self.calculations = [], []

    def residual(self, x):
        assert np.all(x >= self.lower) and np.all(x <= self.upper)
        self.calls.append(np.asarray(x).copy())
        return np.r_[(x - self.target) * [2., 3.], 4.]

    def calculate(self, x):
        self.calculations.append(np.asarray(x).copy())
        return dict(conditional_residual_hz=np.array([3., 99., 4.]),
                    normalization_constant=17., negative_twice_elbo=123.)


@pytest.mark.parametrize('optimizer', ['lbfgsb', 'trf'])
@pytest.mark.parametrize('target', [[.5, -.4], [3., -3.]])
def test_alternative_solves_same_bounded_residual_square_and_counts_calls(optimizer, target):
    problem = QuadraticProblem(target)
    result = probe.alternative_fit(optimizer)(problem, [8., -9.], iterations=48)
    np.testing.assert_allclose(result['parameters'], np.clip(target, problem.lower, problem.upper),
                               atol=.002)
    expected = np.r_[(result['parameters'] - target) * [2., 3.], 4.]
    assert result['score'] == pytest.approx(expected @ expected)
    assert result['negative_twice_elbo'] == 123.
    assert result['active_points'] == 2
    assert result['residual_rms_hz'] == pytest.approx(np.sqrt(12.5))
    assert result['evaluations'] == len(problem.calls) == len(result['history'])
    assert len(problem.calculations) == result['final_metadata_calculate_calls'] == 1
    assert result['history_kind'] == 'all residual evaluations including Jacobians'
    np.testing.assert_array_equal(problem.calculations[0], result['parameters'])
    for observed, recorded in zip(problem.calls, result['history'], strict=True):
        np.testing.assert_array_equal(observed, recorded['parameters'])
    if optimizer == 'trf':
        assert result['evaluations'] == (result['scipy_result']['nfev']
                                         + 4 * result['scipy_result']['njev'])
    assert result['budget_exhausted'] is False
    assert result['scipy_result']['success'] is True
    assert result['converged'] is True


@pytest.mark.parametrize('optimizer', ['lbfgsb', 'trf'])
def test_alternative_rejects_changed_iteration_budget_before_residual(optimizer):
    problem = QuadraticProblem([0., 0.])
    with pytest.raises(ValueError, match='48 position steps'):
        probe.alternative_fit(optimizer)(problem, iterations=47)
    assert problem.calls == problem.calculations == []


def test_trf_jacobian_matches_original_clipped_central_geometry(monkeypatch):
    problem = QuadraticProblem([.2, -.3])
    def least_squares(residual, start, *, jac, bounds, method, **options):
        assert options == probe.optimizer_policy('trf')['options']
        assert method == 'trf'
        np.testing.assert_array_equal(start, [-1., 1.])
        np.testing.assert_array_equal(bounds, [problem.lower, problem.upper])
        value = residual(start)
        np.testing.assert_allclose(jac(start), [[2., 0.], [0., 3.], [0., 0.]])
        np.testing.assert_array_equal(problem.calls[1], [-.999, 1.])
        np.testing.assert_array_equal(problem.calls[2], [-1., 1.])
        np.testing.assert_array_equal(problem.calls[3], [-1., 1.])
        np.testing.assert_array_equal(problem.calls[4], [-1., .999])
        return dict_result(x=start, fun=value, nfev=1, njev=1, success=True, status=1,
                           message='synthetic convergence')
    monkeypatch.setattr(probe, 'least_squares', least_squares)
    result = probe.alternative_fit('trf')(problem, [-9., 9.])
    assert result['evaluations'] == 5 and result['scipy_result']['nfev'] == 1


def dict_result(**kwargs):
    from scipy.optimize import OptimizeResult
    return OptimizeResult(**kwargs)


def test_lbfgsb_uses_direct_residual_square_and_declared_options(monkeypatch):
    problem = QuadraticProblem([.2, -.3])
    def minimize(objective, start, *, method, bounds, options):
        assert options == probe.optimizer_policy('lbfgsb')['options']
        assert method == 'L-BFGS-B'
        np.testing.assert_array_equal(start, [-1., 1.])
        np.testing.assert_array_equal(bounds, np.array([problem.lower, problem.upper]).T)
        value = objective(start)
        assert value == pytest.approx(np.sum(((start - problem.target) * [2., 3.]) ** 2) + 16.)
        return dict_result(x=start, fun=value, nfev=1, njev=0, nit=48, success=False,
                           status=1, message='iteration cap')
    monkeypatch.setattr(probe, 'minimize', minimize)
    result = probe.alternative_fit('lbfgsb')(problem, [-9., 9.])
    assert result['budget_exhausted'] is True
    assert result['scipy_result']['success'] is False
    assert result['converged'] is False


@pytest.mark.parametrize('optimizer', ['lbfgsb', 'trf'])
def test_physical_cap_includes_derivative_calls_and_is_not_convergence(monkeypatch, optimizer):
    problem = QuadraticProblem([0., 0.])
    def exhaust(evaluate, start, **kwargs):
        for _ in range(626):
            evaluate(start)
        pytest.fail('Physical residual cap was ignored')
    monkeypatch.setattr(probe, 'minimize' if optimizer == 'lbfgsb' else 'least_squares', exhaust)
    result = probe.alternative_fit(optimizer)(problem)
    assert result['evaluations'] == len(problem.calls) == 625
    assert result['budget_exhausted'] is True and result['scipy_result'] is None
    assert result['converged'] is False
    assert result['stopped'] == 'physical residual call cap reached'
    assert result['solution_origin'] == 'lowest evaluated score after physical call cap'


@pytest.mark.parametrize('stop', ['fake', 'iteration_budget'])
def test_namespace_instrumentation_counts_both_arms_without_mutation(tmp_path, monkeypatch, stop):
    original_transform = probe.transform
    def transform(rounds):
        return original_transform(rounds, SYNTHETIC, {},
                                   hashlib.sha256(SYNTHETIC.encode()).hexdigest())
    monkeypatch.setattr(probe, 'transform', transform)
    monkeypatch.setattr(probe.prediction, 'fit',
                        lambda *args, **kwargs: dict(evaluations=7, stopped=stop))
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
    assert counts['optimizer_final_metadata_calculations'] == 6
    assert counts['optimizer_budget_exhaustions'] == (6 if stop == 'iteration_budget' else 0)
    assert counts['optimizer_reported_convergences'] is None
    assert probe.work_counts(tmp_path, 'oracle')['optimizer_evaluations'] is None


@pytest.mark.parametrize('optimizer', ['lbfgsb', 'trf'])
def test_alternative_injection_is_private_and_both_arms_keep_full_policy(
    tmp_path, monkeypatch, optimizer
):
    original_transform = probe.transform
    source = SYNTHETIC.replace('fit(None', "fit(d['problem']")
    monkeypatch.setattr(probe, 'transform', lambda rounds: original_transform(
        rounds, source, {}, hashlib.sha256(source.encode()).hexdigest()))
    original_fit = probe.prediction.fit
    original_training = probe.predictive_annotation.annotate_fold.__globals__['fit_training']
    receipts = tmp_path / 'training-receipts'
    receipts.mkdir()
    operation, _, _ = probe.annotation_operation(5, receipts, optimizer=optimizer)
    training = operation.__globals__['annotate_fold'].__globals__['fit_training']
    for arm in probe.prediction.ARMS:
        result = training(dict(problem=QuadraticProblem([.2, -.3])), {}, [], arm)
        assert len(result[2]['history']) == 5
    assert probe.prediction.fit is original_fit
    assert (probe.predictive_annotation.annotate_fold.__globals__['fit_training']
            is original_training)
    counts = probe.work_counts(tmp_path, 'clone')
    assert counts['completed_rounds'] == counts['optimizer_calls_started'] == 10
    records = next(iter(counts['per_pid'].values()))
    assert {r['arm'] for r in records} == set(probe.prediction.ARMS)
    assert all(r['optimizer_policy'] == probe.optimizer_policy(optimizer) for r in records)
    assert all(r['phase_rounds'] == 5 and r['approximation'] for r in records)
    with pytest.raises(ValueError, match='all five'):
        probe.annotation_operation(3, optimizer=optimizer)


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


@pytest.mark.parametrize('optimizer', ['gn', 'lbfgsb', 'trf'])
def test_plan_binds_optimizer_approximation_and_work_budget(tmp_path, monkeypatch, optimizer):
    assert probe.main(cli_inputs(tmp_path, monkeypatch) + ['--optimizer', optimizer]) == 0
    plan = json.loads((tmp_path / 'out' / 'plan.json').read_bytes())
    assert plan['optimizer'] == optimizer
    assert plan['optimizer_policy'] == probe.optimizer_policy(optimizer)
    assert plan['approximation'] is (optimizer != 'gn')
    assert plan['approximation_policy'] == dict(phase_round_cut=False,
                                               optimizer_replacement=optimizer != 'gn')
    assert '625' in plan['work_budget_semantics']
    assert 'both arms' in plan['calibration_policy']


def test_reference_qualification_requires_current_policy_and_gn5_oracle_chain():
    receipt = dict(request_sha256='request', target=0, manifest_sha256='manifest',
                   modules={}, bindings={'source': 'current'}, rounds=5, optimizer='gn',
                   optimizer_policy=probe.optimizer_policy('gn'), mode='oracle')
    plan = dict(receipt)
    probe.qualify_reference(receipt, plan)
    plan['optimizer'] = 'trf'
    with pytest.raises(ValueError, match='full5 oracle proof'):
        probe.qualify_reference(receipt, plan)
    receipt.update(mode='clone', full5_oracle_exact=True)
    probe.qualify_reference(receipt, plan)
    for changes in [dict(full5_oracle_exact=False), dict(optimizer='trf'), dict(rounds=3),
                    dict(bindings={'source': 'old'}), dict(optimizer_policy={})]:
        with pytest.raises(ValueError, match='full5 oracle proof'):
            probe.qualify_reference(dict(receipt, **changes), plan)


@pytest.mark.parametrize('extra', [['--timeout', '121'], ['--target', '-1'],
                                  ['--run'], ['--mode', 'oracle', '--rounds', '2'],
                                  ['--mode', 'oracle', '--optimizer', 'trf'],
                                  ['--rounds', '2', '--optimizer', 'lbfgsb']])
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
    def run(mode, rounds, name, reference=None, optimizer='gn'):
        call = args + ['--run', '--mode', mode, '--rounds', str(rounds),
                       '--output', str(tmp_path / name), '--optimizer', optimizer]
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
    original_operation = probe.annotation_operation
    def different_operation(rounds, receipts=None, optimizer='gn'):
        _, before, after = original_operation(rounds, receipts, optimizer=optimizer)
        changed = annotation()
        changed['result']['folds'][0]['proposals'][0]['arms']['c0']['training_objective'] = 9.
        return lambda *a, **k: changed, before, after
    monkeypatch.setattr(probe, 'annotation_operation', different_operation)
    for optimizer in ['lbfgsb', 'trf']:
        assert run('clone', 5, optimizer, 'clone5', optimizer=optimizer) == 0
        receipt, value = probe.read_reference(tmp_path / optimizer)
        assert receipt['approximation'] is True and receipt['full5_oracle_exact'] is False
        assert receipt['exact'] is False and receipt['rounds'] == 5
        assert receipt['optimizer'] == optimizer
    with pytest.raises(ValueError, match='Entire clone5 annotation differs'):
        run('clone', 5, 'different-gn5', 'oracle')
    assert not (tmp_path / 'different-gn5' / 'result.json').exists()
