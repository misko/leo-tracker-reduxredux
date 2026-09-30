from header_payload_handoff import run


def test_header_payload_handoff():
    assert len(run()['cases']) == 9
