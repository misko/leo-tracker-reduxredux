import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import numerical


class NumericalTests(unittest.TestCase):
    def test_central_gradient_and_box_projection(self):
        r = numerical.gradient_probe(lambda x: float(x@x), np.array([2., -3.]))
        np.testing.assert_allclose(r['gradients'], [[4., -6.], [4., -6.]])
        self.assertTrue(r['stable'])
        boundary = numerical.gradient_probe(lambda x: float(-x.sum()), np.array([12.5, 12.5]))
        self.assertEqual(boundary['projected_gradient_inf'], 0.)

    def test_rescue_only_for_abnormal_nonstationary_solve(self):
        bad = SimpleNamespace(x=np.array([2., 3.]), success=False,
                              message='ABNORMAL: ', fun=13., nfev=6)
        good = SimpleNamespace(x=np.zeros(2), success=True, message='success', fun=0., nfev=12)
        with patch.object(numerical, 'minimize', side_effect=[bad, good]) as mock:
            result, receipt = numerical.position_solve(lambda x: float(x@x), [2., 3.])
        self.assertIs(result, good)
        self.assertTrue(receipt['rescue']['adopted'])
        self.assertEqual(mock.call_args_list[1].kwargs['method'], 'L-BFGS-B')
        self.assertTrue(callable(mock.call_args_list[1].kwargs['jac']))

    def test_stationary_success_needs_no_rescue(self):
        bad = SimpleNamespace(x=np.zeros(2), success=False,
                              message='iteration limit', fun=0., nfev=6)
        with patch.object(numerical, 'minimize', return_value=bad) as mock:
            result, receipt = numerical.position_solve(lambda x: float(x@x), [0., 0.])
        self.assertFalse(result.success)
        self.assertFalse(receipt['rescue_triggered'])
        self.assertEqual(mock.call_count, 1)

    def test_actual_jacobian_calls_are_counted(self):
        called=[]
        result, receipt=numerical.position_solve(lambda x:called.append(1) or float(x@x),[2.,3.])
        self.assertEqual(receipt['actual_objective_calls'],len(called))
        self.assertLessEqual(len(called),receipt['max_actual_calls'])
        self.assertTrue(receipt['central_stationary'])

    def test_worse_rescue_is_not_adopted(self):
        bad = SimpleNamespace(x=np.array([1., 1.]), success=False, message='ABNORMAL: ', fun=2., nfev=6)
        worse = SimpleNamespace(x=np.array([3., 3.]), success=True, message='success', fun=18., nfev=12)
        with patch.object(numerical, 'minimize', side_effect=[bad, worse]):
            result, receipt = numerical.position_solve(lambda x: float(x@x), [1., 1.])
        self.assertIs(result, bad)
        self.assertFalse(receipt['rescue']['adopted'])


if __name__ == '__main__':
    unittest.main()
