from phy_timestamp import run


def test_pps_conversion_wraparound_and_invalid_state():
    cases = run()['cases']
    assert len(cases) == 360
    assert sum(c['status'] == 13 for c in cases) == 180
    assert all(c['output'] == 0xDEADBEEF for c in cases if c['status'] == 13)
