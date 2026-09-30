from variant_execution import FIRMWARE, execute


def test_real_variant_loader_selects_mode_three_only():
    binary = (FIRMWARE / "catson-bin--phyfw_v4").read_bytes()
    ordinary = execute(binary, 0x5F2D0, 2, 0xB2510)
    special = execute(binary, 0x5F2D0, 3, 0xB1D10)
    assert ordinary["writes"] == special["writes"] == 8192
    assert ordinary["output_sha256"] != special["output_sha256"]
    catapult = execute((FIRMWARE / "catson-bin--phyfw_catapult").read_bytes(),
                       0x64AD0, 3, 0xB7980)
    assert ordinary["destination_pointer_member"] == "0x1a588"
    assert catapult["destination_pointer_member"] == "0x1a5a0"
