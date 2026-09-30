from sysinfo_update import run


def test_update_return_tracks_change_not_address_mismatch():
    cases = run()['cases']
    assert len(cases) == 120
    assert sum(c['returned'] for c in cases) == 96
