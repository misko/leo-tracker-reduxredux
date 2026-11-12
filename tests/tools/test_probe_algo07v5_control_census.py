import json
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import probe_algo07v5_control_census as probe
import pytest

from leo.analysis.localization_v3 import recovery_controller
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.contracts.digests import canonical_digest
from tests.analysis.test_localization_v3_recovery_controller import execute, setup


class Backend:
    manifest = {'scientific_backend': 'tiny'}

    def __init__(self, *args):
        self.manifest = deepcopy(type(self).manifest)

    def __call__(self):
        raise AssertionError('No numerical backend should execute in these tests')

    def provenance(self):
        return {}


def fixture():
    bound = Backend()
    scan = object.__new__(ScanLikelihood)
    scan.bound = bound
    scan.tracks, scan.white, scan.rx_basis = [[1], [2]], [1, 2], [3, 4]
    scan.geometry = {'position': np.array([1., 2.])}
    scan.previous_shape_cache = {'calibration': [3.]}
    context = dict(scan=scan, node={}, keep=[True], powers=[1.], means=[0.],
                   model={}, entries=[])
    return context, {'policy': {}}, bound


def key(context, inventory, backend, kind='fit_shared', count=2, option=False):
    return probe.prospective_key(kind, context, inventory, count, option,
                                 backend, canonical_digest(backend.manifest))


def test_key_retains_geometry_and_mutable_scientific_fields():
    context, inventory, backend = fixture()
    original = key(context, inventory, backend)
    assert original is not None
    context['scan'].geometry['position'][0] += .1
    assert key(context, inventory, backend) != original
    context['scan'].geometry['position'][0] -= .1
    original = key(context, inventory, backend)
    context['scan'].previous_shape_cache['calibration'][0] += .1
    assert key(context, inventory, backend) != original
    for name in ('node', 'keep', 'powers', 'means', 'model', 'entries'):
        changed = dict(context, **{name: [{'track_index': 0}] if name == 'entries' else [7.]})
        assert key(changed, inventory, backend) != key(context, inventory, backend)
    assert key(context, {'policy': {'changed': True}}, backend) != key(context, inventory, backend)
    assert key(context, inventory, backend, kind='fit_new') != key(context, inventory, backend)


def test_appended_target_lists_normalize_without_changing_context():
    context, inventory, backend = fixture()
    original = key(context, inventory, backend)
    for name in ('tracks', 'white', 'rx_basis'):
        getattr(context['scan'], name).append('target-only')
    assert key(context, inventory, backend) == original
    census = probe.ControlCensus(backend)
    assert census.context(context, 'fit_shared', False) is context
    assert 'geometry' in vars(context['scan'])


@pytest.mark.parametrize('change', [
    'numerical', 'factory', 'other_callback', 'unknown_value', 'unknown_bound', 'entries',
])
def test_unsafe_paths_are_not_keyed(change):
    context, inventory, backend = fixture()
    if change == 'numerical':
        context['numerical_policy'] = object()
    elif change == 'factory':
        context['problem_factory'] = lambda: None
    elif change == 'other_callback':
        context['scan'].custom = lambda: None
    elif change == 'unknown_value':
        context['scan'].custom = object()
    elif change == 'unknown_bound':
        context['scan'].bound = Backend()
    else:
        context['entries'] = [dict(track_index=2)]
    assert key(context, inventory, backend) is None


def test_refresh_and_bad_counts_are_not_keyed_and_binding_changes_reject():
    context, inventory, backend = fixture()
    assert key(context, inventory, backend, option=True) is None
    assert key(context, inventory, backend, count=0) is None
    assert key(context, inventory, backend, count=3) is None
    binding = canonical_digest(backend.manifest)
    backend.manifest['changed'] = True
    with pytest.raises(ValueError, match='binding changed'):
        probe.prospective_key('fit_new', context, inventory, 2, 'powell', backend, binding)


def test_duplicate_controls_are_recomputed_and_saved_pairs_are_isolated():
    context, inventory, backend = fixture()
    census, calls = probe.ControlCensus(backend), []

    def compute():
        calls.append(1)
        return {'c0': np.array([1.]), 'fitted_c': np.array([2.])}

    args = (True, 'fit_shared', context, inventory, 2, False)
    first = census.pair(compute, *args)
    first['c0'][0] = 99
    second = census.pair(compute, *args)
    assert second['c0'][0] == 1
    assert len(calls) == 2
    assert census.summary()['duplicates'] == 1
    assert census.summary()['cache_reuse'] is False
    assert all(not row['reused'] for row in census.rows)
    with pytest.raises(ValueError, match='different complete control pairs'):
        census.pair(lambda: {'changed': True}, *args)
    assert len(census.rows) == 2


def test_noncontrols_do_not_enter_census():
    context, inventory, backend = fixture()
    census = probe.ControlCensus(backend)
    value = object()
    assert census.pair(lambda: value, False, 'fit_new', context, inventory, 2, 'lbfgsb') is value
    assert census.rows == []


def test_already_working_cache_cannot_be_counted_as_new_work(monkeypatch):
    context, inventory, backend = fixture()
    census = probe.ControlCensus(backend)
    monkeypatch.setattr(probe.inclusion_controls, 'control_key', lambda *args: 'working')
    with pytest.raises(ValueError, match='bypass no longer holds'):
        census.pair(lambda: pytest.fail('Must abort before fitting'),
                    True, 'fit_new', context, inventory, 2, 'lbfgsb')


def test_controller_clone_keeps_complete_ordered_recovery(monkeypatch):
    evidence = setup(monkeypatch, shared=True)
    original = recovery_controller.recover_tracks
    expected = original({}, evidence, run_stage=execute, discovery_allowed=lambda: True)
    census = probe.ControlCensus(Backend())
    clone = probe.controller(census)
    actual = clone({}, evidence, run_stage=execute, discovery_allowed=lambda: True)
    assert probe.fingerprint(actual) == probe.fingerprint(expected)
    assert clone.__code__ is original.__code__
    assert clone.__defaults__ is original.__defaults__
    assert (original.__globals__['InclusionControlCache']
            is probe.inclusion_controls.InclusionControlCache)


@pytest.fixture
def cli(monkeypatch, tmp_path):
    manifest = deepcopy(Backend.manifest)
    request = {'backend_manifest': manifest}
    job = dict(output_root='unused', identity={'run_id': 'tiny'})
    expected = {'tiny': np.array([1., 2.])}
    def store(_):
        return SimpleNamespace(load=lambda _: {
            'evidence': {'audit': {'predictive_recovery': expected}}})
    monkeypatch.setattr(probe, 'request_inputs', lambda _: (request, job, store))
    monkeypatch.setattr(probe, 'validate_manifest', lambda value: value)
    monkeypatch.setattr(probe, 'ProcessBound', Backend)
    monkeypatch.setattr(probe, 'source_binding', lambda _: {'tiny': 'source'})
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda _: {0, 1, 2})
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    request_path, manifest_path = tmp_path / 'request.json', tmp_path / 'manifest.json'
    request_path.write_text('{}')
    manifest_path.write_text(json.dumps(manifest))
    args = ['--request', str(request_path), '--native-manifest', str(manifest_path),
            '--output', str(tmp_path / 'output')]
    return args, tmp_path / 'output', expected


def test_default_cli_plans_without_loading_scientific_archive(monkeypatch, cli):
    args, output, _ = cli
    monkeypatch.setattr(probe, 'load_context', lambda *args: pytest.fail('No archive in plan'))
    assert probe.main(args) == 0
    assert (output / 'plan.json').is_file()
    assert not (output / 'recovery.pickle').exists()


def test_run_cli_requires_complete_saved_audit_equality(monkeypatch, cli):
    args, output, expected = cli
    monkeypatch.setattr(probe, 'load_context', lambda *args: ({}, {}, {'receipt': 'tiny'}))
    monkeypatch.setattr(probe, 'controller', lambda census: lambda *args, **kwargs: expected)
    assert probe.main([*args, '--run']) == 0
    result = json.loads((output / 'result.json').read_text())
    assert result['saved_audit_exact'] is True
    assert result['summary']['cache_reuse'] is False
    assert result['summary']['geometry_fingerprinted'] is True


def test_run_cli_retains_mismatch_as_failure(monkeypatch, cli):
    args, output, _ = cli
    monkeypatch.setattr(probe, 'load_context', lambda *args: ({}, {}, {'receipt': 'tiny'}))
    monkeypatch.setattr(probe, 'controller',
                        lambda census: lambda *args, **kwargs: {'changed': True})
    with pytest.raises(ValueError, match='differs from the saved native audit'):
        probe.main([*args, '--run'])
    assert (output / 'failure.json').is_file()
    assert not (output / 'result.json').exists()
