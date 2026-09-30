from sysinfo_mode_route import run


def test_type0_routing_is_distinct_from_utgw_identity_gate():
    result = run()
    assert len(result['cases']) == 96
    assert sum(c['outcome'] == 'address_stored' for c in result['cases']) == 28
    assert any(c['outcome'] == 'address_stored' and c['expected'] == 10
               and c['received'] == 0xFFFFFFFF for c in result['cases'])
