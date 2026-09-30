from control_opcode import run


def test_control_opcode_length_gate():
    assert len(run()['cases']) == 96
