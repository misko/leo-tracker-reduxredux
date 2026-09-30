from expected_identity import run


def test_expected_identity_copy_preserves_width_and_other_context():
    result = run()
    assert len(result['cases']) == 35
    assert all(row['input'] == row['expected_context'] for row in result['cases'])
    assert all(row['received_context'] == 0x87654321 for row in result['cases'])
