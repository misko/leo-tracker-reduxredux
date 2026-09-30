from header_length_gate import run


def test_header_length_gate():
    assert len(run()['cases']) == 72
