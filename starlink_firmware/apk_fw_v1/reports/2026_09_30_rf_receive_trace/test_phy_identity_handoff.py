from phy_identity_handoff import run


def test_rx_identity_survives_phy_field_transfer():
    cases = run()['cases']
    assert len(cases) == 70
    assert all(c['address'] == c['telemetry_address'] for c in cases)
