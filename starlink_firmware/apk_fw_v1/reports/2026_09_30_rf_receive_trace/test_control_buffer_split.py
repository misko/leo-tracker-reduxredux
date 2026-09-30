from control_buffer_split import run


def test_control_buffer_split():
    assert len(run()['cases']) == 36
