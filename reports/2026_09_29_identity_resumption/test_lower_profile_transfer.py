import numpy as np
from lower_profile_transfer import centered_score, rotate


def test_symbol_flank_offsets_removed_and_rotations_preserve_flanks():
    bins = np.array([525, 526, 527, 536, 537, 538])
    x = np.tile([1., 4., 2., 5., 2., 3.], (6, 1))
    y = 2 * x + np.arange(6)[:, None] * 30 + (bins > 535) * 100
    assert np.isclose(centered_score(x, y, np.ones_like(x, bool), bins), 1)
    shifted = rotate(x, bins, (1, 2))
    np.testing.assert_array_equal(shifted[:, :3], np.roll(x[:, :3], 1, axis=1))
    np.testing.assert_array_equal(shifted[:, 3:], np.roll(x[:, 3:], 2, axis=1))
    assert centered_score(x, y, np.zeros_like(x, bool), bins) is None
