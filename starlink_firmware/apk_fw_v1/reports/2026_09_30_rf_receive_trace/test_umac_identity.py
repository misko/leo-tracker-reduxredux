from umac_identity import run


def test_umac_present_absent_and_global_identity_paths():
    rows = run()['cases']
    assert len(rows) == 105
    absent = [r for r in rows if r.get('present') == 0]
    assert len(absent) == 35
    assert all(r['output'] == r['inherited'] for r in absent)
    assert all(r['output'] == r['input'] for r in rows if r not in absent)
