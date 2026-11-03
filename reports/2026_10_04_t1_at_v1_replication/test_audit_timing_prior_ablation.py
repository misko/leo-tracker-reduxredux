import numpy as np
from audit_timing_prior_ablation import profile_information


def test_profile_eliminates_shared_nuisance_information():
    h=np.array([[4.,0.,2.],[0.,3.,0.],[2.,0.,2.]])
    reduced,eig=profile_information(h,[2])
    np.testing.assert_allclose(reduced,[[2.,0.],[0.,3.]])
    np.testing.assert_allclose(eig,[2.,3.])


def test_unidentified_nuisance_does_not_invent_position_information():
    h=np.array([[4.,0.,2.,0.],[0.,3.,0.,0.],[2.,0.,1.,0.],[0.,0.,0.,0.]])
    reduced,eig=profile_information(h,[2,3])
    np.testing.assert_allclose(reduced,[[0.,0.],[0.,3.]])
    assert eig[0]==0
