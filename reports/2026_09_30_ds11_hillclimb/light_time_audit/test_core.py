import unittest
import numpy as np
from core import retarded,C
class LightTimeTests(unittest.TestCase):
    def test_radial_constant_velocity(self):
        p=np.array([[7000.,0,0]]);v=np.array([[7.,0,0]]);a=np.zeros_like(p);r=np.array([6378.,0,0])
        rate,delay,length=retarded(p,v,a,r,omega=0)
        np.testing.assert_allclose(rate,7/(1+7/C),rtol=1e-12)
        np.testing.assert_allclose(delay,622/(C+7),rtol=1e-12)
    def test_static_ecef_and_differentiated_range(self):
        p=np.array([[6500.,2200.,900.]]);v=np.array([[-2.,6.,1.]]);a=np.array([[-.005,-.002,-.001]])
        r=np.array([6000.,1000.,500.]);h=.01
        rate,_,_=retarded(p,v,a,r)
        plus=retarded(p+v*h+.5*a*h*h,v+a*h,a,r)[2]
        minus=retarded(p-v*h+.5*a*h*h,v-a*h,a,r)[2]
        np.testing.assert_allclose(rate,(plus-minus)/(2*h),atol=1e-8,rtol=0)
        np.testing.assert_allclose(retarded(p,np.zeros_like(v),np.zeros_like(a),r)[0],0,atol=1e-12)
