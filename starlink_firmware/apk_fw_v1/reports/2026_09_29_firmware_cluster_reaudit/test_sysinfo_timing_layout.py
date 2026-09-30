from sysinfo_timing_layout import run


def test_actual_timing_writer_reader_covers_all_field_bits():
    result = run()
    assert len(result["cases"]) == 74
    assert {c["rfnum"] for c in result["cases"]} >= {1 << k for k in range(32)}
    assert {c["ul_tx_time_offset_bits"] for c in result["cases"]} >= {
        1 << k for k in range(32)}
