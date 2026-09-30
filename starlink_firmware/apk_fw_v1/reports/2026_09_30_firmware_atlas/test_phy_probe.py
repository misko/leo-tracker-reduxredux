from phy_probe import readback


def test_readback_keeps_two_separate_mmio_samples_and_output_canaries():
    assert readback(0x1234AAAA, 0x5678BBBB)["output_at_0x16"] == 0x1234
    assert readback(0x1234AAAA, 0x5678BBBB)["output_at_0x18"] == 0xBBBB
    for bit in range(32):
        row = readback(1 << bit, 1 << bit)
        assert row["output_at_0x16"] << 16 | row["output_at_0x18"] == 1 << bit
