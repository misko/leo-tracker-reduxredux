import numpy as np
from simultaneous_signs import agreement_matrix


def test_evaluation_excludes_donor_frame_and_preserves_direction():
    a = np.array([[True, True], [False, False]])
    b = np.array([[False, False], [False, True]])
    assert agreement_matrix([a, b]) == [[0., .5], [1., .5]]
