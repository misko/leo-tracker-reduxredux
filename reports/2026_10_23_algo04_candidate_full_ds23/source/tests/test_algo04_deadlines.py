from finalize_algo04_deadlines import deadline_failure


def test_deadline_fallback_does_not_hide_failed_scientific_audits():
    assert deadline_failure(dict(status='failed',error="RuntimeError('TimeoutError(stage cap)')"))
    assert not deadline_failure(dict(status='failed',error='ValueError(gate replay mismatch)'))
    assert not deadline_failure(dict(status='reference_unqualified'))
