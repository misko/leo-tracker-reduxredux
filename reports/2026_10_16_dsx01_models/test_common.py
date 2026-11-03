"""Shared evaluation checks independent of storage, hardware and PostgreSQL."""
import unittest
from types import SimpleNamespace

import numpy as np

from common import refit, distance_km, jsonable


class QuadraticModel:
    size = 9
    clock_count = 1
    group_scales = np.zeros(0)
    group_limits = np.zeros(0)
    prior = SimpleNamespace(radius_km=100.)
    bank = SimpleNamespace(numbers=np.array([10,20]), nodes_s=np.array([-30.,40.]))
    observations = SimpleNamespace(times_s=np.array([0.,10.]))
    basis = np.array([[1.],[-1.]])/np.sqrt(2)

    def __init__(self):
        self.calls = 0
        self.target = np.array([2.,-3.,300.,1.,-200.,-1.,80.,.2,.3])
        self.scale = np.array([1.,1.,200.,2.,200.,2.,200.,1.,1.])

    def evaluate_joint(self, v, n):
        self.calls += 1
        d = (v-self.target)/self.scale
        extra = (n-25.)/50.
        value = .5*float(d@d+extra@extra)
        return value, d/self.scale, extra/50., SimpleNamespace(nll=value)


class CommonTests(unittest.TestCase):
    def context(self):
        model = QuadraticModel()
        return SimpleNamespace(model=model, fixed_c=False, deadline=float('inf'))

    def test_budget_returns_best_feasible_without_hidden_calls(self):
        ctx = self.context()
        fit = refit(ctx, np.zeros(9), np.zeros(1), max_evaluations=9, max_seconds=5)
        self.assertEqual(ctx.model.calls, fit['diagnostics']['evaluations'])
        self.assertLessEqual(ctx.model.calls,9)
        self.assertLess(fit['diagnostics']['objective'], .001)
        np.testing.assert_allclose(fit['vector'][:2],[2.,-3.],atol=1e-5)

    def test_fixed_c_cannot_move_and_failed_seed_rejected(self):
        ctx = self.context()
        ctx.fixed_c = True
        v = np.zeros(9)
        v[6] = 150.
        fit = refit(ctx,v,np.zeros(1),max_evaluations=10,max_seconds=5)
        self.assertEqual(fit['vector'][6],0.)
        v[:2] = [101.,101.]
        with self.assertRaises(ValueError):
            refit(ctx,v,np.zeros(1),max_evaluations=10,max_seconds=5)

    def test_tiny_budget_has_honest_nonstationary_result(self):
        ctx = self.context()
        fit = refit(ctx,np.zeros(9),np.zeros(1),max_evaluations=1,max_seconds=5)
        self.assertEqual(ctx.model.calls,1)
        self.assertFalse(fit['diagnostics']['accepted'])
        self.assertGreater(fit['diagnostics']['stationarity'],.001)

    def test_geographic_distance_and_nonfinite_serialization(self):
        self.assertEqual(distance_km([37.,-122.],[37.,-122.]),0.)
        self.assertAlmostEqual(distance_km([0.,0.],[0.,1.]),111.19508,places=4)
        self.assertIsNone(jsonable(float('nan')))


if __name__ == '__main__':
    unittest.main()
