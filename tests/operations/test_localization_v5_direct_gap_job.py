"""Schema-seven direct-gap policy is opt-in and binds saved scientific evidence."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from leo.analysis.localization_v4 import backend
from leo.contracts import localization_v5
from leo.contracts.digests import canonical_digest
from leo.operations import localization_v3_job
from leo.operations.localization_v5_job import execute, make_request, validate_request
from leo.storage import localization_v5 as store_module
from tests.operations.test_localization_v3_job import request_fixture
from tests.operations.test_localization_v5_job import saved
from tests.operations.test_localization_v5_policy_job import manifest as manifest


def direct(original, manifest):
    return make_request(original, manifest, recovery_target_limit=0,
                        direct_gap_policy=localization_v5.DIRECT_GAP_POLICY)


def test_schema7_binds_identity_without_changing_omitted_policy(manifest, tmp_path):
    original = request_fixture(tmp_path)
    baseline = make_request(original, manifest, recovery_target_limit=0)
    assert baseline['schema_version'] == 5 and 'direct_gap_policy' not in baseline
    request = direct(original, manifest)
    assert request['schema_version'] == 7
    assert request['direct_gap_policy'] == localization_v5.direct_gap_policy()
    assert request['job']['identity']['run_id'] != baseline['job']['identity']['run_id']
    binding = dict(request=original, backend_manifest=manifest,
                   initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY,
                   recovery_target_policy=request['recovery_target_policy'],
                   direct_gap_policy=request['direct_gap_policy'])
    assert request['job']['identity']['run_id'] == 'v5-' + canonical_digest(binding)[7:47]
    assert validate_request(request) is request


@pytest.mark.parametrize('limit', [None, 1, 8])
def test_direct_policy_requires_explicit_zero_recovery_targets(manifest, tmp_path, limit):
    with pytest.raises(ValueError, match='explicit zero recovery targets'):
        make_request(request_fixture(tmp_path), manifest, recovery_target_limit=limit,
                     direct_gap_policy=localization_v5.DIRECT_GAP_POLICY)


@pytest.mark.parametrize('change', ['missing', 'schema6', 'boolean', 'limit', 'unknown'])
def test_schema7_rejects_incomplete_or_changed_policy(manifest, tmp_path, change):
    request = direct(request_fixture(tmp_path), manifest)
    if change == 'missing':
        del request['direct_gap_policy']
    elif change == 'schema6':
        request['schema_version'] = 6
    elif change == 'boolean':
        request['direct_gap_policy']['maximum_components'] = True
    elif change == 'limit':
        request['recovery_target_policy']['maximum_targets'] = 1
    else:
        request['direct_gap_policy']['id'] = 'unknown'
    with pytest.raises(ValueError):
        validate_request(request)


def test_saved_no_trigger_resumes_without_inputs_or_native(manifest, tmp_path, monkeypatch):
    request = direct(request_fixture(tmp_path), manifest)
    evidence, _ = saved(request)
    assert localization_v5.validate_evidence(evidence) is evidence
    monkeypatch.setattr(localization_v3_job, 'read_bound', lambda *args: pytest.fail('input read'))
    monkeypatch.setattr(backend, 'ProcessBound', lambda *args: pytest.fail('native load'))
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused',
                   resume_only=True)['resumed']
    altered = deepcopy(request)
    altered['direct_gap_policy']['selection'] = 'changed'
    with pytest.raises(ValueError):
        execute(altered, native_manifest=manifest, receipts=tmp_path / 'unused',
                resume_only=True)


def test_public_evidence_rejects_policy_drift_and_unsolicited_marker(manifest, tmp_path):
    request = direct(request_fixture(tmp_path), manifest)
    evidence, _ = saved(request)
    evidence['audit']['gap_recovery']['policy']['gap_s'] = 6
    with pytest.raises(ValueError, match='Direct gap selection'):
        localization_v5.validate_evidence(evidence)
    baseline = make_request(request_fixture(tmp_path), manifest, recovery_target_limit=0)
    old, _ = saved(baseline)
    old['audit']['gap_recovery'] = dict(policy=localization_v5.direct_gap_policy())
    with pytest.raises(ValueError, match='requires its explicit policy'):
        localization_v5.validate_evidence(old)


def test_direct_policy_reaches_execution_and_saved_check(manifest, tmp_path, monkeypatch):
    request = direct(request_fixture(tmp_path), manifest)
    evidence, _ = saved(request)
    monkeypatch.setattr(backend, 'ProcessBound', lambda *args: SimpleNamespace(provenance=lambda: {}))
    monkeypatch.setattr(store_module, 'LocalizationV5Store',
                        lambda *args: SimpleNamespace(receipt=lambda *args:
                            (_ for _ in ()).throw(FileNotFoundError())))

    def routed(job, **kwargs):
        assert kwargs['direct_gap_policy'] == request['direct_gap_policy']
        assert kwargs['recovery_target_limit'] == 0
        assert kwargs['extra_provenance']()['direct_gap_policy'] == request['direct_gap_policy']
        kwargs['check_saved'](evidence)
        evidence['audit']['gap_recovery']['policy']['minimum_points'] = 13
        with pytest.raises(ValueError, match='Direct gap selection'):
            kwargs['check_saved'](evidence)
        return dict(status='routed')

    monkeypatch.setattr(localization_v3_job, '_execute', routed)
    assert execute(request, native_manifest=manifest, receipts=tmp_path / 'unused') == (
        dict(status='routed'))
