from descriptor_payload_handoff import run


def test_descriptor_payload_pointer_and_length_are_preserved():
    assert len(run()['cases']) == 20
