from sysinfo_context import run


def test_received_sysinfo_selects_context_and_preserves_expected_id():
    rows = run()['cases']
    assert len(rows) == 140
    assert {row['selected_offset'] for row in rows} == {'0x41538', '0x415a0'}
