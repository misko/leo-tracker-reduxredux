from grant_timing_gate import run


def test_queued_grant_session_and_modulo_boundary_decisions():
    result = run()
    assert result["case_count"] == 6000
    assert result["outcome_counts"] == {
        "stale_session": 3000, "handle_now": 4, "future": 252, "invalid_time": 2744}
