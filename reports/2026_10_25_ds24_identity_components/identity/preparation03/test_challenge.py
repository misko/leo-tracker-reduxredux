"""Owned numerical tests, synthetic data only; no orbit propagation."""
import itertools
import unittest
from unittest.mock import patch
import time
import numpy as np
from scipy.integrate import quad
from scipy.special import logsumexp
import challenge as c


class NumericalTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(25)
        self.raw = rng.normal(size=(4, 7))
        a = rng.normal(size=(7, 4))
        self.cov = np.eye(7) + a @ a.T
        self.shape = rng.normal(size=(4, 7, 3))
        self.groups = np.array([0,0,0,1,1,1,1])

    def test_rank3_full_dense_density_every_alias(self):
        hypotheses, shifts = c.alias_vectors(self.groups, [-1,0,1])
        shifts = shifts / c.PERIOD
        actual = c.conditional_costs(self.raw, self.cov, self.shape, shifts)
        expected = np.empty(actual.shape)
        for node in range(4):
            covariance = self.cov + self.shape[node] @ self.shape[node].T
            for alias, shift in enumerate(shifts):
                raw = self.raw[node] + shift
                expected[node,alias] = raw @ np.linalg.solve(covariance, raw) + np.linalg.slogdet(covariance)[1] + 7*np.log(2*np.pi)
        self.assertLess(np.max(abs(actual-expected)), 1e-10)

    def test_exact_alias_relabeling_and_permutation(self):
        _, shifts = c.alias_vectors(self.groups, [-1,0,1])
        _, translated = c.alias_vectors(self.groups, [-2,-1,0])
        # A common +period measurement translation and -1 alias translation.
        # Rescale all frequencies here for a well-conditioned synthetic test.
        a = c.conditional_costs(self.raw, self.cov, self.shape, shifts/c.PERIOD)
        b = c.conditional_costs(self.raw+1, self.cov, self.shape, translated/c.PERIOD)
        self.assertLess(np.max(abs(a-b)), 1e-10)
        perm = np.array([4,1,6,0,3,2,5])
        x = c.conditional_costs(self.raw[:,perm], self.cov[np.ix_(perm,perm)],
                                self.shape[:,perm], shifts[:,perm]/c.PERIOD)
        self.assertLess(np.max(abs(a-x)), 1e-10)
        self.assertAlmostEqual(float(logsumexp(-a[0]/2)-np.log(len(a[0]))),
                               float(logsumexp(-a[0,::-1]/2)-np.log(len(a[0]))), places=12)

    def test_finite_alias_mixture_is_normalized(self):
        # Both the physical and unresolved models use this normalized measure;
        # covariance choice does not change mixture mass.
        for sd in (0.7, 2.4):
            density = lambda y: np.mean(np.exp(-.5*((y+np.arange(-4,5))/sd)**2)/(np.sqrt(2*np.pi)*sd))
            value = quad(density, -40, 40, epsabs=1e-11)[0]
            self.assertAlmostEqual(value, 1., places=10)

    def test_held_owner_joint_minus_discovery(self):
        covariance = self.cov + self.shape[0] @ self.shape[0].T
        raw = self.raw[0]
        split = 3
        a = covariance[:split,:split]; b = covariance[split:,:split]
        conditional_cov = covariance[split:,split:] - b @ np.linalg.solve(a,b.T)
        conditional_raw = raw[split:] - b @ np.linalg.solve(a,raw[:split])
        nll = lambda y,v: y@np.linalg.solve(v,y)+np.linalg.slogdet(v)[1]+len(y)*np.log(2*np.pi)
        self.assertAlmostEqual(nll(raw,covariance)-nll(raw[:split],a),
                               nll(conditional_raw,conditional_cov), places=11)

    def test_timeout_stops_candidate_loop(self):
        # Exercise the actual nested runner handler: a deadline exception must
        # terminate the job, rather than become one blocked candidate and carry on.
        saved = []
        item = dict(case='synthetic', target={})
        read = lambda path: dict(rows=[item]) if path.name=='inventory.json' else dict(
            status='complete',candidate_indices=[1,2],candidate_norads=[1,2])
        d = dict(arms={'c0':dict(endpoint_east_north_km=[0.,0.])})
        entries = [dict(points=3)]
        cavity = dict(phase_qualified=True,precision_qualified=True,support_qualified=True)
        comp = dict(raw=np.zeros(3))
        with patch.object(c,'read',read), patch.object(c.m.t,'load_target',return_value=d), \
             patch.object(c,'records',return_value=entries), patch.object(c,'cavity',return_value=(d,cavity)), \
             patch.object(c.owners,'components',return_value=comp), patch.object(c,'null_score',return_value={}), \
             patch.object(c,'alias_diagnostics',return_value=dict(objective=1.)), \
             patch.object(c,'candidate',return_value={}), patch.object(c,'score',side_effect=TimeoutError('test cap')) as score, \
             patch.object(c,'write',side_effect=lambda name,value:saved.append((name,value))):
            result=c.exact_job('synthetic','c0',time.monotonic()+10.)
        self.assertEqual(score.call_count,1)
        self.assertEqual(result['status'],'failed')
        self.assertIn('TimeoutError',saved[-1][1]['error'])


if __name__ == '__main__':
    unittest.main()
