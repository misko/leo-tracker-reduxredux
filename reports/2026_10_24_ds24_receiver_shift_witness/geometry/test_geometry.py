"""Owned numerical tests for the diagnostic, without scientific fixture edits."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import geometry as diagnostic


class GeometryTests(unittest.TestCase):
    def test_schur_matches_augmented_gaussian_covariance(self):
        rng = np.random.default_rng(145)
        jacobian = rng.normal(size=(30, 2))
        features = rng.normal(size=(30, 5))
        weights = rng.uniform(.2, 2, 30)
        precision = rng.uniform(.4, 2, 5)
        info, _, _ = diagnostic.schur_information(jacobian, features, weights, precision)
        all_features = np.column_stack((jacobian, features))
        gram = np.diag(np.r_[np.zeros(2), precision]) + all_features.T@(all_features*weights[:, None])
        np.testing.assert_allclose(np.linalg.inv(info), np.linalg.inv(gram)[:2, :2], rtol=1e-11)
        reduced, _, _ = diagnostic.schur_information(jacobian, features[:, :3], weights, precision[:3])
        self.assertGreaterEqual(float(np.linalg.eigvalsh(reduced-info).min()), -1e-10)

    def test_blocks_partition_and_rx1_indices(self):
        for fitted_c in (False, True):
            for width in (11, 42):
                p = SimpleNamespace(hardware=np.empty((1, 8+fitted_c)), smooth=np.empty((1, 2*width)),
                                    labels=[0, 1], supported=[0], members=[0, 1, 2])
                block = diagnostic.blocks(p)
                indices = np.concatenate(list(block.values()))
                np.testing.assert_array_equal(np.sort(indices), np.arange(len(indices)))
                self.assertEqual(len(np.unique(indices)), len(indices))
                self.assertEqual(len(block['receiver_extra_rx1']), 31 if width == 42 else 0)
                self.assertEqual(len(block['receiver_slow']), 22)

    def test_decomposition_uses_curved_normalization_and_full_predictive(self):
        p = SimpleNamespace(hardware=np.empty((4, 8)), smooth=np.empty((4, 22)), labels=[0, 1],
                            supported=[0], members=[0, 1, 2], keep=np.ones(4, bool),
                            noise_groups=np.array([0, 1, 2, 0]), analysis_powers=np.array([.5, .8, 1.]),
                            point_noise=np.array([2., 3., 4., 2.]))
        n = sum(len(ix) for ix in diagnostic.blocks(p).values())
        latent = np.arange(n)/100.
        precision = np.linspace(.5, 1.5, n)
        residual = np.array([1., -2., 3., -4.])
        noise = np.array([.8, .9, 1.1])
        weighted = float(np.sum(p.analysis_powers[p.noise_groups]*noise[p.noise_groups]*residual**2/p.point_noise**2))
        curved = dict(latent_coefficient=latent, coefficient_prior_precision=precision,
                      conditional_residual_hz=residual, noise_precision=noise,
                      quadratic=weighted+np.sum(latent**2*precision), logvolume=5.,
                      noise_gamma_cost=3., prior_gamma_cost=2., normalization_constant=100.)
        curved['negative_twice_elbo'] = curved['quadratic']+110.
        p.curved_calculate = lambda x: dict(curved)
        p.calculate = lambda x: dict(curved, negative_twice_elbo=curved['negative_twice_elbo']+17.,
                                     normalization_constant=107.)
        terms = diagnostic.terms(p, np.zeros(2))
        self.assertAlmostEqual(terms['predictive'], 17.)
        self.assertEqual(terms['normalization'], 100.)
        self.assertAlmostEqual(sum(terms.values()), curved['negative_twice_elbo']+17.)

    def test_legacy_reference_excludes_final_posterior_update(self):
        history = [dict(fit=dict(parameters=[a, 0])) for a in (1., 2., 3.)]
        labels = [0, 1]
        def factory(d, arm, reference, model):
            return SimpleNamespace(labels=labels,
                state=lambda x: dict(phases=np.asarray(reference)+x[0]),
                calculate=lambda x: dict(negative_twice_elbo=23.))
        record = dict(phase_reference=[6., 6.], history=history,
                      endpoint_east_north_km=[3., 0.], negative_twice_elbo=23.)
        with patch.object(diagnostic, 'build', factory), patch.object(diagnostic, 'factor_contract', lambda p, e: 'contract'):
            result = diagnostic.saved_replay(dict(means=[0., 0.], entries=[], powers=[]), 'c0', 'baseline', record)
        np.testing.assert_array_equal(result['used_phase_reference'], [3., 3.])
        self.assertEqual(result['reference_kind'], 'history_reconstructed_final_fit_reference')


if __name__ == '__main__':
    unittest.main()
