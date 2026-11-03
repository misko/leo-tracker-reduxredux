import numpy as np
from diagnose import derivatives,error,SITE_X
from track_debug import polynomial
from family_debug import marginal_curves

def test_derivatives_and_coordinate_roundtrip():
    H=np.array([[3.,.7],[.7,2.]]);b=np.array([4.,-3.]);x=np.array([1.,2.])
    g,h=derivatives(lambda v:.5*v@H@v+b@v,x)
    np.testing.assert_allclose(g,H@x+b,atol=1e-9)
    np.testing.assert_allclose(h,H,atol=1e-9)
    assert error(SITE_X)<1e-6

def test_family_integral_matches_dense_covariance():
    t=np.linspace(20,250,18);q=np.linspace(.96,1.1,18);group=np.repeat([0,1,2],6)
    raw=np.random.default_rng(45).normal(0,80,(3,18));mask=np.ones(18,bool)
    score,res,coef,aliases=marginal_curves(raw,t,q,group,mask,.5)
    X=np.column_stack([(group==g)*300. for g in range(3)]+[q*(t-150)*.5]);C=np.eye(18)*150**2+X@X.T
    expected=np.einsum('ij,ji->i',raw,np.linalg.solve(C,raw.T))+np.linalg.slogdet(C)[1]-18*np.log(150**2)
    np.testing.assert_allclose(score,expected,rtol=1e-10,atol=1e-10)
    assert not aliases.any()

def test_quadratic_selected_without_inventing_quartic():
    t=np.linspace(0,60,81);y=1000+3*t+2*t*t+np.random.default_rng(3).normal(0,2,len(t))
    result=polynomial(t,y)
    assert result['selected_degree']==2
    assert result['rows'][2]['rms_hz']<3
    assert result['rows'][1]['rms_hz']>100
