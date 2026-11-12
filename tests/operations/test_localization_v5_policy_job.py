"""Policy routing and resume tests use synthetic native provenance only."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from leo.analysis.localization_v4 import backend, native_bound
from leo.contracts import localization_v5
from leo.contracts.digests import canonical_digest
from leo.operations import localization_v3_job
from leo.operations.localization_v5_job import execute, make_request, validate_request
from tests.localization_v5_fixture import evidence_fixture
from tests.operations.test_localization_v3_job import request_fixture
from tests.operations.test_localization_v5_job import saved


@pytest.fixture
def manifest(monkeypatch):
    evidence, _ = evidence_fixture()
    value = evidence['provenance']['native_backend']['manifest']
    value.update(original_sha256=native_bound.ORIGINAL_SHA256,
                 flags=list(native_bound.FLAGS), sanitized=False,
                 ABI='SciPy LAPACKE LP64; C int32/char ABI; column-major=102')
    value['provider']['symbols'] = ['scipy_LAPACKE_' + name
                                  for name in ('dpotrf', 'dpotrs', 'dpotri', 'dpocon')]
    validate = backend.validate_manifest
    monkeypatch.setattr(backend, 'validate_manifest',
                        lambda manifest, **kwargs: validate(manifest, check_artifacts=False))

    def forbidden(*args, **kwargs):
        pytest.fail('Policy tests must not load or build native artifacts')

    for name in ('digest', 'provider', 'build'):
        monkeypatch.setattr(native_bound, name, forbidden)
    return value


def test_legacy_schema_bytes_and_run_id_are_preserved(manifest, tmp_path):
    original = request_fixture(tmp_path)
    expected_job = deepcopy(original)
    expected_job['identity']['run_id'] = 'v5-' + canonical_digest(dict(
        request=original, backend_manifest=manifest,
        initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY))[7:47]
    expected = dict(schema_version=1, algorithm=localization_v5.MODEL,
                    backend_manifest=manifest,
                    initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY,
                    job=expected_job)
    assert make_request(original, manifest) == expected
    assert canonical_digest(make_request(original, manifest, annotation_training_policy=None)) == (
        canonical_digest(expected))


def test_explicit_policy_has_distinct_request_and_run_identity(manifest, tmp_path):
    original = request_fixture(tmp_path)
    legacy = make_request(original, manifest)
    request = make_request(original, manifest,
                          annotation_training_policy=localization_v5.ANNOTATION_TRAINING_POLICY)
    assert request['schema_version'] == 2
    assert request['annotation_training_policy'] == localization_v5.annotation_training_policy()
    assert request['job']['identity'] != legacy['job']['identity']
    assert canonical_digest(request) != canonical_digest(legacy)
    assert validate_request(request) is request
    with pytest.raises(ValueError, match='Unknown'):
        make_request(original, manifest, annotation_training_policy='other')


@pytest.mark.parametrize('change', ['missing', 'extra', 'schema1', 'bool', 'option'])
def test_schema2_requires_exact_descriptor_and_keys(manifest, tmp_path, change):
    request = make_request(request_fixture(tmp_path), manifest,
                          annotation_training_policy=localization_v5.ANNOTATION_TRAINING_POLICY)
    if change == 'missing':
        del request['annotation_training_policy']
    elif change == 'extra':
        request['extra'] = True
    elif change == 'schema1':
        request['schema_version'] = 1
    elif change == 'bool':
        request['schema_version'] = True
    else:
        request['annotation_training_policy']['options']['maxiter'] = True
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize('policy', [None, localization_v5.ANNOTATION_TRAINING_POLICY,
                                  localization_v5.ANNOTATION_FALLBACK_POLICY])
def test_saved_resume_requires_matching_policy_without_native_inputs(manifest, tmp_path,
                                                                   monkeypatch, policy):
    request = make_request(request_fixture(tmp_path), manifest, annotation_training_policy=policy)
    saved(request)
    monkeypatch.setattr(localization_v3_job, 'read_bound',
                        lambda *args: pytest.fail('Resume must not read scientific inputs'))
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused',
                   resume_only=True)['resumed']
    changed = deepcopy(request)
    if policy is None:
        changed.update(schema_version=2,
                       annotation_training_policy=localization_v5.annotation_training_policy())
    else:
        changed['schema_version'] = 1
        del changed['annotation_training_policy']
    with pytest.raises(ValueError, match='different native request'):
        execute(changed, native_manifest=manifest, receipts=tmp_path / 'unused', resume_only=True)
    assert not (tmp_path / 'unused').exists()


@pytest.mark.parametrize('policy', [None, localization_v5.ANNOTATION_TRAINING_POLICY,
                                  localization_v5.ANNOTATION_FALLBACK_POLICY])
def test_only_explicit_policy_injects_fit_and_provenance(manifest, tmp_path, monkeypatch, policy):
    request = make_request(request_fixture(tmp_path), manifest, annotation_training_policy=policy)
    monkeypatch.setattr(backend, 'ProcessBound',
                        lambda *args: SimpleNamespace(provenance=lambda: {}))

    def run(job, **kwargs):
        assert kwargs['request_binding'] == request
        provenance = kwargs['extra_provenance']()
        if policy is None:
            assert 'annotation_training_fit' not in kwargs
            assert 'annotation_training_policy' not in provenance
        else:
            from leo.operations.localization_v5_training import ProcessTrainingFit

            assert isinstance(kwargs['annotation_training_fit'], ProcessTrainingFit)
            assert kwargs['annotation_training_fit'].policy == request['annotation_training_policy']
            assert provenance['annotation_training_policy'] == request['annotation_training_policy']
            assert provenance['annotation_training_work']['policy'] == (
                request['annotation_training_policy'])
        return {'status': 'fake-complete'}

    monkeypatch.setattr(localization_v3_job, '_execute', run)
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused') == {
        'status': 'fake-complete'}


@pytest.mark.parametrize('policy', [None, localization_v5.ANNOTATION_TRAINING_POLICY])
def test_saved_provenance_checks_policy_independently_of_request_digest(
    manifest, tmp_path, monkeypatch, policy
):
    request = make_request(request_fixture(tmp_path), manifest, annotation_training_policy=policy)
    monkeypatch.setattr(backend, 'ProcessBound',
                        lambda *args: SimpleNamespace(provenance=lambda: {}))

    def run(job, **kwargs):
        evidence = dict(provenance=dict(
            algorithm=localization_v5.MODEL, native_backend=dict(manifest=manifest),
            initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY))
        if policy is not None:
            evidence['provenance']['annotation_training_policy'] = (
                request['annotation_training_policy'])
        kwargs['check_saved'](evidence)
        if policy is None:
            evidence['provenance']['annotation_training_policy'] = (
                localization_v5.annotation_training_policy())
        else:
            del evidence['provenance']['annotation_training_policy']
        with pytest.raises(ValueError, match='different native backend'):
            kwargs['check_saved'](evidence)
        return {'status': 'checked'}

    monkeypatch.setattr(localization_v3_job, '_execute', run)
    result = execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')
    assert result['status'] == 'checked'


def test_execution_rejects_implementation_policy_with_changed_numeric_type(
    manifest, tmp_path, monkeypatch
):
    from leo.analysis.localization_v5.annotation_training import fit

    request = make_request(request_fixture(tmp_path), manifest,
                          annotation_training_policy=localization_v5.ANNOTATION_TRAINING_POLICY)
    changed = deepcopy(fit.policy)
    changed['options']['maxiter'] = 48.0
    monkeypatch.setattr(fit, 'policy', changed)
    monkeypatch.setattr(backend, 'ProcessBound', lambda *args: object())
    with pytest.raises(ValueError, match='annotation training policy'):
        execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')


def test_legacy_schema2_identity_and_fallback_identity_are_separate(manifest, tmp_path):
    original = request_fixture(tmp_path)
    legacy = make_request(original, manifest,
                          annotation_training_policy=localization_v5.ANNOTATION_TRAINING_POLICY)
    expected_binding = dict(request=original, backend_manifest=manifest,
                            initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY,
                            annotation_training_policy=dict(
                                id='lbfgsb-full5-625-v1', optimizer='lbfgsb', method='L-BFGS-B',
                                options=dict(maxiter=48, maxfun=625, eps=0.001,
                                             ftol=2.220446049250313e-9, gtol=1e-5,
                                             maxls=20, maxcor=10),
                                residual_call_cap=625, phase_rounds=5, position_steps=48,
                                history_kind='all residual evaluations including Jacobians'))
    assert legacy['job']['identity']['run_id'] == 'v5-' + canonical_digest(expected_binding)[7:47]
    fallback = make_request(original, manifest,
                            annotation_training_policy=localization_v5.ANNOTATION_FALLBACK_POLICY)
    assert fallback['schema_version'] == 2
    assert fallback['annotation_training_policy']['fallback']['iterations'] == 48
    assert fallback['job']['identity'] != legacy['job']['identity']
    assert validate_request(fallback) is fallback


@pytest.mark.parametrize('policy', [localization_v5.ANNOTATION_TRAINING_POLICY,
                                  localization_v5.ANNOTATION_FALLBACK_POLICY])
def test_saved_resume_never_loads_optimizer_or_work_receipts(
    manifest, tmp_path, monkeypatch, policy
):
    import builtins

    from leo.operations.localization_v5_training import ProcessTrainingFit

    request = make_request(request_fixture(tmp_path), manifest, annotation_training_policy=policy)
    saved(request)
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in ('leo.analysis.localization_v5.annotation_training',
                    'leo.analysis.localization_v5.annotation_fallback'):
            pytest.fail('Saved resume must not load either optimizer')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    monkeypatch.setattr(ProcessTrainingFit, '__init__',
                        lambda *args: pytest.fail('Saved resume must not create work receipts'))
    monkeypatch.setattr(ProcessTrainingFit, 'provenance',
                        lambda *args: pytest.fail('Saved resume must not read work receipts'))
    result = execute(request, native_manifest=manifest, receipts=tmp_path / 'unused',
                     resume_only=True)
    assert result['resumed']
    assert not (tmp_path / 'unused').exists()


def test_fresh_publication_retains_training_work_in_saved_result(manifest, tmp_path, monkeypatch):
    from leo.analysis.localization_v5 import annotation_fallback
    from leo.application import localization_v3_engine as engine
    from leo.application import localization_v3_result as projection
    from leo.storage.localization_v5 import LocalizationV5Store
    from tests.operations.test_localization_v5_training import fit, problem

    request = make_request(request_fixture(tmp_path), manifest,
                           annotation_training_policy=localization_v5.ANNOTATION_FALLBACK_POLICY)

    def fake_fit(*args, **kwargs):
        return fit(*args, **kwargs)

    fake_fit.policy = request['annotation_training_policy']
    monkeypatch.setattr(annotation_fallback, 'fit', fake_fit)
    monkeypatch.setattr(backend, 'ProcessBound', lambda *args: SimpleNamespace(
        provenance=lambda: dict(manifest=manifest, manifest_sha256=canonical_digest(manifest),
                                receipts=[])))
    monkeypatch.setattr(localization_v3_job, 'read_bound', lambda record: (
        {'source': {'session_id': 'session'}} if record == request['job']['native_input']
        else {'config': {}}))
    monkeypatch.setattr(localization_v3_job, 'source_bindings', lambda: {})
    evidence, pngs = evidence_fixture()

    def run(*args, **kwargs):
        kwargs['execution'].annotation_training_fit(problem())
        return dict(status='figures_ready', products=pngs)

    def project(*args, **kwargs):
        evidence.update(identity=kwargs['identity'], provenance=kwargs['provenance'])
        return evidence

    monkeypatch.setattr(engine, 'run_native', run)
    monkeypatch.setattr(projection, '_build_evidence', project)
    result = execute(request, native_manifest=manifest, receipts=tmp_path / 'work')
    assert result['status'] == 'complete'
    stored = LocalizationV5Store(request['job']['output_root']).load(
        request['job']['identity']['run_id'])
    work = stored['evidence']['provenance']['annotation_training_work']
    assert work['policy'] == request['annotation_training_policy']
    assert work['counts']['evaluations'] == 2
    assert work['counts']['optimizer_attempts'] == 2
    assert work['counts']['primary_failures'] == work['counts']['fallback_completed'] == 1
