import numpy as np
import pytest

from leo.analysis.localization_group_proposals import rank_group_proposals


def test_shared_epoch_penalty_once_and_zero_epoch_trap():
    scores = np.array([[[-3., -5.], [-3., -5.]], [[-4., 0.], [-4., 0.]]])
    proposals = rank_group_proposals(scores, [0., 1.], [0, 0], [-3., -3.], [0., 0.])
    best = proposals[0]
    assert (best.source, best.target, best.epoch_index) == (0, 1, 1)
    assert best.track_indices == (0, 1)
    assert best.conditional_gain == pytest.approx(4.)
    # Independent full conditional objective difference agrees with the ranking.
    old = -6.
    new = 0.-.5*4*1.**2
    assert new-old == best.conditional_gain


def test_used_targets_background_ineligible_and_offset_credit():
    scores = np.zeros((2, 3, 3))
    scores[:, :, 2] = -np.inf
    assert rank_group_proposals(scores, [0., 1.], [0, 1, 3], [-1., -1., -1.],
                                [.2, .3, .4]) == []
    scores[:, :, 2] = 0.
    rows = rank_group_proposals(scores, [0., 1.], [0, 1, 3], [-1., -1., -1.],
                                [.2, .3, .4], limit=3)
    assert all(p.target == 2 and 2 not in p.track_indices for p in rows)
    assert rows[0].conditional_gain == pytest.approx(1+2*(.3**2+.4**2))
    with pytest.raises(ValueError):
        rank_group_proposals(scores, [0., 1.], [0, 1, 4], [-1., -1., -1.], [.2, .3, .4])
