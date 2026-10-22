import numpy as np
import pytest

from probe_ds23_family_predictive_guard import training_masks,guard_decision


def test_fold_holds_only_original_family_points_and_keeps_new_same_family_evidence():
    rows=[dict(candidate_index=1),dict(candidate_index=1),dict(candidate_index=2)]
    slices=[slice(0,2),slice(2,4),slice(4,6)]
    original=np.array([1,1,0,0,1,1],bool)
    expanded=np.ones(6,bool)
    training,held=training_masks(rows,slices,original,expanded,1)
    np.testing.assert_array_equal(held,[1,1,0,0,0,0])
    np.testing.assert_array_equal(training,[0,0,1,1,1,1])
    with pytest.raises(ValueError,match='every original'):
        training_masks(rows,slices,original,np.zeros(6,bool),1)


def test_predictive_guard_requires_total_and_majority_gain_in_both_arms_and_valid_folds():
    assert guard_decision(dict(c0=[1.,2.,3.],fitted_c=[1.,2.,3.]),True)
    assert not guard_decision(dict(c0=[10.,-1.,-2.],fitted_c=[1.,2.,3.]),True)
    assert not guard_decision(dict(c0=[1.,2.,3.],fitted_c=[-1.,-2.,-3.]),True)
    assert not guard_decision(dict(c0=[1.,2.,3.],fitted_c=[1.,2.,3.]),False)
