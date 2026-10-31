import unittest
import numpy as np
from continue_0154_numerics import gradient_audit,centered_fit


class NumericalContinuationTests(unittest.TestCase):
    def test_audit_distinguishes_forward_difference_bias_at_optimum(self):
        objective=lambda x:float(10*x[0]**2+3*x[1]**2)
        audit=gradient_audit(objective,np.zeros(2))
        self.assertTrue(audit['finite'])
        np.testing.assert_allclose(audit['rows'][1]['forward_gradient'],[.01,.003])
        np.testing.assert_allclose(audit['rows'][1]['centered_gradient'],[0.,0.],atol=1e-12)

    def test_centered_solver_keeps_counted_evaluation_budget(self):
        result=centered_fit(lambda x:float((x[0]-.5)**2+2*(x[1]+.25)**2),np.array([1.,-2.]))
        self.assertTrue(result['success'])
        np.testing.assert_allclose(result['endpoint_east_north_km'],[.5,-.25],atol=1e-4)
        self.assertLessEqual(result['total_objective_evaluations'],240)


if __name__=='__main__':unittest.main()
