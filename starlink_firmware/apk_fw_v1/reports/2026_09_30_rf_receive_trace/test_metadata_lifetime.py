from metadata_lifetime import run


def test_cleanup_consumes_before_invalidating_metadata():
    result = run()
    assert len(result['cases']) == 768
    assert all(c['old_body_preserved_but_gate_closed'] for c in result['cases'])
