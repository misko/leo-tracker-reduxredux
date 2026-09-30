from xp70_host_loader import run


def test_xp70_byte_routing():
    result = run()
    assert len(result['cases']) == 33
    assert result['mesh_shiraz_slot_40']['target'] == '0x4784b0'
    assert {case['outcome'] for case in result['cases']} == {
        'copied', 'data_bounds', 'strs_bounds', 'text_bounds'}
