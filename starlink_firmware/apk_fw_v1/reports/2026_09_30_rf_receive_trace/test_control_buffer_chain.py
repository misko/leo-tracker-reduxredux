from control_buffer_chain import run


def test_control_buffer_chain():
    result = run()
    assert len(result['cases']) == 280
    assert {case['status'] for case in result['cases']} == {0, 27}


def test_control_buffer_through_context_store():
    result = run(store=True)
    assert len(result['cases']) == 280
    assert result['through_context_store']
