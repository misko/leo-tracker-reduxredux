"""Independent black-box normalization and pair-admission review tests."""
import unittest
import numpy as np
from leo.contracts.regional_position import PositionScore,PositionObservations,PositionOrbitBank,RegionalPrior
from leo.analysis.regional_position_score import ALIAS_HZ
from objective import coupled_likelihood,PairedObjective

class IndependentPairReview(unittest.TestCase):
    def setUp(self):
        self.score=PositionScore('V16',125.,1.6,.5,3.,1.)

    def test_actual_likelihood_preserves_equal_visibility_marginal(self):
        # Integrate implemented joint density, rather than restating boost algebra.
        # Equal visibility has equal odds: common-identity marginal then equals
        # the independent model at each fixed measurement in the other row.
        pred=np.array([[0.,300.,-200.,1800.],[3.,210.,-180.,1700.]])
        visible=np.ones_like(pred,dtype=bool)
        grid=np.r_[-ALIAS_HZ/2,np.arange(-4000.,5000.1,20.),ALIAS_HZ/2]
        integrals=[]
        for rho in (0.,.9,1.):
            density=np.array([np.exp(-coupled_likelihood(np.array([10.,peer]),pred,visible,self.score,[[0,1]],rho).nll) for peer in grid])
            integrals.append(float(np.trapezoid(density,grid)))
        np.testing.assert_allclose(integrals[1:],integrals[0],rtol=1e-10,atol=1e-15)

    def make_objective(self,receiver,rf,pairs):
        obs=PositionObservations(('a','b','c'),np.array([0.,0.,1.]),np.zeros(3),np.asarray(rf),np.asarray(receiver),np.ones(3,int),np.ones(3))
        bank=PositionOrbitBank(np.arange(1,5),np.arange(-2.,3.),np.broadcast_to([7000.,1000.,1000.],(4,5,3)).copy(),np.broadcast_to([0.,7.,0.],(4,5,3)).copy())
        return PairedObjective(obs,bank,RegionalPrior(),self.score,pairs=pairs,rho=.9)

    def test_requires_distinct_receivers_same_rf(self):
        self.make_objective([0,1,0],[1e9,1e9,1e9],[[0,1]])
        with self.assertRaisesRegex(ValueError,'distinct receivers'):
            self.make_objective([0,0,1],[1e9,1e9,1e9],[[0,1]])
        with self.assertRaisesRegex(ValueError,'identical RF'):
            self.make_objective([0,1,0],[1e9,1.1e9,1e9],[[0,1]])

if __name__=='__main__':unittest.main()
