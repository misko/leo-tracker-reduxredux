from identity_request import run


def test_up_request_cached_identity_transfer():
    result = run()
    assert result['memcpy_port_calls'] == len(result['cases']) == 35
    assert all(row['request_id'] == row['expected_id'] for row in result['cases'])
