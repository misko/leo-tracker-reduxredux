"""Nonlinear preparation checks: exact phase propagation and objective scalar."""

import copy
import unittest

import numpy as np
from scipy.special import logsumexp

import adapter as a
import quadrature02 as q
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon


class NonlinearTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contexts = {case:a.load_context(case) for case in a.CASES}

    def test_domain_moments_and_prior_weights(self):
        for case, d in self.contexts.items():
            law = q.prior(d)
            self.assertEqual(law['nu'], 3.)
            self.assertLess(law['conditional_sd_s'], law['original_marginal_sd_s'])
            nodes, weights = q.phase_nodes(d, 1281)
            self.assertLess(abs(np.exp(logsumexp(weights))-1), 1e-8)
            self.assertGreater(nodes.min(), -15.)
            self.assertLess(nodes.max(), 15.)

    def test_vector_phase_geometry_matches_original_scalar(self):
        phases = np.array([-15., -1.123, 0., 2.345, 15.])
        for case, d in self.contexts.items():
            x = np.asarray(d['arms']['c0']['endpoint_east_north_km'])
            vector = q.phase_geometry(d, x, phases)
            times = np.asarray(d['target_track']['times'])
            labels = np.zeros(len(times), int); coordinates = latlon(x)
            scale = d['target_track']['rf_hz']/11.5e9
            for k, phase in enumerate(phases):
                f, e = paired_phase_frequency(d['target_sky'], times, labels,
                                               np.array([phase]), *coordinates)
                b = paired_frequency_modes(d['target_sky'], d['target_mode_bank'], times,
                                            labels, np.array([phase]), *coordinates)
                np.testing.assert_array_equal(vector['frequency_hz'][k], f*scale)
                np.testing.assert_array_equal(vector['elevation_deg'][k], e)
                np.testing.assert_array_equal(vector['shape_columns_hz'][k], b*scale)

    def test_per_phase_low_rank_matches_dense_covariance(self):
        phases = np.array([-2., .3, 3.])
        for case, d in self.contexts.items():
            saved = d['arms']['c0']; x = np.asarray(saved['endpoint_east_north_km'])
            p = q.build(d, 'c0', saved['phase_reference'], a.BRANCHES[0], 81)
            components = q.conditional_components(d, p, x)
            for include_shape in (False, True):
                values = q.node_log_density(d, components, phases, include_shape)
                for k in range(len(phases)):
                    covariance = components['base_covariance_hz2'].copy()
                    if include_shape:
                        b = values['geometry']['shape_columns_hz'][k]
                        covariance += b@b.T
                    raw = components['base_raw_hz']-values['geometry']['frequency_hz'][k]
                    expected = raw@np.linalg.solve(covariance, raw)+np.linalg.slogdet(covariance)[1]+components['density_normalization']
                    self.assertAlmostEqual(-2*values['log_density'][k], expected, places=6)

    def test_repeated_evaluation_parent_cache_and_optimizer_scalar(self):
        h = q.FD_STEP_KM
        for case, d in self.contexts.items():
            for arm in a.ARMS:
                saved = d['arms'][arm]; x = np.asarray(saved['endpoint_east_north_km'])
                for branch in a.BRANCHES:
                    p = q.build(d, arm, saved['phase_reference'], branch, 81)
                    parent = copy.deepcopy(p.original_parent_calculate(x))
                    first, second = p.calculate(x), p.calculate(x)
                    self.assertEqual(first['negative_twice_elbo'], second['negative_twice_elbo'])
                    np.testing.assert_array_equal(parent['residual'], p.original_parent_calculate(x)['residual'])
                    np.testing.assert_array_equal(parent['coefficient'], first['coefficient'])
                    offsets = []
                    for at in (x, x+np.array([h, 0]), x-np.array([h, 0])):
                        c = p.calculate(at); residual = p.residual(at)
                        offsets.append(float(residual@residual)-c['negative_twice_elbo'])
                    self.assertLess(np.ptp(offsets), 1e-8)
                    self.assertGreater(first['nonlinear_target_prediction']['objective'], 0)


if __name__ == '__main__':
    unittest.main()
