"""Owned algebra and real-context regression checks; no position fits."""

import copy
import unittest

import numpy as np

import adapter as a


class CovarianceTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(21025)
        self.ye, self.yt = rng.normal(size=6), rng.normal(size=4)
        self.he, self.ht = rng.normal(size=(6, 3)), rng.normal(size=(4, 3))
        self.se, self.st = np.linspace(1, 2, 6), np.linspace(2, 3, 4)
        self.ge = np.repeat(np.arange(2), 3)
        self.phase, self.shape = rng.normal(size=4), rng.normal(size=(4, 3))
        self.gram = np.array([[3., .5, .2], [.5, 2., .3], [.2, .3, 1.5]])

    def calculate(self, include_shape=True, **kwargs):
        args = dict(parent_raw=self.ye, parent_design=self.he, parent_sigma=self.se,
                    parent_groups=self.ge, target_raw=self.yt, target_design=self.ht,
                    target_sigma=self.st, phase=self.phase, shape=self.shape,
                    posterior_precision=self.gram, include_shape=include_shape)
        args.update(kwargs)
        return a.joint_prediction(**args)

    def test_dense_joint_normalized_objective(self):
        r = self.calculate()
        cov = r['covariance_hz2']; y = r['raw_hz']
        expected = y@np.linalg.solve(cov, y)+np.linalg.slogdet(cov)[1]+len(y)*np.log(2*np.pi)
        self.assertAlmostEqual(r['joint']['objective'], expected, places=8)
        np.linalg.cholesky(cov)

    def test_shared_cross_covariance_retained(self):
        r = self.calculate()
        expected = self.he@np.linalg.solve(self.gram, self.ht.T)
        np.testing.assert_allclose(r['covariance_hz2'][:6, 6:], expected, atol=1e-12)
        self.assertGreater(np.linalg.norm(expected), 0)

    def test_only_shape_covariance_changes(self):
        zero, prior = self.calculate(False), self.calculate(True)
        expected = np.zeros((10, 10)); expected[6:, 6:] = self.shape@self.shape.T
        np.testing.assert_allclose(prior['covariance_hz2']-zero['covariance_hz2'], expected, atol=1e-10)
        self.assertGreaterEqual(np.linalg.eigvalsh(expected).min(), -1e-12)
        self.assertEqual(zero['existing']['objective'], prior['existing']['objective'])

    def test_zero_shape_equivalence_and_redaction(self):
        zero = self.calculate(False)
        empty = self.calculate(True, shape=np.zeros((4, 3)))
        self.assertEqual(zero['joint']['objective'], empty['joint']['objective'])
        changed = self.calculate(True, target_raw=self.yt+100)
        self.assertEqual(changed['existing']['objective'], zero['existing']['objective'])

    def test_schur_conditional_closure(self):
        r = self.calculate()
        self.assertLess(abs(r['closure']), 1e-8)
        self.assertAlmostEqual(r['target_whitened_innovation']@r['target_whitened_innovation'],
                               r['target_conditional']['quadratic'], places=10)


class RealContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contexts = {case:a.load_context(case) for case in a.CASES}

    def test_ids_alias_noise_owner_bindings(self):
        for case, d in self.contexts.items():
            t = d['target']
            self.assertEqual(t['points'], 49 if case.endswith('0095') else 43)
            self.assertEqual(t['alias'], 1 if case.endswith('0095') else 0)
            self.assertEqual(len(t['observation_ids']), len(set(t['observation_ids'])))
            for arm in a.ARMS:
                self.assertFalse(set(t['observation_ids']) & set(d['parent_membership'][arm]['accepted_observation_ids']))

    def test_parent_prediction_redaction_and_dormant_slots(self):
        for case, d in self.contexts.items():
            for arm in a.ARMS:
                saved = d['arms'][arm]; x = np.asarray(saved['endpoint_east_north_km'])
                p = a.build(d, arm, saved['phase_reference'], a.BRANCHES[0])
                c = p.calculate(x)
                baseline = p.original_parent_calculate(x)
                self.assertAlmostEqual(c['parent_negative_twice_elbo'], baseline['negative_twice_elbo'], places=6)
                for field in ('coefficient', 'noise_precision', 'coefficient_prior_precision'):
                    np.testing.assert_array_equal(c[field], baseline[field])
                nt = len(d['target']['observation_ids'])
                ht = c['predictive_decomposition']['shared_design'][-nt:]
                radio = p.hardware.shape[1]+p.smooth.shape[1]
                np.testing.assert_array_equal(ht[:, radio:], np.zeros_like(ht[:, radio:]))
                changed = dict(d, target_track=dict(d['target_track']))
                # linear_geometry uses scan tracks, so a scientific input redaction
                # test requires a shallow scan copy rather than changing metadata.
                changed['scan'] = copy.copy(d['scan'])
                changed['scan'].tracks = list(d['scan'].tracks)
                idx = d['target']['track_index']
                changed['scan'].tracks[idx] = dict(d['target_track'], values=np.asarray(d['target_track']['values'])+999.)
                changed['target_track'] = changed['scan'].tracks[idx]
                q = a.build(changed, arm, saved['phase_reference'], a.BRANCHES[0])
                z = q.calculate(x)
                for field in ('coefficient', 'noise_precision', 'coefficient_prior_precision'):
                    np.testing.assert_array_equal(c[field], z[field])
                self.assertEqual(c['parent_negative_twice_elbo'], z['parent_negative_twice_elbo'])
                np.testing.assert_array_equal(c['target_prediction']['phase_column_hz'], z['target_prediction']['phase_column_hz'])
                self.assertNotEqual(c['negative_twice_elbo'], z['negative_twice_elbo'])

    def test_real_shape_change_and_c_arm_matching(self):
        for case, d in self.contexts.items():
            ids = []
            for arm in a.ARMS:
                saved = d['arms'][arm]; x = np.asarray(saved['endpoint_east_north_km'])
                pp = [a.build(d, arm, saved['phase_reference'], b) for b in a.BRANCHES]
                cc = [p.calculate(x) for p in pp]
                t = len(d['target']['observation_ids']); b = cc[0]['target_prediction']['shape_columns_hz']
                diff = cc[1]['predictive_decomposition']['covariance_hz2']-cc[0]['predictive_decomposition']['covariance_hz2']
                expected = np.zeros_like(diff); expected[-t:, -t:] = b@b.T
                np.testing.assert_allclose(diff, expected, atol=1e-7)
                np.testing.assert_array_equal(cc[0]['coefficient'], cc[1]['coefficient'])
                ids.append(pp[0].experimental_target['observation_ids'])
            self.assertEqual(*ids)

    def test_repeated_position_never_mutates_cached_parent(self):
        for case, d in self.contexts.items():
            for arm in a.ARMS:
                saved = d['arms'][arm]; x = np.asarray(saved['endpoint_east_north_km'])
                for branch in a.BRANCHES:
                    p = a.build(d, arm, saved['phase_reference'], branch)
                    parent_before = copy.deepcopy(p.original_parent_calculate(x))
                    first, second = p.calculate(x), p.calculate(x)
                    parent_after = p.original_parent_calculate(x)
                    for field in ('negative_twice_elbo', 'normalization_constant'):
                        self.assertEqual(first[field], second[field])
                        self.assertEqual(parent_before[field], parent_after[field])
                    np.testing.assert_array_equal(first['residual'], second['residual'])
                    np.testing.assert_array_equal(parent_before['residual'], parent_after['residual'])


if __name__ == '__main__':
    unittest.main()
