import numpy as np

from stability import masks, winners


def test_partition_keeps_bins_together_and_is_seeded():
    times = np.asarray([0.1, 0.8, 1.1, 1.7, 2.3, 3.5, 4.7])
    first = list(masks(times, 42, 10))
    second = list(masks(times, 42, 10))
    for (mask, groups), (again, repeated) in zip(first, second, strict=True):
        assert np.array_equal(mask, again)
        assert groups == repeated
        assert mask[0] == mask[1]
        assert mask[2] == mask[3]
        assert mask.any() and (~mask).any()


def test_refitting_offset_does_not_penalize_correct_shape():
    times = np.arange(8.)
    measured = 100 + 2 * times
    predictions = np.asarray([[2 * times], [4 * times]])
    partitions = list(masks(times, 100, 20))
    assert winners(measured, predictions, np.ones(2, dtype=bool), ["1", "2"], partitions) == ["1"] * 20


def test_invisible_better_fit_cannot_win():
    times = np.arange(8.)
    predictions = np.asarray([[2 * times], [4 * times]])
    assert winners(100 + 2 * times, predictions, np.asarray([False, True]), ["1", "2"], list(masks(times, 100, 5))) == ["2"] * 5
