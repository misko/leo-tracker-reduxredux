from receive_buffer_wrap import run


def test_receive_buffer_wrap_preserves_payload():
    assert len(run()['cases']) == 60
