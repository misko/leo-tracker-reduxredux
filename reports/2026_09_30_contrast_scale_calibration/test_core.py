import importlib.util
from pathlib import Path
import unittest
import numpy as np
from core import moments,pack,density,conditional

spec=importlib.util.spec_from_file_location('reference',Path(__file__).resolve().parents[1]/'2026_09_30_ds10_scale_weighting/scaled_model.py')
ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)


class StatisticsTest(unittest.TestCase):
    def test_direct_density_and_gradient(self):
        y=np.array([100.,20.,300.,70.,260.]);t=np.array([0.,.1,.4,1.5,2.]);p=np.array([t*120,t*-50]);visible=np.array([True,False])
        stats=pack([moments(y,t,p,visible)])
        for scale in [30.,100.,250.]:
            got,g=density(stats,np.log([scale]))
            signal,_=ref.trend_module.contrast_density((y[None,:]-p)[:1],scale)
            bg=ref.trend_module.trend_density(y,t,scale,2000.)
            expected=np.logaddexp(np.log(.8)+signal[0],np.log(.2)+bg)
            self.assertAlmostEqual(got[0],expected,places=10)
            delta=1e-5
            fd=(density(stats,np.log([scale])+delta)[0]-density(stats,np.log([scale])-delta)[0])/(2*delta)
            np.testing.assert_allclose(g,fd,atol=1e-8)

    def test_constant_time_background_and_conditional(self):
        y=np.array([1.,30.,-40.,80.]);t=np.ones(4);p=np.zeros((1,4));visible=np.array([True])
        train=pack([moments(y[:3],t[:3],p[:,:3],visible)])
        full=pack([moments(y,t,p,visible)])
        value,g=conditional(train,full,np.log([100.]))
        expected=ref.trend_module.contrast_density(y[None,:],100.)[0][0]-ref.trend_module.contrast_density(y[None,:3],100.)[0][0]
        self.assertAlmostEqual(value[0],expected,places=10)
        fd=(conditional(train,full,np.log([100.])+1e-5)[0]-conditional(train,full,np.log([100.])-1e-5)[0])/2e-5
        np.testing.assert_allclose(g,fd,atol=1e-8)


if __name__=='__main__':unittest.main()
