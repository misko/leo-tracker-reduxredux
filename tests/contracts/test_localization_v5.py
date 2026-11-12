import pytest

from leo.contracts import localization_v3, localization_v4, localization_v5
from leo.contracts.digests import canonical_digest
from tests.localization_v5_fixture import evidence_fixture


def test_control_policy_is_explicit_and_independent():
    policy = localization_v5.inclusion_control_policy()
    assert policy['id'] == 'native-complete-controls-v1'
    assert policy['scope'] == 'one recovery invocation'
    assert policy['scan'] == 'all fields including geometry'
    assert localization_v5.validate_inclusion_control_policy(policy) is policy
    policy['normalized_lists'].clear()
    assert localization_v5.inclusion_control_policy()['normalized_lists'] == [
        'tracks', 'white', 'rx_basis']
    with pytest.raises(ValueError):
        localization_v5.validate_inclusion_control_policy(policy)
    with pytest.raises(ValueError, match='Unknown'):
        localization_v5.inclusion_control_policy('other')


def test_joint_schedule_policy_has_independent_complete_descriptor():
    policy = localization_v5.joint_schedule_policy()
    assert policy['id'] == 'defer-factorized-unless-retry-v1'
    assert policy['optimizer_and_phase_budgets'] == 'unchanged'
    assert localization_v5.validate_joint_schedule_policy(policy) is policy
    policy['order'].clear()
    assert localization_v5.joint_schedule_policy()['order'] == ['control', 'joint', 'factorized']
    with pytest.raises(ValueError):
        localization_v5.validate_joint_schedule_policy(policy)
    with pytest.raises(ValueError, match='Unknown'):
        localization_v5.joint_schedule_policy('other')


@pytest.mark.parametrize('limit', [0, 2, 4, 8])
def test_target_selection_policy_retains_the_declared_rf_prefix(limit):
    evidence, _ = evidence_fixture()
    original = ['a', 'b']
    policy = localization_v5.recovery_target_policy(limit)
    evidence['provenance']['recovery_target_policy'] = policy
    evidence['audit']['recovery_inventory'] = dict(target_limit=limit,
        original_selected_track_ids=original,
        selected_targets=[dict(track_id=tid) for tid in original[:limit]],
        policy_omitted_track_ids=original[limit:])
    assert policy['per_target_fit_and_audit_budget'] == 'unchanged'
    assert localization_v5.validate_evidence(evidence) is evidence


@pytest.mark.parametrize('failure', ['orphan', 'missing', 'limit', 'ids', 'order', 'omitted'])
def test_target_selection_rejects_hidden_or_inconsistent_omissions(failure):
    evidence, _ = evidence_fixture()
    evidence['provenance']['recovery_target_policy'] = localization_v5.recovery_target_policy(1)
    inventory = dict(target_limit=1, original_selected_track_ids=['a', 'b'],
                     selected_targets=[dict(track_id='a')], policy_omitted_track_ids=['b'])
    evidence['audit']['recovery_inventory'] = inventory
    if failure == 'orphan':
        del evidence['provenance']['recovery_target_policy']
    elif failure == 'missing':
        del inventory['original_selected_track_ids']
    elif failure == 'limit':
        inventory['target_limit'] = True
    elif failure == 'ids':
        inventory['selected_targets'][0]['track_id'] = 'other'
    elif failure == 'order':
        inventory['original_selected_track_ids'].reverse()
    else:
        inventory['policy_omitted_track_ids'].clear()
    with pytest.raises(ValueError, match='target selection'):
        localization_v5.validate_evidence(evidence)


@pytest.mark.parametrize('failure', [None, 'missing_work', 'orphaned_work', 'binding', 'counts'])
def test_joint_work_is_required_and_bound_when_explicitly_enabled(failure):
    evidence, _ = evidence_fixture()
    provenance = evidence['provenance']
    policy = localization_v5.joint_schedule_policy()
    provenance['joint_schedule_policy'] = policy
    provenance['joint_schedule_work'] = dict(
        schema_version=1, policy=localization_v5.joint_schedule_policy(),
        backend_manifest_sha256=provenance['native_backend']['manifest_sha256'],
        experiments=[], counts=localization_v5.joint_schedule_counts([]))
    if failure == 'missing_work':
        del provenance['joint_schedule_work']
    elif failure == 'orphaned_work':
        del provenance['joint_schedule_policy']
    elif failure == 'binding':
        provenance['joint_schedule_work']['backend_manifest_sha256'] = 'other'
    elif failure == 'counts':
        provenance['joint_schedule_work']['counts']['factorized_computed'] = 1
    if failure is None:
        assert localization_v5.validate_evidence(evidence) is evidence
    else:
        with pytest.raises(ValueError, match='[Jj]oint schedule work|Joint schedule aggregate'):
            localization_v5.validate_evidence(evidence)


def test_v5_outer_model_preserves_v4_native_backend_and_scientific_checks():
    evidence, _ = evidence_fixture()
    assert localization_v5.validate_evidence(evidence) is evidence
    backend = evidence['provenance']['native_backend']
    assert backend['manifest']['algorithm'] == localization_v4.MODEL
    assert {r['algorithm'] for r in backend['receipts']} == {localization_v4.MODEL}
    for contract in (localization_v3, localization_v4):
        with pytest.raises(ValueError):
            contract.validate_evidence(evidence)
    evidence['selected']['owners']['c0']['a'] = 12345
    with pytest.raises(ValueError):
        localization_v5.validate_evidence(evidence)


@pytest.mark.parametrize('failure', ['policy', 'algorithm', 'manifest', 'receipt'])
def test_v5_rejects_misbound_policy_outer_algorithm_or_native_identity(failure):
    evidence, _ = evidence_fixture()
    provenance = evidence['provenance']
    backend = provenance['native_backend']
    if failure == 'policy':
        provenance['initial_control_policy'] = 'other'
    elif failure == 'algorithm':
        provenance['algorithm'] = localization_v4.MODEL
    elif failure == 'manifest':
        backend['manifest']['algorithm'] = localization_v5.MODEL
        backend['manifest_sha256'] = canonical_digest(backend['manifest'])
    else:
        backend['receipts'][0]['algorithm'] = localization_v5.MODEL
    with pytest.raises(ValueError):
        localization_v5.validate_evidence(evidence)


def test_annotation_policy_is_independent_and_optional_for_existing_evidence():
    policy = localization_v5.annotation_training_policy()
    policy['options']['maxiter'] = 1
    assert localization_v5.annotation_training_policy()['options']['maxiter'] == 48
    evidence, _ = evidence_fixture()
    assert localization_v5.validate_evidence(evidence) is evidence
    evidence['provenance']['annotation_training_policy'] = (
        localization_v5.annotation_training_policy())
    assert localization_v5.validate_evidence(evidence) is evidence


def test_fallback_policy_has_independent_complete_budgets():
    descriptor = localization_v5.annotation_training_policy(
        localization_v5.ANNOTATION_FALLBACK_POLICY)
    assert descriptor == dict(
        id='lbfgsb-gn-fallback-full5-v1', optimizer='lbfgsb_with_reference_gn_fallback',
        phase_rounds=5, position_steps=48, primary=localization_v5.annotation_training_policy(),
        fallback=dict(optimizer='original_gn', iterations=48, residual_call_cap=625,
                      start='original phase start', trigger='primary not converged'),
        total_residual_call_cap=1250,
        history_kind='all physical residual evaluations across attempts')
    assert localization_v5.validate_annotation_training_policy(descriptor) is descriptor
    descriptor['primary']['options']['maxiter'] = 1
    assert localization_v5.annotation_training_policy()['options']['maxiter'] == 48
    with pytest.raises(ValueError, match='annotation training policy'):
        localization_v5.validate_annotation_training_policy(descriptor)
    with pytest.raises(ValueError, match='Unknown'):
        localization_v5.annotation_training_policy('unknown')


@pytest.mark.parametrize('field,value', [('total_residual_call_cap', True),
                                       ('phase_rounds', 5.0), ('position_steps', 47)])
def test_fallback_policy_rejects_changed_budget_types(field, value):
    descriptor = localization_v5.annotation_training_policy(
        localization_v5.ANNOTATION_FALLBACK_POLICY)
    descriptor[field] = value
    with pytest.raises(ValueError, match='annotation training policy'):
        localization_v5.validate_annotation_training_policy(descriptor)


@pytest.mark.parametrize('field,value', [
    ('id', 'other'), ('optimizer', 'gn'), ('method', 'BFGS'),
    ('residual_call_cap', True), ('phase_rounds', 5.0), ('position_steps', 47),
    ('history_kind', 'accepted iterations'), ('extra', 1),
])
def test_annotation_policy_rejects_changed_or_ambiguous_descriptor(field, value):
    evidence, _ = evidence_fixture()
    descriptor = localization_v5.annotation_training_policy()
    descriptor[field] = value
    evidence['provenance']['annotation_training_policy'] = descriptor
    with pytest.raises(ValueError, match='annotation training policy'):
        localization_v5.validate_evidence(evidence)


@pytest.mark.parametrize('field', list(localization_v5.annotation_training_policy()['options']))
@pytest.mark.parametrize('value', [True, None, '48', 0])
def test_annotation_policy_requires_exact_optimizer_options(field, value):
    descriptor = localization_v5.annotation_training_policy()
    descriptor['options'][field] = value
    with pytest.raises(ValueError, match='annotation training policy'):
        localization_v5.validate_annotation_training_policy(descriptor)
