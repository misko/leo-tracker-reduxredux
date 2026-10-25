"""Focused numerical/component tests; no RF capture or golden mutation."""
import copy
import unittest
import numpy as np
from heldout import gaussian_score, fold_assignment, training_data, build, causal_reference, held_posterior
from investigate_dsx01_localization_failures import fit


class GaussianTests(unittest.TestCase):
    def test_density_matches_dense_covariance(self):
        rng = np.random.default_rng(9)
        raw = rng.normal(size=19);u = rng.normal(size=(19, 6));sigma = rng.uniform(.4, 2, 19)
        got = gaussian_score(raw, u, sigma)
        covariance = np.diag(sigma**2)+u@u.T
        expected = raw@np.linalg.solve(covariance, raw)+np.linalg.slogdet(covariance)[1]+19*np.log(2*np.pi)
        self.assertAlmostEqual(got['negative_twice_log_density'], expected, places=11)

    def test_full_shared_covariance_changes_joint_density(self):
        raw = np.full(12, 3.);u = np.ones((12, 1));s = np.ones(12)
        joint = gaussian_score(raw, u, s)['negative_twice_log_density']
        independent = sum(gaussian_score(raw[i:i+1], u[i:i+1], s[i:i+1])['negative_twice_log_density'] for i in range(12))
        self.assertGreater(independent-joint, 20.)

    def test_position_sensitive_signal_is_retained(self):
        t = np.linspace(-1, 1, 31)
        a = gaussian_score(t*15., np.zeros((31, 0)), np.ones(31))
        b = gaussian_score(np.zeros(31), np.zeros((31, 0)), np.ones(31))
        self.assertGreater(a['negative_twice_log_density']-b['negative_twice_log_density'], 2000.)


class FrozenInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from matched_controls import load_baseline
        cls.data = load_baseline('DS24-0017')

    def test_folds_partition_all_likelihood_families(self):
        groups = fold_assignment(self.data)
        self.assertEqual(groups, fold_assignment(self.data))
        self.assertEqual(len(set().union(*map(set, groups))), sum(map(len, groups)))
        for held in groups:
            d = training_data(self.data, held)
            p = build(d, 'c0', causal_reference(d, held), 'baseline')
            self.assertFalse(np.isin(np.asarray(p.labels)[p.flat_labels[p.keep]], held).any())
            self.assertFalse(any(e['candidate_index'] in held for e in d['entries']))

    def test_held_values_cannot_change_train_objective_or_posterior(self):
        held = fold_assignment(self.data)[0]
        d = training_data(self.data, held)
        p = build(d, 'fitted_c', causal_reference(d, held), 'sharedRF50')
        x = np.array([.2, -.3]);before = p.calculate(x)
        held_posterior(p, p.curved_calculate(x), d, held)
        changed = dict(d);changed['scan'] = copy.copy(d['scan']);changed['scan'].tracks = copy.deepcopy(d['scan'].tracks)
        held_tracks = {i for i, r in zip(p.members, p.rows, strict=True) if r['candidate_index'] in held}
        held_tracks.update(e['track_index'] for e in self.data['entries'] if e['candidate_index'] in held)
        for i in held_tracks:
            changed['scan'].tracks[i]['values'] = np.asarray(changed['scan'].tracks[i]['values'])+12345.
        q = build(changed, 'fitted_c', causal_reference(changed, held), 'sharedRF50')
        after = q.calculate(x)
        np.testing.assert_array_equal(before['coefficient'], after['coefficient'])
        np.testing.assert_array_equal(before['noise_precision'], after['noise_precision'])
        self.assertEqual(before['negative_twice_elbo'], after['negative_twice_elbo'])
        np.testing.assert_array_equal(p.residual(x), q.residual(x))
        # A real bounded optimization trajectory must also be identical.
        a = fit(p, np.zeros(2), iterations=8)
        b = fit(q, np.zeros(2), iterations=8)
        np.testing.assert_array_equal(a['parameters'], b['parameters'])



if __name__ == '__main__':
    unittest.main()
