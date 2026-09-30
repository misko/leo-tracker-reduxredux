import numpy as np
from time_separated_code_probe import paired_windows, take_word


def test_symbol_pair_windows_preserve_frequency_and_frame_pairing():
    bits = np.zeros((6, 6, 50), dtype=np.uint8)
    bits[::2, 1, 10] = 1
    valid = np.ones_like(bits, dtype=bool)
    windows, good = paired_windows(bits, valid, (1, 4))
    assert windows.shape == (3, 44, 14)
    assert windows[0, 10, 0] == 1
    assert not windows[:, :, 7:].any()
    selected, enough = take_word(windows, good, 0)
    assert enough and selected.shape == (96, 14)
    valid[:2, 4] = False
    assert not take_word(*paired_windows(bits, valid, (1, 4)), 0)[1]
