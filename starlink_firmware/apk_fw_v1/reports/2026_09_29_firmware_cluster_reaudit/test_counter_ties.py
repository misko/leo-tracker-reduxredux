import numpy as np
from counter_ties import bank, gains, tail_rank, tied_prediction


def test_discovery_ties_average_disagreeing_future_predictions():
    training = np.array([[0, 1], [0, 1], [1, 0]], dtype=bool)
    held = np.array([[0, 0], [1, 1], [0, 1]], dtype=bool)
    first, mixed, count = tied_prediction(training, held, training[0, :, None])
    np.testing.assert_array_equal(first, [[0], [0]])
    np.testing.assert_array_equal(mixed, [[.5], [.5]])
    np.testing.assert_array_equal(count, [2])
    np.testing.assert_array_equal(gains(mixed, np.array([[0], [1]]), [True]), [0])


def test_templates_respect_physical_frame_gaps():
    full = bank(range(80))
    np.testing.assert_array_equal(bank([0, 7, 21, 79]), full[:, [0, 7, 21, 79]])


def test_tail_rank_includes_roundoff_ties():
    assert tail_rank([2 / 3, 1 - 1 / 3, 2 / 3 - 1e-16, .2]) == .75
