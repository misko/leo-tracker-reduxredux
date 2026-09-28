import numpy as np
from blind_header_114 import (
    check_score,
    mixed_null_check,
    ordered_symbol_span,
    pair_windows,
    qualified_checks,
    serialized_words,
)


def test_recovers_unknown_generators_and_rejects_corruption():
    rng = np.random.default_rng(847)

    def encoded():
        data = np.pad(rng.integers(0, 2, (20, 32)), ((0, 0), (6, 6)))
        taps = (np.array([0o117, 0o155, 0o127])[:, None] >> np.arange(6, -1, -1)) & 1
        code = np.lib.stride_tricks.sliding_window_view(data, 7, axis=-1) @ taps.T % 2
        return pair_windows(code.reshape(20, 114), 0, (0, 1))

    mask = mixed_null_check(encoded())
    assert mask is not None
    assert check_score(encoded(), mask) == 1
    bad = encoded()
    bad[:, (mask & -mask).bit_length() - 1] ^= 1
    assert check_score(bad, mask) == -1


def test_random_and_constant_data_do_not_support_a_check():
    rng = np.random.default_rng(848)
    assert mixed_null_check(rng.integers(0, 2, (200, 14))) is None
    assert mixed_null_check(np.zeros((200, 14))) is None


def test_stream_block_layout_recovers_encoded_relation():
    rng = np.random.default_rng(849)
    data = np.pad(rng.integers(0, 2, (20, 32)), ((0, 0), (6, 6)))
    taps = (np.array([0o117, 0o155, 0o127])[:, None] >> np.arange(6, -1, -1)) & 1
    encoded = np.lib.stride_tricks.sliding_window_view(data, 7, axis=-1) @ taps.T % 2
    stored = encoded.swapaxes(1, 2).reshape(20, 114)
    recovered = serialized_words(stored, "stream_blocks")
    assert np.array_equal(recovered, encoded.reshape(20, 114))
    assert mixed_null_check(pair_windows(recovered, 0, (0, 1))) is not None
    assert mixed_null_check(pair_windows(stored, 0, (0, 1))) is None


def test_rare_changes_are_testable_without_accepting_constant_columns():
    rng = np.random.default_rng(850)
    data = np.zeros((20, 32), dtype=int)
    data[0] = rng.integers(0, 2, 32)
    data = np.pad(data, ((0, 0), (6, 6)))
    taps = (np.array([0o117, 0o155, 0o127])[:, None] >> np.arange(6, -1, -1)) & 1
    code = np.lib.stride_tricks.sliding_window_view(data, 7, axis=-1) @ taps.T % 2
    windows = pair_windows(code.reshape(20, 114), 0, (0, 1))
    assert mixed_null_check(windows) is None
    mask = mixed_null_check(windows, activity_floor=0)
    assert mask is not None and check_score(windows, mask) == 1
    assert mixed_null_check(np.zeros((200, 14)), activity_floor=0) is None


def test_partial_quality_retains_unaffected_windows_and_requires_each_pair():
    rng = np.random.default_rng(851)
    words = rng.integers(0, 2, (3, 114), dtype=np.uint8)
    quality = np.ones_like(words, dtype=bool)
    quality[0, 30] = False
    actual, support, enough = qualified_checks(words, quality, "interleaved", (0, 1))
    assert enough and support == [25, 32, 32]
    changed = words.copy()
    changed[0, 30] ^= 1
    assert np.array_equal(actual, qualified_checks(changed, quality, "interleaved", (0, 1))[0])
    quality[1] = False
    assert not qualified_checks(words, quality, "interleaved", (0, 1))[2]


def test_crossing_span_preserves_time_and_reorders_each_symbol():
    data = np.arange(2 * 3 * 120).reshape(2, 3, 120)
    ids = np.arange(119, -1, -1)
    span = ordered_symbol_span(data, 2, 1, ids, crossing=True)
    assert span.shape == (2, 240)
    assert np.array_equal(span[:, :120], data[:, 1, ::-1])
    assert np.array_equal(span[:, 120:], data[:, 2, ::-1])
    assert np.array_equal(
        span[:, 119:233], np.concatenate([data[:, 1, :1], data[:, 2, :6:-1]], axis=1)
    )
