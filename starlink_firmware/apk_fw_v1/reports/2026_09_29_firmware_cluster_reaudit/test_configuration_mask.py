from configuration_mask import FIRMWARE, execute


def test_mask_orientation_and_consumer_count_boundary():
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    forward, reverse = [execute(binary, 16, flag) for flag in (1, 0)]
    assert forward["table"] == list(reversed(reverse["table"]))
    assert forward["count_low5"] == reverse["count_low5"] == 16
    assert forward["enable_bit31"] and reverse["enable_bit31"]
    boundary = execute(binary, 20, 0)
    assert boundary["table"] == [0] * 20
    assert boundary["count_low5"] == 20 and not boundary["enable_bit31"]
