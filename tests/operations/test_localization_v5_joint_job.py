from copy import deepcopy

import pytest

from leo.analysis.localization_v4 import backend
from leo.contracts import localization_v5
from leo.contracts.digests import canonical_digest
from leo.operations import localization_v3_job
from leo.operations.localization_v5_job import execute, make_request, validate_request
from tests.analysis.test_localization_v5_control_reuse import fixture
from tests.analysis.test_localization_v5_joint_schedule import experiment
from tests.operations.test_localization_v3_job import request_fixture
from tests.operations.test_localization_v5_job import saved
from tests.operations.test_localization_v5_policy_job import manifest as manifest


@pytest.mark.parametrize('training', [None, localization_v5.ANNOTATION_FALLBACK_POLICY])
@pytest.mark.parametrize('controls', [None, localization_v5.INCLUSION_CONTROL_POLICY])
def test_schema4_is_independent_and_preserves_existing_request_identities(
    manifest, tmp_path, training, controls
):
    original = request_fixture(tmp_path)
    options = dict(annotation_training_policy=training, inclusion_control_policy=controls)
    legacy = make_request(original, manifest, **options)
    assert legacy == make_request(original, manifest, joint_schedule_policy=None, **options)
    request = make_request(original, manifest,
                           joint_schedule_policy=localization_v5.JOINT_SCHEDULE_POLICY, **options)
    assert request['schema_version'] == 4
    assert request['joint_schedule_policy'] == localization_v5.joint_schedule_policy()
    assert validate_request(request) is request
    assert request['job']['identity'] != legacy['job']['identity']
    binding = dict(request=original, backend_manifest=manifest,
                   initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY,
                   joint_schedule_policy=request['joint_schedule_policy'])
    for name in ('annotation_training_policy', 'inclusion_control_policy'):
        if name in request:
            binding[name] = request[name]
    assert request['job']['identity']['run_id'] == 'v5-' + canonical_digest(binding)[7:47]


@pytest.mark.parametrize('change', ['missing', 'extra', 'schema3', 'bool', 'order'])
def test_schema4_requires_the_complete_explicit_policy(manifest, tmp_path, change):
    request = make_request(request_fixture(tmp_path), manifest,
                           joint_schedule_policy=localization_v5.JOINT_SCHEDULE_POLICY)
    if change == 'missing':
        del request['joint_schedule_policy']
    elif change == 'extra':
        request['extra'] = True
    elif change == 'schema3':
        request['schema_version'] = 3
    elif change == 'bool':
        request['schema_version'] = True
    else:
        request['joint_schedule_policy']['order'].reverse()
    with pytest.raises(ValueError):
        validate_request(request)


def test_saved_schema4_resumes_without_loading_native_artifacts_or_inputs(
    manifest, tmp_path, monkeypatch
):
    request = make_request(request_fixture(tmp_path), manifest,
                           annotation_training_policy=localization_v5.ANNOTATION_FALLBACK_POLICY,
                           inclusion_control_policy=localization_v5.INCLUSION_CONTROL_POLICY,
                           joint_schedule_policy=localization_v5.JOINT_SCHEDULE_POLICY)
    saved(request)
    monkeypatch.setattr(localization_v3_job, 'read_bound', lambda *a: pytest.fail('No input read'))
    monkeypatch.setattr(backend, 'ProcessBound', lambda *a: pytest.fail('No native load on resume'))
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused',
                   resume_only=True)['resumed']
    assert not (tmp_path / 'unused').exists()
    altered = deepcopy(request)
    del altered['joint_schedule_policy']
    altered['schema_version'] = 3
    with pytest.raises(ValueError, match='different native request'):
        execute(altered, native_manifest=manifest, receipts=tmp_path / 'unused', resume_only=True)


def test_execution_owns_the_factory_and_saved_work_is_bound_and_required(
    manifest, tmp_path, monkeypatch
):
    request = make_request(request_fixture(tmp_path), manifest,
                           joint_schedule_policy=localization_v5.JOINT_SCHEDULE_POLICY)

    class Backend:
        def __init__(self, manifest, receipts):
            self.manifest = deepcopy(manifest)

        def __call__(self):
            pytest.fail('No numerical backend in a routing test')

        def provenance(self):
            return {}

    monkeypatch.setattr(backend, 'ProcessBound', Backend)

    def run(job, **kwargs):
        factory = kwargs['joint_schedule_factory']
        context, _, _ = fixture()
        context['scan'].bound = kwargs['bound']
        schedule = factory(context, 'lbfgsb')
        values = experiment()
        assert schedule.omit_factorized(values)
        values['factorized'] = {}
        schedule.finish(values, True)
        provenance = kwargs['extra_provenance']()
        assert provenance['joint_schedule_policy'] == request['joint_schedule_policy']
        assert provenance['joint_schedule_work']['counts']['factorized_omitted'] == 1
        assert provenance['joint_schedule_work']['counts']['factorized_computed'] == 0
        assert 'inclusion_control_factory' not in kwargs
        assert 'annotation_training_fit' not in kwargs
        return {'status': 'synthetic-complete'}

    monkeypatch.setattr(localization_v3_job, '_execute', run)
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')['status'] == (
        'synthetic-complete')
    evidence, _ = saved(request)

    def check(job, **kwargs):
        kwargs['check_saved'](evidence)
        del evidence['provenance']['joint_schedule_work']
        with pytest.raises(ValueError, match='joint schedule work'):
            kwargs['check_saved'](evidence)
        return {'status': 'checked'}

    monkeypatch.setattr(localization_v3_job, '_execute', check)
    result = execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')
    assert result['status'] == 'checked'
