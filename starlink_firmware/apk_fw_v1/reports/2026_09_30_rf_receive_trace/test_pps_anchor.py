from pps_anchor import run


def test_register_latch_anchor_update_and_incompatibility():
    cases = run()['cases']
    assert len(cases) == 16
    assert sum(c['status'] == 13 for c in cases) == 4
