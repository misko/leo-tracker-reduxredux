from receive_route_lookup import run


def test_route_lookup():
    result = run()
    assert len(result['cases']) == 98
    assert any(c['mode_result'] == 1 and c['value'] == 0xFF00 and c['found']
               for c in result['cases'])
