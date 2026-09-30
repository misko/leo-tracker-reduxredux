import numpy as np
from tie_audit import adjusted_rand


def test_partition_agreement_ignores_label_names_but_detects_changed_membership():
    assert adjusted_rand([0, 0, 1, 1], [9, 9, 3, 3]) == 1
    assert np.isclose(adjusted_rand([0, 0, 1, 1], [0, 1, 0, 1]), -.5)
