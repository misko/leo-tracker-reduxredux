from audit_annotation_likelihood_roles import next_action,describe


def test_old_supported_record_is_not_predictive_support():
    d=dict(role='older_calibration_participating',status='conditionally_supported_identity')
    assert next_action({},d)=='needs_predictive_role_assessment_in_primary_ledger'
    assert next_action({},dict(d,role='predictive_only'))=='supported_predictive_identity_needs_inclusion_source'


def test_secondary_evidence_requires_reconciliation():
    d=dict(role='older_calibration_participating',status='conditionally_supported_identity')
    assert next_action(dict(predictive_role_status='unstable_identity'),d)=='reconcile_separate_role_or_fragment_evidence'
    assert next_action(dict(bundle_inclusion_source='/example'),d)=='review_recorded_inclusion'


def test_empty_predictive_result_is_insufficient_not_supported():
    d=describe(dict(folds=[],inclusion_mode='predictive_only',identity_score_name='conditional_target'))
    assert d['role']=='predictive_only' and d['status']=='insufficient_partitions'
