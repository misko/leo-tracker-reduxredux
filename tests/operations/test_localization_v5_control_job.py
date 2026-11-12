from copy import deepcopy

import pytest

from leo.analysis.localization_v4 import backend
from leo.contracts import localization_v5
from leo.contracts.digests import canonical_digest
from leo.operations import localization_v3_job
from leo.operations.localization_v5_job import execute, make_request, validate_request
from tests.analysis.test_localization_v5_control_reuse import fixture, value
from tests.operations.test_localization_v3_job import request_fixture
from tests.operations.test_localization_v5_job import saved
from tests.operations.test_localization_v5_policy_job import manifest as manifest


@pytest.mark.parametrize('training', [None, localization_v5.ANNOTATION_TRAINING_POLICY,
                                     localization_v5.ANNOTATION_FALLBACK_POLICY])
def test_schema3_binds_independent_control_policy_without_changing_legacy(
    manifest, tmp_path, training
):
    original = request_fixture(tmp_path)
    legacy = make_request(original, manifest, annotation_training_policy=training)
    assert make_request(original, manifest, annotation_training_policy=training,
                        inclusion_control_policy=None) == legacy
    request = make_request(original, manifest, annotation_training_policy=training,
                           inclusion_control_policy=localization_v5.INCLUSION_CONTROL_POLICY)
    assert request['schema_version'] == 3
    assert request['inclusion_control_policy'] == localization_v5.inclusion_control_policy()
    assert ('annotation_training_policy' in request) is (training is not None)
    assert request['job']['identity'] != legacy['job']['identity']
    assert validate_request(request) is request
    binding = dict(request=original, backend_manifest=manifest,
                   initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY)
    if training:
        binding['annotation_training_policy'] = localization_v5.annotation_training_policy(training)
    assert legacy['job']['identity']['run_id'] == 'v5-' + canonical_digest(binding)[7:47]


@pytest.mark.parametrize('change', ['missing', 'extra', 'schema2', 'bool', 'policy'])
def test_schema3_requires_complete_descriptor(manifest, tmp_path, change):
    request = make_request(request_fixture(tmp_path), manifest,
                           inclusion_control_policy=localization_v5.INCLUSION_CONTROL_POLICY)
    if change == 'missing':
        del request['inclusion_control_policy']
    elif change == 'extra':
        request['extra'] = True
    elif change == 'schema2':
        request['schema_version'] = 2
    elif change == 'bool':
        request['schema_version'] = True
    else:
        request['inclusion_control_policy']['scan'] = 'omit geometry'
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize('training', [None, localization_v5.ANNOTATION_FALLBACK_POLICY])
def test_saved_schema3_resume_uses_no_native_inputs_or_work_artifacts(
    manifest, tmp_path, monkeypatch, training
):
    request = make_request(request_fixture(tmp_path), manifest, annotation_training_policy=training,
                           inclusion_control_policy=localization_v5.INCLUSION_CONTROL_POLICY)
    saved(request)
    monkeypatch.setattr(localization_v3_job, 'read_bound', lambda *a: pytest.fail('No input read'))
    monkeypatch.setattr(backend, 'ProcessBound', lambda *a: pytest.fail('No native load on resume'))
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused',
                   resume_only=True)['resumed']
    assert not (tmp_path / 'unused').exists()
    altered = deepcopy(request)
    del altered['inclusion_control_policy']
    altered['schema_version'] = 2 if training else 1
    with pytest.raises(ValueError, match='different native request'):
        execute(altered, native_manifest=manifest, receipts=tmp_path / 'unused', resume_only=True)


def test_explicit_factory_and_actual_work_are_bound_to_execution(manifest, tmp_path, monkeypatch):
    request = make_request(request_fixture(tmp_path), manifest,
                           inclusion_control_policy=localization_v5.INCLUSION_CONTROL_POLICY)

    class Backend:
        def __init__(self, manifest, receipts):
            self.manifest = deepcopy(manifest)

        def __call__(self):
            pytest.fail('No numerical backend in synthetic routing test')

        def provenance(self):
            return {}

    monkeypatch.setattr(backend, 'ProcessBound', Backend)

    def run(job, **kwargs):
        factory = kwargs['inclusion_control_factory']
        context, inventory, _ = fixture()
        context['scan'].bound = kwargs['bound']
        cache = factory()
        args = (True, 'fit_shared', context, inventory, 2, False)
        cache.pair(value, *args)
        cache.pair(value, *args)
        provenance = kwargs['extra_provenance']()
        assert provenance['inclusion_control_policy'] == request['inclusion_control_policy']
        counts = provenance['inclusion_control_work']['counts']
        assert counts['requests'] == 2 and counts['computed'] == counts['reused'] == 1
        assert counts['failed'] == counts['in_progress'] == 0
        assert 'annotation_training_fit' not in kwargs
        return {'status': 'fake-complete'}

    monkeypatch.setattr(localization_v3_job, '_execute', run)
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused') == {
        'status': 'fake-complete'}


def test_saved_control_work_is_required_independently_of_request_digest(
    manifest, tmp_path, monkeypatch
):
    request = make_request(request_fixture(tmp_path), manifest,
                           inclusion_control_policy=localization_v5.INCLUSION_CONTROL_POLICY)
    evidence, _ = saved(request)

    def run(job, **kwargs):
        kwargs['check_saved'](evidence)
        del evidence['provenance']['inclusion_control_work']
        with pytest.raises(ValueError, match='control work'):
            kwargs['check_saved'](evidence)
        return {'status': 'checked'}

    monkeypatch.setattr(localization_v3_job, '_execute', run)
    result = execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')
    assert result['status'] == 'checked'
