from identity_handoff import run


def test_umac_constructed_identity_reaches_rx_expected_field():
    result = run()
    assert len(result['cases']) == 35
    assert all(row['input'] == row['rx_expected'] for row in result['cases'])
