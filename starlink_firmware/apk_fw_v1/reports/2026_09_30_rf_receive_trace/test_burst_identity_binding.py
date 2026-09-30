from burst_identity_binding import run


def test_mode1_burst_match_and_saturating_mismatch_counter():
    cases = run()['cases']
    assert len(cases) == 840
    assert sum(c['outcome'] == 'suppress_feedback' for c in cases) == 210
