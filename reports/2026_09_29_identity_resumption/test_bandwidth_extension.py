import numpy as np
from bandwidth_extension import extract


def test_wide_features_use_extra_carriers_and_do_not_bridge_pilot_gap():
    bins = np.array([10, 11, 12, 20, 21, 22])
    z = np.ones((2, 6, 6), dtype=complex)
    z[:, :, 2] = -1
    result = extract(z, bins, [10, 11, 20, 21])
    assert result[0].shape == (2, 24)
    assert result[1].shape == (2, 72)
    assert result[2].shape == (2, 48)  # Four adjacent pairs, not five.
    assert result[3].shape == (2, 36)
    assert (result[0] == 1).all()
    assert (result[3] == -1).sum() == 12
