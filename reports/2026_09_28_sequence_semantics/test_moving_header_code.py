import numpy as np
from moving_header_code import syndromes


def test_convolutional_syndrome_and_corruption():
    rng = np.random.default_rng(211)
    g = [0o133, 0o171, 0o165]
    u = rng.integers(0, 2, (4, 45), dtype=np.uint8)
    w = np.lib.stride_tricks.sliding_window_view(u, 7, axis=-1)
    taps = (np.array(g)[:, None] >> np.arange(6, -1, -1)) & 1
    encoded = (w @ taps.T) % 2
    words = encoded.reshape(4, -1)
    assert not syndromes(words, g).any()
    words[:, 40] ^= 1
    assert syndromes(words, g).any()


def test_uncoded_random_bits_fail_checks():
    words = np.random.default_rng(213).integers(0, 2, (100, 81), dtype=np.uint8)
    assert 0.45 < syndromes(words, [0o133, 0o171, 0o165]).mean() < 0.55


def test_114_bit_terminated_words_and_fixed_mask_cancellation():
    rng = np.random.default_rng(114)
    g = [0o133, 0o171, 0o165]
    # Six initial zeros, 32 information bits, and six termination zeros.
    data = rng.integers(0, 2, (8, 32), dtype=np.uint8)
    padded = np.pad(data, ((0, 0), (6, 6)))
    taps = (np.array(g)[:, None] >> np.arange(6, -1, -1)) & 1
    words = (np.lib.stride_tricks.sliding_window_view(padded, 7, axis=-1) @ taps.T) % 2
    words = words.reshape(8, 114)
    mask = rng.integers(0, 2, 114, dtype=np.uint8)
    received = words ^ mask
    differences = received[::2] ^ received[1::2]
    assert not syndromes(differences, g).any()
    differences[:, 57] ^= 1
    assert syndromes(differences, g).any()
