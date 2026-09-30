from descriptor_gate import run


def test_crc_enable_and_initial_payload_admission():
    rows = run()['cases']
    assert len(rows) == 528
    crc = [r for r in rows if r['flags'] == 1 and r['enabled']]
    assert crc and all(r['outcome'] == 'drop_path' for r in crc)
    disabled = [r for r in rows if r['flags'] == 1 and not r['enabled']]
    assert all(r['outcome'] == 'continue_after_initial_gate' for r in disabled)
