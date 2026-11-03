from types import SimpleNamespace

import numpy as np
import pytest
from receiver_satellite_ablation import ReceiverSubset, detection_probabilities


def test_emitter_omission_preserves_other_detection_probabilities():
    actual = detection_probabilities(np.array([100, 200, 300]), 200)
    np.testing.assert_allclose(actual, [0.8 / 3, 0, 0.8 / 3])
    with pytest.raises(ValueError, match="once"):
        detection_probabilities([100, 200], 300)


def test_receiver_subset_preserves_bank_and_receipt_time_without_reindexing_groups():
    source = SimpleNamespace(**{name: np.array([0, 1, 0, 1]) for name in
                               ("times", "measured", "rf", "receiver", "channel", "margin")},
                             group=np.array([10, 11, 12, 13]), numbers=np.array([123]),
                             nodes=np.array([-60, 360]))
    subset = ReceiverSubset(source, 1)
    np.testing.assert_array_equal(subset.group, [11, 13])
    np.testing.assert_array_equal(subset.receiver, [1, 1])
    assert subset.numbers is source.numbers
    with pytest.raises(ValueError, match="no rows"):
        ReceiverSubset(source, 2)
