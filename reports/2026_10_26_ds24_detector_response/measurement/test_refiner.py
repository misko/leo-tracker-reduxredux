import unittest
import numpy as np
import refiner as r


class RefinerTests(unittest.TestCase):
    def fixture(self,f):
        times=np.arange(64)[None,:]*4.4e-6+np.arange(3)[:,None]/750
        values=np.array([1+0j,.7+.2j,-.3+.8j])[:,None]*np.exp(2j*np.pi*f*(times-times[:,:1]))
        return values,times

    def test_autocorrelation_matches_direct_and_original_fft(self):
        v,t=self.fixture(19.7);ceiling=np.sum(np.sum(abs(v),axis=1)**2)
        result=r.refine_correlations(v,t,0.)
        self.assertTrue(result['numerically_qualified'])
        self.assertLess(abs(result['residual_cfo_hz']-19.7),.01)
        grid=np.fft.fftfreq(512,d=4.4e-6)
        spectrum=np.sum(abs(np.fft.fft(v,n=512,axis=1))**2,axis=0)/ceiling
        for i in (0,1,7,255,256,511):
            direct=r.direct_score(v,t-t[:,:1],grid[i],ceiling)[0]
            self.assertLess(abs(direct-spectrum[i]),1e-11)

    def test_signed_local_residuals(self):
        for f in (-119.3,-19.7,19.7,120.5):
            v,t=self.fixture(f);q=r.refine_correlations(v,t,0.)
            self.assertTrue(q['numerically_qualified']);self.assertLess(abs(q['residual_cfo_hz']-f),.01)

    def test_original_cell_boundary_is_not_rescued(self):
        v,t=self.fixture(300.)
        q=r.refine_correlations(v,t,0.)
        self.assertFalse(q['numerically_qualified'])
        self.assertTrue(q['boundary'])
        self.assertIsNone(q['reference_root_hz'])

    def test_frame_common_phase_and_amplitude_invariance(self):
        v,t=self.fixture(31.7);a=r.refine_correlations(v,t,0.)
        b=r.refine_correlations(v*np.exp(1j*np.array([.2,1.,-2.]))[:,None]*7,t+100.,0.)
        self.assertTrue(b['numerically_qualified'])
        self.assertLess(abs(a['residual_cfo_hz']-b['residual_cfo_hz']),.01)

    def test_direct_derivative_and_curvature(self):
        v,t=self.fixture(-31.7);lags=t-t[:,:1];ceiling=np.sum(np.sum(abs(v),axis=1)**2)
        h=.5;s,d,dd=r.direct_score(v,lags,20.,ceiling)
        sp=r.direct_score(v,lags,20.+h,ceiling)[0];sm=r.direct_score(v,lags,20.-h,ceiling)[0]
        self.assertLess(abs(d-(sp-sm)/(2*h)),1e-10)
        self.assertLess(abs(dd-(sp+sm-2*s)/h**2),1e-10)

    def test_invalid_support_and_zero_ceiling_rejected(self):
        v,t=self.fixture(0.)
        with self.assertRaises(ValueError):r.refine_correlations(v[:,:63],t[:,:63],0.)
        with self.assertRaises(ValueError):r.refine_correlations(v*0,t,0.)
        t[1,3]+=.001
        with self.assertRaises(ValueError):r.refine_correlations(v,t,0.)


if __name__=='__main__':unittest.main()
