import numpy as np
from family_validation import assignments,family_cut,correction_fit,forecast,TARGET


def test_family_folds_reproducible_disjoint_complete():
    a=assignments([1,2,3,4,5,6,7,TARGET]);assert a==assignments([7,6,5,4,3,2,1,TARGET])
    assert sorted(n for f in a for n in f)==list(range(1,8))
    assert len(set(n for f in a for n in f))==7


def test_cut_removes_all_channels_and_receivers_in_family():
    rows=[dict(candidate_norad=n) for n in [1,2,1,TARGET]]
    sl=[slice(i*2,i*2+2) for i in range(4)]
    assert family_cut(rows,sl,np.ones(8,bool),{1,TARGET}).tolist()==[False,False,True,True,False,False,False,False]


def test_target_cannot_train_correction():
    try:correction_fit([dict(norad=TARGET)])
    except AssertionError:pass
    else:raise AssertionError('target accepted into correction fit')


def test_no_extrapolation_without_two_same_receiver_families():
    t=dict(times_s=np.array([0.,10.,100.]),rf_hz=11.5e9,receiver=1)
    train=[dict(norad=n,receiver=1,times_s=np.array([1.,10.])) for n in [1,2]]
    from family_validation import KNOTS
    pred=forecast(t,train,np.ones(2*len(KNOTS))*30,np.eye(2*len(KNOTS)))
    assert pred['support'].tolist()==[True,True,False]
    assert pred['prediction_hz'][2]==0
    assert pred['correction_sigma_hz'][2]>0
