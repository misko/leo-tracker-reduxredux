from phy_feedback_route import run


def test_type7_uses_supplied_length_at_phy_boundary():
    cases = run()['cases']
    assert len(cases) == 30
    assert sum(c['outcome'] == 'rf_info_length_admitted' for c in cases) == 2
