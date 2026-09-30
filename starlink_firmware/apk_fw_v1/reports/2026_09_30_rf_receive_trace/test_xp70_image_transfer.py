from xp70_image_transfer import run


def test_transfer_arguments():
    result = run()
    assert len(result['cases']) == 36
    assert result['message_type']['vtable'] == '0x153c390'
    assert 'Scp19AppRegistersMessage' in result['message_type']['name']
    assert {case['stopped_before_call'] for case in result['cases']} == {
        '0x50b2cc', '0x50b3d4', '0x50b34c', '0x50b45c'}
