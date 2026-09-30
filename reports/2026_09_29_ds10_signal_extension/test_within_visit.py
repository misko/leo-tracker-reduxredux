import numpy as np
from within_visit import aggregate, agreement_matrix


def test_changing_frames_distinguish_same_frame_from_mismatch():
    x = np.array([[[1, 1, -1, -1]], [[-1, -1, 1, 1]]], dtype=complex)
    matches, counts = agreement_matrix(x, x, np.ones(x.shape, dtype=bool))
    diag = np.eye(2, dtype=bool)
    assert aggregate(matches, counts, diag)["agreement"] == 1
    assert aggregate(matches, counts, ~diag)["agreement"] == 0


def test_mask_frozen_and_constant_signal_has_no_diagonal_excess():
    x = np.ones((3, 1, 4), dtype=complex)
    keep = np.zeros(x.shape, dtype=bool)
    keep[0, :, :2] = True
    keep[1:, :, :3] = True
    matches, counts = agreement_matrix(x, x, keep)
    assert counts.tolist() == [[2, 2, 2], [3, 3, 3], [3, 3, 3]]
    diag = np.eye(3, dtype=bool)
    assert aggregate(matches, counts, diag)["agreement"] == 1
    assert aggregate(matches, counts, ~diag)["agreement"] == 1
