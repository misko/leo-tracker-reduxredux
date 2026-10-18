"""Satellite proposals cannot split or duplicate fixed coherent source groups."""

import numpy as np
import pytest
from iterate_dsx01_clock_identities import grouped_labels


def test_joint_group_proposal_uses_combined_evidence_not_one_receiver():
    cost = np.array([[0.0, 3.0, 4.0], [9.0, 1.0, 6.0], [4.0, 3.0, 0.0]])
    proposals = grouped_labels(cost, [[0, 1], [2]], np.array([0, 0, 2]))
    assert proposals[0]["new"] == 1 and proposals[0]["group"] == [0, 1]
    assert proposals[0]["gain"] == 5
    assert proposals[1]["new"] == 2


def test_invalid_membership_or_disagreeing_source_labels_fail_closed():
    with pytest.raises(ValueError, match="exactly once"):
        grouped_labels(np.ones((3, 2)), [[0, 1], [1, 2]], [0, 0, 0])
    with pytest.raises(ValueError, match="agree"):
        grouped_labels(np.ones((3, 2)), [[0, 1], [2]], [0, 1, 0])
