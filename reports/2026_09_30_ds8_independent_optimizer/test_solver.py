import unittest
import numpy as np
from solver import fit_model


class Quadratic:
    def __init__(self,target,wrong=False):
        self.target=np.array(target)
        self.wrong=wrong
        self.matrix=np.array([[4.,.4,.2],[.4,2.,.3],[.2,.3,1.]])

    def evaluate(self,x,gradient=True):
        delta=np.asarray(x)-self.target
        g=-2*self.matrix@delta
        if self.wrong:
            g=np.zeros(3)
        return dict(score=-423000.-float(delta@self.matrix@delta),gradient=g)


class SolverTest(unittest.TestCase):
    def test_coupled_interior_recovery(self):
        fit=fit_model(Quadratic([.3,-.8,1.2]),[0.,0.,0.])
        self.assertTrue(fit['qualified'],fit)
        np.testing.assert_allclose(fit['x'],[.3,-.8,1.2],atol=1e-5)

    def test_boundary_optimum_is_not_qualified(self):
        fit=fit_model(Quadratic([20.,0.,0.]),[0.,0.,0.])
        self.assertTrue(fit['boundary'])
        self.assertFalse(fit['qualified'])

    def test_incorrect_zero_gradient_is_rejected(self):
        fit=fit_model(Quadratic([.3,-.8,1.2],wrong=True),[0.,0.,0.])
        self.assertGreater(fit['gradient_audit'],.02)
        self.assertFalse(fit['qualified'])


if __name__=='__main__':
    unittest.main()
