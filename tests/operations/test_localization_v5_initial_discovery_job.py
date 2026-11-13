from copy import deepcopy
from types import SimpleNamespace

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
@pytest.mark.parametrize('limit', [None, 0])
def test_schema6_preserves_old_requests_and_binds_initial_policy(
    manifest, tmp_path, training, controls, joint, limit
):
    original = request_fixture(tmp_path)
    options = dict(annotation_training_policy=training, inclusion_control_policy=controls,
                   joint_schedule_policy=joint, recovery_target_limit=limit)
    legacy = make_request(original, manifest, **options)
    assert legacy == make_request(original, manifest, initial_seed_policy=None,
                                  initial_ranking_policy=None, **options)
    request = make_request(original, manifest, initial_seed_policy='anchor-round-robin-v1',
                           initial_ranking_policy='warm-center-v1', **options)
    assert request['schema_version'] == 6
    assert request['initial_discovery_policy'] == dict(id='initial-discovery-v1',
        seed_policy='anchor-round-robin-v1', ranking_policy='warm-center-v1')
    assert validate_request(request) is request
    binding = dict(request=original, backend_manifest=manifest,
                   initial_control_policy=contract.INITIAL_CONTROL_POLICY)
    for key in ('annotation_training_policy', 'inclusion_control_policy',
                'joint_schedule_policy', 'recovery_target_policy', 'initial_discovery_policy'):
        if key in request:
            binding[key] = request[key]
    assert request['job']['identity']['run_id'] == 'v5-' + canonical_digest(binding)[7:47]
    assert request['job']['identity'] != legacy['job']['identity']


@pytest.mark.parametrize('seed,ranking', [('legacy', None), (None, 'legacy'),
                                       ('anchor-round-robin-v1', None),
                                       (None, 'warm-center-v1')])
def test_each_explicit_policy_binds_both_policy_names(manifest, tmp_path, seed, ranking):
    request = make_request(request_fixture(tmp_path), manifest,
                           initial_seed_policy=seed, initial_ranking_policy=ranking)
    assert request['schema_version'] == 6
    assert request['initial_discovery_policy'] == dict(id='initial-discovery-v1',
        seed_policy=seed or 'legacy', ranking_policy=ranking or 'legacy')


@pytest.mark.parametrize('field', ['initial_seed_policy', 'initial_ranking_policy'])
@pytest.mark.parametrize('value', ['unknown', False, 1, [], {}])
def test_unknown_initial_policy_fails_before_execution(manifest, tmp_path, field, value):
    with pytest.raises(ValueError, match='initial discovery policy'):
        make_request(request_fixture(tmp_path), manifest, **{field: value})


@pytest.mark.parametrize('change', ['missing', 'extra', 'schema5', 'bool', 'seed', 'ranking', 'id'])
def test_schema6_rejects_incomplete_or_unbound_policy(manifest, tmp_path, change):
    request = make_request(request_fixture(tmp_path), manifest, initial_seed_policy='legacy')
    if change == 'missing':
        del request['initial_discovery_policy']
    elif change == 'extra':
        request['extra'] = True
    elif change == 'schema5':
        request['schema_version'] = 5
    elif change == 'bool':
        request['schema_version'] = True
    else:
        request['initial_discovery_policy'][{'seed': 'seed_policy',
            'ranking': 'ranking_policy', 'id': 'id'}[change]] = 'unknown'
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize('seed,ranking', [('legacy', 'legacy'),
    ('anchor-round-robin-v1', 'legacy'), ('legacy', 'warm-center-v1'),
    ('anchor-round-robin-v1', 'warm-center-v1')])
def test_saved_initial_policy_resumes_without_inputs(manifest, tmp_path, monkeypatch,
                                                    seed, ranking):
    request = make_request(request_fixture(tmp_path), manifest,
                           initial_seed_policy=seed, initial_ranking_policy=ranking)
    saved(request)
    monkeypatch.setattr(localization_v3_job, 'read_bound', lambda *a: pytest.fail('No input read'))
    monkeypatch.setattr(backend, 'ProcessBound', lambda *a: pytest.fail('No native load on resume'))
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused',
                   resume_only=True)['resumed']
    altered = deepcopy(request)
    altered['initial_discovery_policy']['seed_policy'] = (
        'legacy' if seed != 'legacy' else 'anchor-round-robin-v1')
    with pytest.raises(ValueError, match='different native request'):
        execute(altered, native_manifest=manifest, receipts=tmp_path / 'unused', resume_only=True)


def test_initial_policy_reaches_execution_and_saved_provenance(manifest, tmp_path, monkeypatch):
    request = make_request(request_fixture(tmp_path), manifest,
                           initial_seed_policy='anchor-round-robin-v1',
                           initial_ranking_policy='warm-center-v1')
    monkeypatch.setattr(backend, 'ProcessBound', lambda *a: SimpleNamespace(provenance=lambda: {}))

    def run(job, **kwargs):
        assert kwargs['initial_discovery_policy'] == request['initial_discovery_policy']
        assert kwargs['extra_provenance']()['initial_discovery_policy'] == (
            request['initial_discovery_policy'])
        return {'status': 'routed'}

    monkeypatch.setattr(localization_v3_job, '_execute', run)
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')['status'] == (
        'routed')
    evidence, _ = saved(request)

    def check(job, **kwargs):
        kwargs['check_saved'](evidence)
        evidence['audit']['initial']['initial_discovery_policy']['seed_policy'] = 'legacy'
        with pytest.raises(ValueError, match='Initial discovery selection'):
            kwargs['check_saved'](evidence)
        return {'status': 'checked'}

    monkeypatch.setattr(localization_v3_job, '_execute', check)
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused')['status'] == (
        'checked')
