import numpy as np
from receiver_validation import split_groups, fit, design


def test_random_whole_groups_reproducible():
    a=split_groups(['d','b','a','c','e','f'])
    assert a==split_groups(['a','b','c','d','e','f'])
    assert not set(a['training'])&set(a['held'])
    assert set(a['training']+a['held'])==set('abcdef')


def test_receiver_excludes_same_satellite_and_target_values_never_used():
    t=dict(component='target',receiver=1,norad=3,rf_hz=11.5e9,times_s=np.arange(20.),residual_hz=np.zeros(20))
    w=dict(t,component='w',norad=4,residual_hz=np.linspace(-80,80,20))
    forbidden=dict(t,component='forbidden',residual_hz=np.ones(20)*1e9)
    knots=np.arange(-6,30,6.)
    c,names=fit([w,forbidden,t],t,knots,'receiver')
    c2,_=fit([w],dict(t,residual_hz=np.ones(20)*1e9),knots,'receiver')
    assert names==['w']
    assert np.array_equal(c,c2)
    assert np.std(design(t,t,knots,'receiver')@c)>1


def test_satellite_requires_other_receiver_and_zero_support_zero_correction():
    t=dict(component='target',receiver=1,norad=3,rf_hz=11.5e9,times_s=np.arange(10.),residual_hz=np.ones(10))
    c,names=fit([dict(t,component='same_rx')],t,np.arange(0,15,6.),'satellite')
    assert names==[]
    assert np.all(c==0)


def test_joint_directly_excludes_target():
    t=dict(component='target',receiver=1,norad=3,rf_hz=11.5e9,times_s=np.arange(10.),residual_hz=np.ones(10)*1e9)
    c,names=fit([t],t,np.arange(0,15,6.),'joint')
    assert names==[]
    assert np.all(c==0)
