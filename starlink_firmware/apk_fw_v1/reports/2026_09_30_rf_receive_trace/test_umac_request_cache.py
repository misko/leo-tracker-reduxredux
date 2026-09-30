from umac_request_cache import run


def test_request_transfer_and_selection():
    result = run()
    assert len(result['cases']) == 12
    assert sum(c['selected'] == 'active' for c in result['cases']) == 3
