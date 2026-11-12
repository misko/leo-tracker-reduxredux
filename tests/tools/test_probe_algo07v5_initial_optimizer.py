import copy
import hashlib
import json
import pickle
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import probe_algo07v5_initial_optimizer as probe
import pytest


class TinyProblem:
    lower, upper = np.array([-2., -2.]), np.array([2., 2.])
    keep, labels = np.array([True, True]), np.array([0])

    def __init__(self, scan, node, sigma, fitted_c, *, reference=None):
        self.rows, self.alias, self.reference = node['seed']['rows'], node['aliases'], reference
        self.target = np.array([.2 if fitted_c else .1, -.1])

    def residual(self, x):
        return np.asarray(x) - self.target

    def calculate(self, x):
        residual = self.residual(x)
        return dict(conditional_residual_hz=residual,
                    normalization_constant=0., negative_twice_elbo=float(residual @ residual))

    def state(self, x):
        return dict(phases=np.array([.01]), endpoint=np.asarray(x))


def tiny_operation(optimizer, *, oracle=False):
    fit = probe.position.fit if optimizer == 'gn' else probe.annotation_fit
    refreshed = probe.private_clone(probe.position.refreshed, NormalPosition=TinyProblem, fit=fit)
    arm = probe.private_clone(probe.initial.fit_initial_arm, refreshed=refreshed,
        actual_metrics=lambda *args: dict(tracks=[dict(compatible=True, component='track',
                                                       candidate_index=0)]),
        extend_associations=lambda *args: dict(points=2))
    nodes = [dict(seed=dict(rows=[dict(candidate_index=0)], state={}), aliases=[i],
                  center_score=float(i)) for i in range(3)]
    base = probe.initial.initial_search if oracle else probe.initial_operation(optimizer)
    return probe.private_clone(base, fit_initial_arm=arm, NormalPosition=TinyProblem,
        fresh_discovery=lambda *args, **kwargs: copy.deepcopy(nodes),
        signature=lambda node: tuple(node['aliases']), zero_state=lambda scan: {},
        explore=lambda *args, **kwargs: (nodes[0]['seed'], dict(candidate_hypotheses=[])),
        AnchoredFamilies=lambda *args: SimpleNamespace(alias=[0]))


def tiny_result(optimizer='gn', *, oracle=False, mapper=map):
    scan = SimpleNamespace(search_region=SimpleNamespace(
        half_width_km=2., width_km=4., center=(0., 0.)))
    callbacks = []
    result = tiny_operation(optimizer, oracle=oracle)(
        scan, 40., map_branches=mapper, initial_control=probe.initial_control,
        on_branch=lambda choice: callbacks.append(choice['hypothesis']))
    assert callbacks == [0, 1, 2]
    return result


def test_private_clones_leave_runtime_globals_and_code_untouched():
    sources = probe.guarded_sources()
    assert set(sources) == set(probe.SOURCE_HASHES)
    before = [dict(f.__globals__) for f in (
        probe.position.refreshed, probe.initial.fit_initial_arm, probe.initial.initial_search)]
    operation = probe.initial_operation('lbfgsb')
    arm = operation.__globals__['fit_initial_arm']
    refreshed = arm.__globals__['refreshed']
    assert refreshed.__globals__['fit'] is probe.annotation_fit
    assert operation.__globals__['fit'] is probe.annotation_fit
    for clone, original, snapshot in zip((refreshed, arm, operation), (
            probe.position.refreshed, probe.initial.fit_initial_arm, probe.initial.initial_search),
            before, strict=True):
        assert clone.__code__ is original.__code__
        assert clone.__defaults__ == original.__defaults__
        assert clone.__kwdefaults__ == original.__kwdefaults__
        assert clone.__globals__ is not original.__globals__
        assert snapshot.keys() == original.__globals__.keys()
        assert all(value is original.__globals__[key] for key, value in snapshot.items())
    with pytest.raises(ValueError, match='existing global'):
        probe.private_clone(probe.position.fit, invented_binding=object())


def test_changed_source_requires_review(monkeypatch):
    monkeypatch.setitem(probe.SOURCE_HASHES, 'position.refreshed', 'changed')
    with pytest.raises(ValueError, match='Frozen initial-search source changed'):
        probe.guarded_sources()


def test_full_gn_clone_and_production_queue_are_bit_identical_to_oracle():
    oracle = tiny_result(oracle=True)
    cloned = tiny_result(mapper=probe.map_initial_branches)
    assert probe.fingerprint(oracle) == probe.fingerprint(cloned)
    assert probe.compare(oracle, cloned)['differences'] == []
    counts = probe.work_counts(cloned)
    assert counts['branch_arm_fits'] == 6
    assert counts['optimizer_calls'] == counts['optimizer_final_metadata_calculations'] == 30
    assert counts['additional_control_optimizer_calls'] == 0
    assert counts['stationarity_available'] == 0
    assert counts['reported_convergences'] is None
    for arm in probe.ARMS:
        assert probe.fingerprint(cloned['zero_phase_control'][arm]) == probe.fingerprint(
            cloned['choices'][0]['arms'][arm]['phase_rounds'][0]['fit'])


def test_lbfgsb_keeps_rounds_calls_objective_and_matched_arms():
    result = tiny_result('lbfgsb')
    counts = probe.work_counts(result)
    assert counts['optimizer_calls'] == 30
    assert counts['stationarity_available'] == 30
    assert counts['residual_evaluations'] == sum(
        epoch['fit']['evaluations'] for choice in result['choices'] for arm in probe.ARMS
        for epoch in choice['arms'][arm]['phase_rounds'])
    assert all(row['evaluations'] <= 625 for row in counts['per_fit'])
    for choice in result['choices']:
        for arm in probe.ARMS:
            value = choice['arms'][arm]
            expected = np.array([.2 if arm == 'fitted_c' else .1, -.1])
            np.testing.assert_allclose(value['fit']['parameters'], expected, atol=.002)
            residual = value['fit']['parameters'] - expected
            assert value['fit']['score'] == pytest.approx(residual @ residual)
    assert probe.compare(tiny_result(), result)['position_accuracy_evaluated'] is False
    assert probe.metrics(result)['branches'][0]['arms']['c0']['accepted_nominated_owners'] == [0]


def test_nomination_and_acceptance_changes_are_reported_separately():
    baseline = tiny_result()
    changed = copy.deepcopy(baseline)
    changed['choices'][0]['node']['aliases'][0] = 99
    changed['choices'][0]['arms']['c0']['metrics']['tracks'][0]['compatible'] = False
    changed['choices'][0]['arms']['c0']['all_graph_associations']['tracks'] = [
        dict(component='new', candidate_index=4, norad=44)]
    report = probe.compare(baseline, changed)
    assert report['branch_winner_equal'] is True
    assert report['nomination_equal'] is False
    assert report['nominated_acceptance_equal'] is False
    assert report['graph_owners_equal'] is False


def test_reference_requires_oracle_then_current_bound_qualified_gn():
    base = dict(status='complete', mode='oracle', optimizer='gn',
                optimizer_policy=probe.optimizer_policy('gn'), request_sha256='request',
                manifest_sha256='manifest', modules={}, bindings={}, source_hashes={})
    plan = dict(base, status='plan', mode='clone')
    probe.qualify_reference(base, plan)
    candidate = dict(plan, optimizer='lbfgsb')
    with pytest.raises(ValueError, match='cloned GN'):
        probe.qualify_reference(base, candidate)
    qualified = dict(base, mode='clone', oracle_exact=True, oracle_initial_sha256='oracle')
    probe.qualify_reference(qualified, candidate)
    for key in ('request_sha256', 'manifest_sha256', 'modules', 'bindings', 'source_hashes'):
        with pytest.raises(ValueError, match='same source and inputs'):
            probe.qualify_reference(qualified, dict(candidate, **{key: 'changed'}))
    with pytest.raises(ValueError):
        probe.qualify_reference(dict(qualified, oracle_exact=False), candidate)


def test_read_reference_checks_pickle_and_exact_fingerprint(tmp_path):
    result = tiny_result()
    raw = pickle.dumps(result)
    receipt = dict(status='complete', pickle_sha256=hashlib.sha256(raw).hexdigest(),
                   initial_sha256=probe.fingerprint(result))
    (tmp_path / 'result.json').write_text(json.dumps(receipt))
    (tmp_path / 'initial.pickle').write_bytes(raw)
    assert probe.fingerprint(probe.read_reference(tmp_path)[1]) == probe.fingerprint(result)
    (tmp_path / 'initial.pickle').write_bytes(raw + b'corrupt')
    with pytest.raises(ValueError, match='content-bound'):
        probe.read_reference(tmp_path)


def saved_inputs():
    job = dict(output_root='fake', identity=dict(run_id='run', dataset_id='dataset'),
               search_center=[1., 2.])
    request = dict(job=job)
    receipt = dict(job['identity'], result_sha256='archive')
    prepared = dict(noise=dict(scale=40.), marker='original preparation')
    evidence = dict(identity=job['identity'], preparation=prepared,
        provenance=dict(request_sha256=probe.canonical_digest(request),
                        configuration=dict(request=job)))
    saved = dict(evidence=evidence, receipt=receipt, sha256=probe.canonical_digest(receipt))
    return request, job, saved


def test_load_scan_binds_saved_evidence_and_uses_original_context(monkeypatch):
    request, job, saved = saved_inputs()
    calls, scan, backend = [], object(), object()

    def context(prepared, region, noise_sha256, **kwargs):
        calls.append((prepared, region.center, noise_sha256, kwargs))
        return scan

    monkeypatch.setattr(probe, '_context', context)
    def store(root):
        return SimpleNamespace(load=lambda run_id: saved)
    actual, scientific = probe.load_scan(request, job, store, backend)
    assert actual is scan
    assert calls[0][0] is saved['evidence']['preparation']
    assert calls[0][1] == (1., 2.)
    assert calls[0][3] == dict(genuine=True, bound=backend)
    assert scientific['receipt_sha256'] == saved['sha256']
    saved['receipt']['dataset_id'] = 'other'
    with pytest.raises(ValueError, match='binding mismatch'):
        probe.load_scan(request, job, store, backend)
    assert len(calls) == 1


@pytest.fixture
def cli_inputs(tmp_path, monkeypatch):
    request, manifest = tmp_path / 'request.json', tmp_path / 'manifest.json'
    request.write_text('{}')
    manifest.write_text('{}')
    monkeypatch.setattr(probe, 'request_inputs', lambda path: ({}, {}, object()))
    monkeypatch.setattr(probe, 'read_manifest', lambda path: {})
    monkeypatch.setattr(probe, 'validate_manifest', lambda value: value)
    monkeypatch.setattr(probe, 'source_binding', lambda root: dict(files={'all': 'bound'}))
    return ['--request', str(request), '--native-manifest', str(manifest),
            '--output', str(tmp_path / 'output')]


def test_plan_never_loads_archive_or_constructs_context(cli_inputs, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('Plan opened the archive or constructed native context')

    monkeypatch.setattr(probe, 'load_scan', forbidden)
    monkeypatch.setattr(probe, 'ProcessBound', forbidden)
    assert probe.main(cli_inputs) == 0
    plan = json.loads((tmp_path / 'output' / 'plan.json').read_text())
    assert plan['phase_rounds'] == 5 and plan['position_steps'] == 48
    assert plan['seed_budget'] == 4 and plan['branch_budget'] == 3
    assert not (tmp_path / 'output' / 'result.json').exists()


def test_inner_deadline_failure_is_honest_and_never_complete(
    cli_inputs, monkeypatch, tmp_path
):
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {0, 1, 2})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')

    @contextmanager
    def deadline(seconds):
        assert seconds == 120
        raise TimeoutError('synthetic deadline')
        yield

    monkeypatch.setattr(probe, 'stage_deadline', deadline)
    with pytest.raises(TimeoutError):
        probe.main(cli_inputs + ['--mode', 'oracle', '--run'])
    failure = json.loads((tmp_path / 'output' / 'failure.json').read_text())
    assert failure['status'] == 'failed' and failure['error'] == 'TimeoutError'
    assert not (tmp_path / 'output' / 'result.json').exists()


def test_fake_cli_complete_path_uses_default_ports_and_binds_all_sources_twice(
    cli_inputs, monkeypatch, tmp_path
):
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {0, 1, 2})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    bindings = []

    def bound(root):
        bindings.append(root)
        assert probe.annotation_fit.policy['residual_call_cap'] == 625
        return dict(files={'all': 'bound'})

    monkeypatch.setattr(probe, 'source_binding', bound)
    monkeypatch.setattr(probe, 'ProcessBound', lambda *args: SimpleNamespace(provenance=lambda: {}))
    monkeypatch.setattr(probe, 'load_scan', lambda *args: (
        SimpleNamespace(radio_sigma_hz=40.), dict(original_scan='bound')))
    result = tiny_result()
    calls = []

    def operation(scan, sigma, **options):
        calls.append(options)
        for choice in result['choices']:
            options['on_branch'](choice)
        return result

    monkeypatch.setattr(probe, 'guarded_sources', lambda: {})
    monkeypatch.setattr(probe.initial, 'initial_search', operation)
    assert probe.main(cli_inputs + ['--mode', 'oracle', '--run']) == 0
    assert len(bindings) == 2 and bindings[0] == bindings[1]
    assert calls[0]['map_branches'] is probe.map_initial_branches
    assert calls[0]['initial_control'] is probe.initial_control
    assert set(calls[0]) == {'map_branches', 'initial_control', 'on_branch'}
    receipt = json.loads((tmp_path / 'output' / 'result.json').read_text())
    assert receipt['callback_order'] == [0, 1, 2]
    assert receipt['work_counts']['optimizer_calls'] == 30
    assert receipt['preparation_seconds'] >= 0 and receipt['initial_seconds'] >= 0
    assert len(receipt['initial_cpu_seconds']) == 2


def test_invalid_clone_and_resource_requests_fail_before_archive(
    cli_inputs, monkeypatch, tmp_path
):
    with pytest.raises(SystemExit):
        probe.main(cli_inputs + ['--run'])
    assert not (tmp_path / 'output').exists()
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {0, 1})
    with pytest.raises(ValueError, match='exactly three CPUs'):
        probe.main(cli_inputs + ['--mode', 'oracle', '--run'])
