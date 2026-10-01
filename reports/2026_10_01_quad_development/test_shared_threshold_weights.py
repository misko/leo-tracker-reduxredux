import numpy as np
from shared_threshold_weights import shared_log_weights


def test_unique_minimum_derivative_and_probability_conservation():
    margins=np.array([[.1,.3],[-.2,.1]])
    jac=np.array([[[1.,2.],[3.,4.]],[[.5,-1.],[2.,3.]]])
    logs,g,info=shared_log_weights(margins,jac,.1,.8)
    assert np.all(info['differentiable'])
    np.testing.assert_allclose(np.exp(logs).sum(),1,atol=1e-14)
    for d in range(2):
        plus=shared_log_weights(margins+1e-6*jac[:,:,d],jac,.1,.8)[0]
        minus=shared_log_weights(margins-1e-6*jac[:,:,d],jac,.1,.8)[0]
        np.testing.assert_allclose((plus-minus)/2e-6,g[:,d],rtol=1e-7,atol=1e-7)


def test_duplicate_geometry_and_derivatives_do_not_change_weights():
    m=np.array([[0.,.2],[.1,.3]]);j=np.ones((2,2,1))
    original=shared_log_weights(m,j,.1,.8)
    repeated=shared_log_weights(np.repeat(m,16,axis=1),np.repeat(j,16,axis=1),.1,.8)
    np.testing.assert_array_equal(original[0],repeated[0])
    np.testing.assert_array_equal(original[1],repeated[1])
    assert np.all(repeated[2]['tie_counts']==16)


def test_crossing_minima_is_continuous_but_not_falsely_certified_smooth():
    j=np.array([[[1.],[-1.]]])
    logs,g,info=shared_log_weights([[0.,0.]],j,.1,.8)
    assert g is None and not info['differentiable'][0]
    differences=[]
    for h in [1e-3,1e-5,1e-7]:
        a=shared_log_weights([[h,-h]],j,.1,.8)[0]
        b=shared_log_weights([[-h,h]],j,.1,.8)[0]
        np.testing.assert_allclose(a,b,atol=1e-14)
        differences.append(abs(a[0]-logs[0]))
    assert differences[2]<differences[1]<differences[0]
