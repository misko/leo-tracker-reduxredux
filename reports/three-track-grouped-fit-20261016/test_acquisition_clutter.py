import unittest
from types import SimpleNamespace
import numpy as np
from acquisition_clutter import conditioned_density,covariate
from leo.analysis.shared_scan_model import density
from leo.analysis.regional_position_score import ALIAS_HZ


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.y=np.array([5.,120.,-30.]);self.pred=np.array([[0.,80.],[90.,130.],[-45.,50.]])
        self.weight=np.array([[.4,.9],[.6,.3],[.8,.5]])
        self.sigma=np.full(3,125.);self.q=np.array([.08,.12])
        self.config=SimpleNamespace(clutter_rate=.3,detection_budget=.2)

    def test_zero_slope_replays_original_density(self):
        old,od=density(self.y,self.pred,self.weight,self.sigma,self.q,self.config)
        new,nd=conditioned_density(self.y,self.pred,self.weight,self.sigma,self.q,self.config,np.zeros(3))
        for name in ['nll','responsibilities','clutter_probability','prediction_gradient','residual_hz']:
            np.testing.assert_allclose(getattr(old,name),getattr(new,name),rtol=0,atol=1e-12)
        for name in ['detection_probability_gradient','visibility_weight_gradient']:
            np.testing.assert_allclose(od[name],nd[name],rtol=0,atol=1e-12)

    def test_clutter_multiplier_and_frequency_gradients(self):
        log_rate=np.array([-.4,.8,.3]);terms,detail=conditioned_density(self.y,self.pred,self.weight,self.sigma,self.q,self.config,log_rate)
        for i in range(3):
            hi=log_rate.copy();lo=log_rate.copy();hi[i]+=1e-5;lo[i]-=1e-5
            fd=(conditioned_density(self.y,self.pred,self.weight,self.sigma,self.q,self.config,hi)[0].nll-conditioned_density(self.y,self.pred,self.weight,self.sigma,self.q,self.config,lo)[0].nll)/2e-5
            self.assertAlmostEqual(fd,detail['clutter_log_multiplier_gradient'][i],delta=1e-8)
        for index in np.ndindex(self.pred.shape):
            hi=self.pred.copy();lo=self.pred.copy();hi[index]+=.001;lo[index]-=.001
            fd=(conditioned_density(self.y,hi,self.weight,self.sigma,self.q,self.config,log_rate)[0].nll-conditioned_density(self.y,lo,self.weight,self.sigma,self.q,self.config,log_rate)[0].nll)/.002
            self.assertAlmostEqual(fd,terms.prediction_gradient[index],delta=1e-8)

    def test_visibility_and_budget_preserving_q_gradients(self):
        _,detail=conditioned_density(self.y,self.pred,self.weight,self.sigma,self.q,self.config,np.ones(3)*.2)
        for index in np.ndindex(self.weight.shape):
            hi=self.weight.copy();lo=self.weight.copy();hi[index]+=1e-6;lo[index]-=1e-6
            fd=(conditioned_density(self.y,self.pred,hi,self.sigma,self.q,self.config,np.ones(3)*.2)[0].nll-conditioned_density(self.y,self.pred,lo,self.sigma,self.q,self.config,np.ones(3)*.2)[0].nll)/2e-6
            self.assertAlmostEqual(fd,detail['visibility_weight_gradient'][index],delta=1e-7)
        hi=self.q+np.array([1e-6,-1e-6]);lo=self.q-np.array([1e-6,-1e-6])
        fd=(conditioned_density(self.y,self.pred,self.weight,self.sigma,hi,self.config,np.ones(3)*.2)[0].nll-conditioned_density(self.y,self.pred,self.weight,self.sigma,lo,self.config,np.ones(3)*.2)[0].nll)/2e-6
        self.assertAlmostEqual(fd,detail['detection_probability_gradient'][0]-detail['detection_probability_gradient'][1],delta=1e-6)

    def test_conditional_density_integrates_to_one(self):
        y=np.linspace(-ALIAS_HZ/2,ALIAS_HZ/2,10001);pred=np.tile([-1000.,1500.],(len(y),1))
        _,detail=conditioned_density(y,pred,np.ones_like(pred),np.full(len(y),125.),self.q,self.config,np.full(len(y),.7))
        self.assertAlmostEqual(float(np.trapezoid(np.exp(-detail['row_nll']),y)),1.,places=10)

    def test_training_normalization_does_not_use_held_margins(self):
        margins=np.array([.05,.1,.2,.3]);mask=np.array([True,True,False,False])
        first,meta=covariate(margins,mask);changed=margins.copy();changed[~mask]=[1e-8,1e8]
        second,other=covariate(changed,mask)
        self.assertEqual(meta,other);np.testing.assert_array_equal(first[mask],second[mask])

    def test_invalid_covariate_and_density_rejected(self):
        with self.assertRaises(ValueError):covariate(np.ones(3),np.ones(3,bool))
        with self.assertRaises(ValueError):covariate(np.array([0.,1.]),np.ones(2,bool))
        with self.assertRaises(ValueError):conditioned_density(self.y,self.pred,self.weight,self.sigma,self.q+.01,self.config,np.zeros(3))


if __name__=='__main__':unittest.main()
