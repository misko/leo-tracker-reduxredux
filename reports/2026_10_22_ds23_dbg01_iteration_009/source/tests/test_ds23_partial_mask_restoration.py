from types import SimpleNamespace

import numpy as np

from probe_ds23_partial_mask_restoration import restoration_offers


def problem(linear=False):
    t=np.arange(60,dtype=float);values=100*t if linear else 8*(t-30)**2
    track=dict(key='source',times=t,values=values,observation_ids=[str(i) for i in range(len(t))])
    return SimpleNamespace(members=[0],slices=[slice(0,60)],keep=np.r_[np.ones(30,bool),np.zeros(30,bool)],scan=SimpleNamespace(tracks=[track]))


def test_only_an_independently_curved_unused_subset_is_offered_without_mutating_the_mask():
    p=problem();before=p.keep.copy();offers=restoration_offers(p,[])
    assert len(offers)==1 and offers[0]['added_observation_ids']==[str(i) for i in range(30,60)]
    assert offers[0]['added_points']==30
    np.testing.assert_array_equal(p.keep,before)
    assert restoration_offers(problem(True),[])==[]


def test_wholly_unused_or_wholly_used_rows_and_predictive_overlap_are_not_restoration():
    p=problem();p.keep[:]=False;assert restoration_offers(p,[])==[]
    p.keep[:]=True;assert restoration_offers(p,[])==[]
    p=problem();assert restoration_offers(p,[dict(observation_ids=['40'])])==[]
