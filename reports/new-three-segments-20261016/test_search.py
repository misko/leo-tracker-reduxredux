import numpy as np
from search import offset_fit,ALIAS_HZ


def test_alias_boundary_and_held_measurements_do_not_change_training_offset():
    train=np.array([True,True,False,False])
    residual=np.array([[ALIAS_HZ/2-20],[-ALIAS_HZ/2+20],[ALIAS_HZ/2-10],[-ALIAS_HZ/2+10]])
    offset,rms,held=offset_fit(residual,train)
    assert abs(abs(offset[0])-ALIAS_HZ/2)<1e-8
    np.testing.assert_allclose(rms,[20],atol=1e-8)
    np.testing.assert_allclose(held,[10],atol=1e-8)
    residual[~train]+=3210
    other,other_rms,_=offset_fit(residual,train)
    np.testing.assert_array_equal(offset,other)
    np.testing.assert_array_equal(rms,other_rms)


def test_each_candidate_has_its_own_offset():
    residual=np.array([[100.,400.],[102.,398.],[101.,399.]])
    offset,rms,held=offset_fit(residual,np.ones(3,bool))
    np.testing.assert_allclose(offset,[101,399],atol=1e-8)
    np.testing.assert_allclose(rms,np.full(2,np.sqrt(2/3)),atol=1e-8)
    np.testing.assert_array_equal(held,[0,0])
