from meh_transmit_trailer import run


def test_meh_helper_preserves_input_and_writes_ones_then_zero_trailer():
    result = run()
    assert len(result["cases"]) == 576
    assert result["trailer_table"] == [16, 24]
    assert all(c["trailer_zero_after_flush_and_join"] for c in result["cases"])
