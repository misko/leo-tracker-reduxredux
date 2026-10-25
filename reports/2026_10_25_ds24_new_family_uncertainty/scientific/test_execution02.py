"""Runner boundary and endpoint numerical qualification checks; no fits."""

import unittest
from unittest.mock import patch

import numpy as np

import adapter as a
import execution02 as e


class RunnerTests(unittest.TestCase):
    def test_receipts_are_required_before_run(self):
        self.assertEqual(len(e.required_receipts()), 3)
        self.assertTrue(all(path.is_absolute() for path in e.required_receipts()))
        self.assertEqual(e.ARM_SECONDS, 180.)
        self.assertEqual(e.GLOBAL_SECONDS, 1200.)

    def test_endpoint_qualification_has_five_points_and_both_references(self):
        calls = []
        class P:
            experimental_branch = a.BRANCHES[0]
        def components(d, p, at):
            calls.append(np.asarray(at))
            return dict(at=np.asarray(at))
        def integrate(d, c, n, include):
            return dict(objective=float(c['at']@c['at'])+100., quadrature_prior_mass=1.,
                        minimum_node_elevation_deg=30., minimum_domain_endpoint_elevation_deg=30.)
        def adaptive(d, c, include):
            return dict(objective=float(c['at']@c['at'])+100.)
        with patch.object(e.q, 'conditional_components', components), patch.object(e.q, 'integrate', integrate), patch.object(e.q, 'adaptive_reference', adaptive):
            result = e.endpoint_qualification({}, P(), np.array([1., 2.]))
        self.assertTrue(result['passed'])
        self.assertEqual(len(calls), 5)
        np.testing.assert_allclose(result['gradients']['1281'], [2., 4.], atol=1e-10)

    def test_numerically_failed_endpoint_is_not_refined(self):
        class P:
            experimental_branch = a.BRANCHES[1]
        def integrate(d, c, n, include):
            return dict(objective=100.+(1. if n == 1281 else 0.), quadrature_prior_mass=1.,
                        minimum_node_elevation_deg=30., minimum_domain_endpoint_elevation_deg=30.)
        with patch.object(e.q, 'conditional_components', lambda *args:{}), patch.object(e.q, 'integrate', integrate), patch.object(e.q, 'adaptive_reference', lambda *args:dict(objective=100.)):
            result = e.endpoint_qualification({}, P(), np.zeros(2))
        self.assertFalse(result['passed'])
        self.assertEqual(result['maximum_score_error_vs_adaptive'], 1.)


if __name__ == '__main__':
    unittest.main()
