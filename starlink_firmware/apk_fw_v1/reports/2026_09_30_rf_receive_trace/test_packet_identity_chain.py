from packet_identity_chain import run


def test_packet_identity_chain():
    assert len(run()['cases']) == 35


def test_real_buffer_wrapper_and_install_preserve_identity_path():
    assert run(wrapped=True)['cases'] == run()['cases']
    assert run(controls=True, wrapped=True)['cases'] == run(controls=True)['cases']


def test_descriptor_receive_and_identity_parser_share_mode_one():
    assert run(descriptor=True)['cases'] == run()['cases']
    assert run(controls=True, descriptor=True)['cases'] == run(controls=True)['cases']


def test_actual_receive_callers_connect_descriptor_to_identity():
    for caller in (0x28B80, 0x28D50):
        assert run(caller=caller)['cases'] == run()['cases']
        assert run(controls=True, caller=caller)['cases'] == run(controls=True)['cases']


def test_actual_fifo_and_translation_connect_to_identity():
    for caller in (0x28B80, 0x28D50):
        assert run(caller=caller, fifo=True)['cases'] == run()['cases']
        assert run(controls=True, caller=caller, fifo=True)['cases'] == run(controls=True)['cases']


def test_identity_survives_complete_minimal_update_to_cleanup():
    assert run(fifo=True, through_update=True)['cases'] == run()['cases']
    controls = run(controls=True, fifo=True, through_update=True)['cases']
    assert controls == run(controls=True)['cases']


def test_primary_context_update_reaches_followup_despite_expected_mismatch():
    result = run(fifo=True, through_update=True, primary=True)
    assert result['cases'] == run()['cases']
    controls = run(controls=True, fifo=True, through_update=True, primary=True)
    assert controls['cases'] == run(controls=True)['cases']


def test_received_identity_is_copied_unchanged_to_internal_notification():
    assert run(notification=True)['cases'] == run()['cases']
    assert run(notification=True, controls=True)['cases'] == run(controls=True)['cases']


def test_packet_identity_gates():
    cases = run(controls=True)['cases']
    assert cases[0]['identity'] == 0x12345678
    assert cases[0]['visited'][-1] == '0x44da0'
    assert {case['label']: case['rejection']['stage'] for case in cases[1:]} == {
        'header_too_small': 'header_length',
        'header_too_large': 'header_length',
        'payload_too_large': 'payload_length',
        'truncated_buffer': 'payload_length',
        'short_sysinfo': 'sysinfo',
    }
    assert all('0x44da0' not in case['visited'] for case in cases[1:])
    assert [cases[index]['rejection']['x0_at_stop'] for index in (1, 2, 5)] == [27, 27, 1]
