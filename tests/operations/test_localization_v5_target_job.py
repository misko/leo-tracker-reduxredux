from copy import deepcopy

import pytest

from leo.analysis.localization_v4 import backend
from leo.contracts import localization_v5 as contract
from leo.contracts.digests import canonical_digest
from leo.operations import localization_v3_job
from leo.operations.localization_v5_job import execute, make_request, validate_request
from tests.operations.test_localization_v3_job import request_fixture
from tests.operations.test_localization_v5_job import saved
from tests.operations.test_localization_v5_policy_job import manifest as manifest


@pytest.mark.parametrize('training', [None, contract.ANNOTATION_FALLBACK_POLICY])
@pytest.mark.parametrize('controls', [None, contract.INCLUSION_CONTROL_POLICY])
@pytest.mark.parametrize('joint', [None, contract.JOINT_SCHEDULE_POLICY])
def test_schema5_preserves_all_legacy_request_variants(
    manifest, tmp_path, training, controls, joint
):
    original = request_fixture(tmp_path)
    options = dict(annotation_training_policy=training, inclusion_control_policy=controls,
                   joint_schedule_policy=joint)
    legacy = make_request(original, manifest, **options)
    assert legacy == make_request(original, manifest, recovery_target_limit=None, **options)
    request = make_request(original, manifest, recovery_target_limit=0, **options)
    assert request['schema_version'] == 5
    assert request['recovery_target_policy'] == contract.recovery_target_policy(0)
    assert validate_request(request) is request
    assert request['job']['identity'] != legacy['job']['identity']
    binding = dict(request=original, backend_manifest=manifest,
                   initial_control_policy=contract.INITIAL_CONTROL_POLICY)
    for key in ('annotation_training_policy', 'inclusion_control_policy',
                'joint_schedule_policy', 'recovery_target_policy'):
        if key in request:
            binding[key] = request[key]
    assert request['job']['identity']['run_id'] == 'v5-' + canonical_digest(binding)[7:47]


@pytest.mark.parametrize('limit', [-1, 9, True, 2., '2'])
def test_invalid_limit_never_becomes_a_request(manifest, tmp_path, limit):
    with pytest.raises(ValueError, match='target limit'):
        make_request(request_fixture(tmp_path), manifest, recovery_target_limit=limit)


@pytest.mark.parametrize('change', ['missing', 'extra', 'schema4', 'bool', 'policy'])
def test_schema5_rejects_ambiguous_or_unbound_policy(manifest, tmp_path, change):
    request = make_request(request_fixture(tmp_path), manifest, recovery_target_limit=4)
    if change == 'missing':
        del request['recovery_target_policy']
    elif change == 'extra':
        request['extra'] = True
    elif change == 'schema4':
        request['schema_version'] = 4
    elif change == 'bool':
        request['schema_version'] = True
    else:
        request['recovery_target_policy']['GPS_used'] = 0
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize('limit', [0, 4])
def test_saved_target_policy_resumes_without_native_inputs(manifest, tmp_path, monkeypatch, limit):
    request = make_request(request_fixture(tmp_path), manifest, recovery_target_limit=limit)
    saved(request)
    monkeypatch.setattr(localization_v3_job, 'read_bound', lambda *a: pytest.fail('No input read'))
    monkeypatch.setattr(backend, 'ProcessBound', lambda *a: pytest.fail('No native load on resume'))
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused',
                   resume_only=True)['resumed']
    altered = deepcopy(request)
    altered['recovery_target_policy'] = contract.recovery_target_policy(2)
    with pytest.raises(ValueError, match='different native request'):
        execute(altered, native_manifest=manifest, receipts=tmp_path / 'unused', resume_only=True)


def test_zero_limit_routes_to_inventory_and_is_bound_to_provenance(manifest, tmp_path, monkeypatch):
    request = make_request(request_fixture(tmp_path), manifest, recovery_target_limit=0)

    class Backend:
        def __init__(self, manifest, receipts):
            self.manifest = deepcopy(manifest)

        def __call__(self):
            pytest.fail('No numerical work in a routing test')

        def provenance(self):
            return {}

    monkeypatch.setattr(backend, 'ProcessBound', Backend)

    def run(job, **kwargs):
        assert kwargs['recovery_target_limit'] == 0
        assert type(kwargs['recovery_target_limit']) is int
        provenance = kwargs['extra_provenance']()
        assert provenance['recovery_target_policy'] == request['recovery_target_policy']
        return {'status': 'synthetic-complete'}

    monkeypatch.setattr(localization_v3_job, '_execute', run)
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')['status'] == (
        'synthetic-complete')
    evidence, _ = saved(request)

    def check(job, **kwargs):
        kwargs['check_saved'](evidence)
        evidence['audit']['recovery_inventory']['target_limit'] = 4
        with pytest.raises(ValueError, match='target selection'):
            kwargs['check_saved'](evidence)
        return {'status': 'checked'}

    monkeypatch.setattr(localization_v3_job, '_execute', check)
    result = execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')
    assert result['status'] == 'checked'
