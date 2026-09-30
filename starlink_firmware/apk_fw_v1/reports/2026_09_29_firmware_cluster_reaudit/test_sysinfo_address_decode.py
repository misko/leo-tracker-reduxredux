from sysinfo_address_decode import run


def test_actual_sysinfo_decoder_preserves_address_bits_and_exposes_partial_failure():
    result = run()
    assert len(result["cases"]) == 52
    assert {r["input_address"] for r in result["cases"]} >= {1 << i for i in range(32)}
    assert result["truncated_case"]["status"] == 27
