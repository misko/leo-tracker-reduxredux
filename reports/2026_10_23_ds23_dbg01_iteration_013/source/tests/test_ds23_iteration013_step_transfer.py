import numpy as np

from diagnose_ds23_iteration013_step_transfer import affine_eliminated_step


def test_smooth_offset_and_rate_cannot_vote_for_a_frequency_step():
    t=np.linspace(0,40,50);s=np.full(50,100.)
    zero=affine_eliminated_step(t,200+7*t,s,20.)
    assert abs(zero['amplitude_hz'])<1e-10 and zero['gain']<0


def test_step_evidence_is_invariant_to_free_affine_terms():
    t=np.linspace(0,40,50);s=np.full(50,100.);r=np.where(t>=20.,400.,0.)
    a=affine_eliminated_step(t,r,s,20.);b=affine_eliminated_step(t,r+700-15*t,s,20.)
    assert a['gain']>10 and a['amplitude_hz']>300
    assert abs(a['gain']-b['gain'])<1e-10 and abs(a['amplitude_hz']-b['amplitude_hz'])<1e-10
