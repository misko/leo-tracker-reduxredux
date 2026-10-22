import numpy as np

from probe_ds23_iteration011_parent_choice import choose


def test_only_identical_masks_and_predictive_factors_allow_bound_comparison():
    a=dict(mask=[True,False],entries=[]);b=dict(mask=[True,True],entries=[])
    assert not choose(a,b,{})['eligible']
    assert not choose(None,b,{})['eligible']


def test_support_must_beat_same_mask_default_by_declared_margin_in_both_arms():
    t=dict(mask=[True,False],entries=[])
    scores=dict(default=dict(c0=10.,fitted_c=10.),support=dict(c0=8.,fitted_c=8.))
    assert choose(t,t,scores)['choose_support']
    scores['support']['fitted_c']=9.5
    assert not choose(t,t,scores)['choose_support']
