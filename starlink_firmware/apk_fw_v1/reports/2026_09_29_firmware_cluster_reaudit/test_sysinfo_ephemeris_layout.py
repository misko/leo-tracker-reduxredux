from sysinfo_ephemeris_layout import run


def test_all_ephemeris_bits_round_trip_and_shift_timing_by_352_bits():
    result = run()
    assert len(result["cases"]) == 708
    assert {c["message_bytes"] for c in result["cases"]} == {52, 62}
    assert result["serialized_offsets"]["rfnum"] - 69 == 352
