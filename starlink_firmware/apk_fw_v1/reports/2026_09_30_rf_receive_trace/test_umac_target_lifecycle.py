from umac_target_lifecycle import run


def test_target_initialization_and_session_lookup():
    result = run()
    assert len(result['cases']) == 20
    assert {c['family'] for c in result['cases']} == {0, 1}
