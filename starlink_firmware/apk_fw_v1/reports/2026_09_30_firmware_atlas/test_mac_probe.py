"""Component tests execute known-format synthetic bytes in emulated firmware."""

from mac_probe import grant_probe


def test_grant_decoder_retains_unknown_bit_and_checks_logical_lengths():
    result = grant_probe()
    assert len(result["cases"]) == 986
    successful = [c for c in result["cases"] if c["available_bits"] >= 56]
    assert all(c["input_hex"] == c["output_hex"] for c in successful)
    bit47 = (1 << 47).to_bytes(7, "little").hex()
    assert any(c["input_hex"] == bit47 and c["output_hex"] == bit47 for c in successful)
    assert all(c["status"] == 27 for c in result["cases"] if c["available_bits"] < 56)
