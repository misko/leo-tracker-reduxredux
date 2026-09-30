from register_mapping import RX_PATH, run


def test_bank_mapping_and_physical_fallbacks():
    result = run()
    assert len(result['cases']) == 4
    for case in result['cases']:
        primary = [c for c in case['calls'] if c['path'] == RX_PATH]
        assert [c['offset'] for c in primary] == ['0x0', '0x1000']
        for call in case['calls']:
            if call['path'] == '/dev/mem':
                assert int(call['offset'], 16) == 0xC204000 + call['bank'] * 0x1000


def test_v4_bank_mapping_matches_device_tree():
    result = run(variant=True)
    assert len(result['cases']) == 4
    for case in result['cases']:
        primary = [c for c in case['calls'] if c['path'] == RX_PATH]
        assert [c['offset'] for c in primary] == ['0x0', '0x1000']
        for call in case['calls']:
            if call['path'] == '/dev/mem':
                assert int(call['offset'], 16) == 0xC228000 + call['bank'] * 0x1000
