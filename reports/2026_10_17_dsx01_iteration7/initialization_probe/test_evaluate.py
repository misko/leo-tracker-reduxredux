import numpy as np
import pytest
from evaluate import paired


def test_new_support_debits_losses_and_paired_rms_uses_intersection():
    a = np.array([True, True, False, False])
    b = np.array([True, False, True, True])
    row = paired(a, b, [10., 20., 900., 900.], [5., 900., 30., 40.],
                 [1, 1, 2, 2], [2, 1, 2, 2])
    assert row['new'] == 2 and row['lost'] == 1
    assert row['retained'] == 1 and row['retained_identity_changes'] == 1
    assert row['assigned'] - row['original'] == row['new'] - row['lost']
    assert row['intersection_before_rms_hz'] == 10.
    assert row['intersection_after_rms_hz'] == 5.


def test_alignment_and_boolean_labels_required():
    with pytest.raises(ValueError, match='Aligned'):
        paired(np.array([True]), np.array([True, False]), [1.], [1.], [1], [1])
    with pytest.raises(ValueError, match='association masks'):
        paired([1], [1], [1.], [1.], [1], [1])
