import numpy as np
import pytest
from leo.analysis.research.grouped_prediction import family_folds


def test_every_active_family_is_withheld_whole_once_across_receivers():
    labels=np.array([10,20,30,40,50,60]*4);use=np.ones(24,bool);use[[0,8,23]]=False
    before=use.copy();folds=family_folds(labels,use,seed=583,folds=3);counts=np.zeros(24,int)
    for train,held,receipt in folds:
        counts+=held
        assert not np.any(train&held)
        np.testing.assert_array_equal(train|held,use)
        assert not set(labels[train])&set(labels[held])
        assert receipt['held_families']==np.unique(labels[held]).tolist()
    np.testing.assert_array_equal(counts,use.astype(int));np.testing.assert_array_equal(use,before)
    again=family_folds(labels,use,seed=583,folds=3)
    assert [r[2] for r in folds]==[r[2] for r in again]


def test_insufficient_independent_families_is_explicit():
    with pytest.raises(ValueError,match='not enough'):family_folds(np.array([1,1,2,2]),np.ones(4,bool),seed=1)
    with pytest.raises(ValueError,match='integer'):family_folds(np.array([1.,2.,3.]),np.ones(3,bool),seed=1)
