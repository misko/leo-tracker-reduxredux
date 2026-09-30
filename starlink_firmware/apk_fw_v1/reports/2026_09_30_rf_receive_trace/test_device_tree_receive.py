from device_tree_receive import run, words


def test_receive_maps():
    result = run()
    assert result['current_count'] > 0


def test_reg_bytes_that_look_like_strings():
    assert words(b'\x0c\x20\x40\x00\x00\x00\x20\x00') == [0xC204000, 0x2000]
