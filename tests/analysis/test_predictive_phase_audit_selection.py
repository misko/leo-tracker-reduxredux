from audit_predictive_annotation_phase import selected


def test_predictive_phase_audit_preserves_curved_and_prior_audit_boundaries():
    rows=[dict(track_id=str(k),scopes='DS24',state='conditionally_supported_identity',phase_audit_source='') for k in range(5)]
    rows[1]['phase_audit_source']='previous';rows[2]['state']='ambiguous_identity';rows[3]['scopes']='automatic'
    members={str(k):k==4 for k in range(5)}
    assert selected(rows,members)==[rows[0]]
