from umac_missing_identity import run


def test_absent_target_identity_defaults_to_zero_on_successful_path():
    cases = run()['cases']
    assert len(cases) == 140
    assert all(c['output'] == 0 for c in cases if not c['present'])
