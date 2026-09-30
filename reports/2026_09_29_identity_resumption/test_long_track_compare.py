import numpy as np
from long_track_compare import contrast


def test_contrast_excludes_self_pairs_and_recovers_known_group_separation():
    labels = [0, 0, 1, 1]
    matrix = (np.array(labels)[:, None] == np.array(labels)[None, :]).astype(float)
    np.fill_diagonal(matrix, 100)
    assert contrast(matrix, labels) == 1
