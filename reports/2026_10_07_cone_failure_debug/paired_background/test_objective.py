import unittest
import numpy as np
from leo.contracts.regional_position import PositionScore,PositionObservations,PositionOrbitBank,RegionalPrior
from leo.analysis.regional_position_score import ALIAS_HZ,PositionObjective
from objective import paired,background_likelihood,BackgroundObjective

class BackgroundLikelihoodTests(unittest.TestCase):
    def setUp(self):
        self.score=PositionScore('V16',125.,1.6,.5,3.,1.)
        self.y=np.array([10.,80.,-200.]);self.clock=np.array([15.,-20.,10.])
        self.pred=np.array([[0.,300.,-200.,1800.],[3.,210.,-180.,1700.],[-100.,-200.,-310.,-900.]])
        self.vis=np.ones_like(self.pred,dtype=bool);self.pairs=[[0,1]]
    def call(self,pred=None,clock=None,eta=.9,rho=.9,visible=None):
        return background_likelihood(self.y,self.pred if pred is None else pred,self.vis if visible is None else visible,self.score,self.pairs,rho,eta,self.clock if clock is None else clock)
    def test_eta_zero_exact_reviewed_model(self):
        for rho in (0.,.9,1.):
            old=paired.coupled_likelihood(self.y,self.pred,self.vis,self.score,self.pairs,rho)
            new,extra,_=self.call(eta=0,rho=rho)
            self.assertEqual(old.nll,new.nll)
            np.testing.assert_array_equal(old.prediction_gradient,new.prediction_gradient)
            np.testing.assert_array_equal(extra,0)
    def test_prediction_and_clock_gradients_are_separate(self):
        for eta in (.5,.9,1.):
            terms,extra,_=self.call(eta=eta)
            np.testing.assert_allclose(terms.responsibilities.sum(axis=1)+terms.clutter_probability,1,atol=1e-12)
            for i in range(3):
                d=np.eye(3)[i]*.01
                fd=(self.call(clock=self.clock+d,eta=eta)[0].nll-self.call(clock=self.clock-d,eta=eta)[0].nll)/.02
                self.assertAlmostEqual(fd,extra[i],places=8)
                for j in range(4):
                    delta=np.zeros_like(self.pred);delta[i,j]=.01
                    fd=(self.call(pred=self.pred+delta,eta=eta)[0].nll-self.call(pred=self.pred-delta,eta=eta)[0].nll)/.02
                    self.assertAlmostEqual(fd,terms.prediction_gradient[i,j],places=8)
    def test_fully_unmodeled_pair_has_only_clock_gradient(self):
        vis=np.zeros_like(self.vis)
        terms,extra,diag=self.call(visible=vis)
        np.testing.assert_array_equal(terms.prediction_gradient,0)
        self.assertGreater(diag['common_background_probability'][0],.99)
        self.assertGreater(extra[0],0);self.assertLess(extra[1],0)
        self.assertAlmostEqual(extra.sum(),0)
        shifted=self.call(clock=self.clock+987.,visible=vis)[0]
        self.assertEqual(terms.nll,shifted.nll)
        periodic=self.call(clock=self.clock+np.array([ALIAS_HZ,0,0]),visible=vis)[0]
        self.assertAlmostEqual(terms.nll,periodic.nll,places=10)
    def test_actual_background_integral_mass_preserved(self):
        visible=np.zeros((2,4),bool);pred=self.pred[:2]
        grid=np.r_[-ALIAS_HZ/2,np.arange(-4000.,5000.1,20.),ALIAS_HZ/2]
        integrals=[]
        for eta in (0.,.9,1.):
            density=np.array([np.exp(-background_likelihood(np.array([10.,peer]),pred,visible,self.score,[[0,1]],.9,eta,self.clock[:2])[0].nll) for peer in grid])
            integrals.append(float(np.trapezoid(density,grid)))
        np.testing.assert_allclose(integrals[1:],integrals[0],rtol=1e-10,atol=1e-15)
    def test_unmodeled_far_pair_no_overflow_at_eta_one(self):
        with np.errstate(over='raise',invalid='raise'):
            terms,gradient,diag=self.call(visible=np.zeros_like(self.vis),eta=1,clock=self.clock+np.array([50000.,0.,0.]))
        self.assertTrue(np.isfinite(terms.nll))
        self.assertTrue(np.isfinite(gradient).all())
        np.testing.assert_array_equal(terms.responsibilities,0)
        np.testing.assert_allclose(terms.clutter_probability,1)
    def test_full_objective_background_cannot_create_orbit_gradient(self):
        obs=PositionObservations(('a','b'),np.zeros(2),np.array([10.,80.]),np.full(2,1e9),np.array([0,1]),np.ones(2,int),np.ones(2))
        # This bank is below the California prior's horizon: only unknown background.
        bank=PositionOrbitBank(np.arange(1,5),np.arange(-2.,3.),np.broadcast_to([7000.,1000.,1000.],(4,5,3)).copy(),np.broadcast_to([0.,7.,0.],(4,5,3)).copy())
        objective=BackgroundObjective(obs,bank,RegionalPrior(),self.score,pairs=[[0,1]])
        v=np.zeros(objective.size);_,g,t=objective.evaluate(v)
        np.testing.assert_array_equal(t.responsibilities,0)
        np.testing.assert_array_equal(g[np.r_[0,1,6,np.arange(7,objective.size)]],0)
        self.assertGreater(g[2],0);self.assertLess(g[4],0)
        zero=BackgroundObjective(obs,bank,RegionalPrior(),self.score,pairs=[[0,1]],rho=0,eta=0)
        base=PositionObjective(obs,bank,RegionalPrior(),self.score)
        a=base.evaluate(v);b=zero.evaluate(v)
        self.assertEqual(a[0],b[0]);np.testing.assert_array_equal(a[1],b[1])

if __name__=='__main__':unittest.main()
