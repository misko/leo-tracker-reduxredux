import unittest
import numpy as np
from owner_mixture_localization import OwnerLikelihood,logistic


class OwnerLikelihoodTests(unittest.TestCase):
    def setUp(self):
        self.like=OwnerLikelihood(np.array([20.,300.,1200.]),np.array([9,2,7]),np.array([0,1,0]),np.zeros((3,1)))
        self.pred=np.array([[0.,999.],[999.,50.],[400.,999.]])
        self.visible=np.ones((3,2),bool)

    def test_mean_sigma_and_inlier_derivatives(self):
        like=self.like
        r=like.evaluate(self.pred,self.visible)
        analytic=r['prediction_gradient'].copy();eps=.001
        for i in range(3):
            for j in range(2):
                e=np.zeros_like(self.pred);e[i,j]=eps
                fd=(like.evaluate(self.pred+e,self.visible)['total_log_likelihood']-like.evaluate(self.pred-e,self.visible)['total_log_likelihood'])/(2*eps)
                self.assertAlmostEqual(analytic[i,j],fd,places=8)
        eps=1e-5
        sigma=like.sigma_hz
        like.sigma_hz=sigma*np.exp(eps);vp=-like.evaluate(self.pred,self.visible)['total_log_likelihood']
        like.sigma_hz=sigma*np.exp(-eps);vm=-like.evaluate(self.pred,self.visible)['total_log_likelihood']
        like.sigma_hz=sigma
        self.assertAlmostEqual((vp-vm)/(2*eps),r['log_sigma_nll_gradient'],places=5)
        z=np.log(like.inlier_probability/(1-like.inlier_probability))
        like.inlier_probability=logistic(z+eps);vp=-like.evaluate(self.pred,self.visible)['total_log_likelihood']
        like.inlier_probability=logistic(z-eps);vm=-like.evaluate(self.pred,self.visible)['total_log_likelihood']
        self.assertAlmostEqual((vp-vm)/(2*eps),r['logit_inlier_nll_gradient'],places=5)

    def test_unused_candidates_do_not_change_owner_support(self):
        r=self.like.evaluate(self.pred,self.visible)
        q=self.like.evaluate(np.column_stack([self.pred,np.zeros((3,50))]),np.ones((3,52),bool))
        self.assertAlmostEqual(r['total_log_likelihood'],q['total_log_likelihood'])
        np.testing.assert_allclose(r['inlier_weight'],q['inlier_weight'])
        np.testing.assert_array_equal(r['group_values'],[2,7,9])

    def test_legacy_bank_size_confidence_ceiling(self):
        from finite_set_likelihood import prepare_finite_set_likelihood
        from owner_mixture_localization import ALIAS
        n=50;prepared=prepare_finite_set_likelihood([0.],[0])
        predictions=np.full((1,n),50000.);predictions[0,0]=0.
        result=prepared.evaluate(predictions,np.ones((1,n),bool),sigma_hz=200.,
            detection_probability=.8/n,clutter_rate=2.,implementation='batched',return_gradient=True)
        odds=(.8/n)/(1-.8/n)/(np.sqrt(2*np.pi)*200.)
        expected=odds/(odds+2./ALIAS)
        self.assertAlmostEqual(result['row_association_probability'][0,0],expected,places=10)
        self.assertLess(expected,.8)

    def test_invisible_owner_is_uniform_and_duplicate_window_rejected(self):
        visible=self.visible.copy();visible[1,1]=False
        r=self.like.evaluate(self.pred,visible)
        self.assertEqual(r['inlier_weight'][1],0.)
        np.testing.assert_array_equal(r['prediction_gradient'][1],0.)
        with self.assertRaises(ValueError):OwnerLikelihood([1,2],[0,0],[0,0],np.zeros((2,1)))


if __name__=='__main__':unittest.main()
