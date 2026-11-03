"""Component-owned tests for the trajectory proposal's evidence accounting."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from numpy.testing import assert_allclose, assert_array_equal

from model_b import (ALIAS_HZ, TrajectoryLikelihood, build_tracklets, circular, fit,
                     training_observations)


def observations(times, measured, receivers=None, channels=None):
    times = np.asarray(times, float)
    return SimpleNamespace(times_s=times, measured_hz=np.asarray(measured, float),
        receiver=np.zeros(len(times), int) if receivers is None else np.asarray(receivers),
        channel=np.ones(len(times), int) if channels is None else np.asarray(channels),
        rf_hz=np.linspace(11.1e9, 11.2e9, len(times)))


class TrajectoryTests(unittest.TestCase):
    def test_coherent_latent_identity_resists_pointwise_crossing_swap(self):
        # The third point alone prefers identity 1, while the trajectory strongly
        # supports identity 0. Swapping per point is impossible under one latent.
        residual = np.array([[0., 600.], [0., 400.], [160., 0.], [0., -400.], [0., -600.]])
        model = TrajectoryLikelihood(np.zeros(5, int), 125., [1., 1.], np.ones((5, 2)))
        _, _, posterior, weights = model.evaluate(residual)
        self.assertEqual(abs(residual[2]).argmin(), 1)
        self.assertGreater(posterior[0, 0], .999)
        self.assertGreater(weights[2, 0], weights[2, 1])

    def test_isolated_clutter_does_not_destroy_shared_identity(self):
        residual = np.column_stack(([0., 30., 60000., -30., 0.], np.full(5, 4000.)))
        model = TrajectoryLikelihood(np.zeros(5, int), 125., [1., 1.], np.ones((5, 2)))
        _, gradient, posterior, weights = model.evaluate(residual)
        self.assertGreater(posterior[0, 0], .999)
        self.assertLess(weights[2].sum(), 1e-12)
        assert_allclose(gradient[2], 0., atol=1e-12)

    def test_velocity_links_two_crossing_tracks_without_overlap(self):
        times = np.repeat(np.arange(7.), 2)
        measured = np.column_stack((-600 + 200 * np.arange(7.),
                                     600 - 200 * np.arange(7.))).ravel()
        labels = build_tracklets(observations(times, measured), gate_hz=250.)
        self.assertEqual(len(np.unique(labels)), 2)
        self.assertEqual(len(np.unique(labels[::2])), 1)
        self.assertEqual(len(np.unique(labels[1::2])), 1)
        self.assertNotEqual(labels[0], labels[1])
        # Each of these two segment lengths is seven, rather than an overlapping
        # rolling-window construction that would count central rows repeatedly.
        assert_array_equal(np.bincount(labels), [7, 7])

    def test_gap_jump_and_finite_duration_allow_source_breaks(self):
        obs = observations([0, 1, 2, 3, 20, 21, 80, 81],
                           [0, 10, 20, 5000, 5010, 5020, 5030, 5040])
        labels = build_tracklets(obs, maximum_duration_s=5.)
        self.assertEqual(labels[0], labels[2])
        self.assertNotEqual(labels[2], labels[3])
        self.assertNotEqual(labels[3], labels[4])
        self.assertNotEqual(labels[5], labels[6])

    def test_large_receiver_chirp_and_alias_wrap_are_linked(self):
        times = np.arange(20.) * .35
        measured = circular(-110000. - 4000. * times)
        labels = build_tracklets(observations(times, measured))
        self.assertEqual(len(np.unique(labels)), 1)

    def test_far_frequency_clutter_is_not_attached_to_short_cadence_track(self):
        times = np.arange(20.) * .35
        measured = -4000. * times
        measured[9] += 60000.
        labels = build_tracklets(observations(times, measured))
        self.assertNotEqual(labels[9], labels[8])
        self.assertNotEqual(labels[9], labels[10])
        self.assertEqual(labels[8], labels[10])

    def test_held_measured_cfo_invariance_in_extraction_and_likelihood(self):
        obs = observations(np.arange(8.), np.arange(8.) * 20.)
        mask = np.array([True, True, False, True, False, True, True, False])
        context = SimpleNamespace(observations=obs, train_mask=mask)
        training = training_observations(context)
        labels = build_tracklets(training)
        prediction = np.column_stack((training.measured_hz + 30., training.measured_hz + 900.))
        model = TrajectoryLikelihood(labels, 125., [1., 1.], np.ones_like(prediction))
        expected = model.evaluate(training.measured_hz[:, None] - prediction)
        obs.measured_hz[~mask] = [np.nan, 1e99, -1e99]
        changed = training_observations(context)
        assert_array_equal(changed.measured_hz, training.measured_hz)
        assert_array_equal(build_tracklets(changed), labels)
        actual = model.evaluate(changed.measured_hz[:, None] - prediction)
        for left, right in zip(expected, actual):
            assert_allclose(left, right, rtol=0, atol=0)

    def test_prediction_gradient_matches_finite_difference(self):
        rng = np.random.default_rng(43)
        residual = rng.normal(0., 180., (7, 3))
        labels = np.array([0, 0, 0, 1, 1, 1, 1])
        visibility = rng.uniform(.2, 1., residual.shape)
        model = TrajectoryLikelihood(labels, 125., [1., 2., 3.], visibility)
        _, gradient, _, _ = model.evaluate(residual)
        direction = rng.normal(size=residual.shape)
        step = .001
        measured = (model.evaluate(residual - step * direction)[0] -
                    model.evaluate(residual + step * direction)[0]) / (2 * step)
        assert_allclose(measured, np.sum(gradient * direction), atol=2e-8, rtol=2e-6)

    def test_complete_fit_is_held_cfo_invariant_and_respects_fixed_c(self):
        obs = observations(np.arange(10.), 100 + 15 * np.arange(10.))
        mask = np.array([True, True, True, True, True, False, False, False, False, False])
        basis = np.array([[1.], [-1.]]) / np.sqrt(2.)
        full_design = np.column_stack((np.ones(10), obs.times_s, np.zeros((10, 2)),
                                       (obs.rf_hz - 11.15e9) / 1e9))
        derivative = np.tile([50., -80.], (mask.sum(), 1))
        model = SimpleNamespace(mask=mask, basis=basis,
            original=SimpleNamespace(design=full_design),
            score=SimpleNamespace(common_sigma_s=2., relative_sigma_s=.5))
        context = SimpleNamespace(observations=obs, train_mask=mask, model=model,
            bank=SimpleNamespace(numbers=np.array([101, 202])), prior=None,
            vector=np.zeros(9), nuisance=np.zeros(0), fixed_c=False)
        model.scored_observations = training_observations(context)

        def evaluate(vector, nuisance):
            tau = vector[7] + basis @ vector[8:]
            prediction = (np.array([0., 900.])[None, :] + derivative * tau[None, :] +
                          (full_design[mask] @ vector[2:7])[:, None])
            residual = circular(obs.measured_hz[mask, None] - prediction)
            value = float(np.min(residual ** 2, axis=1).sum())
            return (value, None, None, SimpleNamespace(residual_hz=residual)), dict(
                sigma_hz=np.full(mask.sum(), 125.), detection_probability=np.ones(2),
                visibility_weight=np.ones((mask.sum(), 2)))

        model.evaluate_details = evaluate

        def fake_refit(ctx, vector, nuisance, **options):
            return dict(vector=vector, nuisance=nuisance, diagnostics=dict(evaluations=1,
                objective=evaluate(vector, nuisance)[0][0]))

        fake_modules = {
            "common": SimpleNamespace(refit=fake_refit),
            "leo.analysis.hard60_score": SimpleNamespace(predict_orbits=
                lambda *a, **kw: (None, None, None, derivative)),
            "leo.analysis.hard60_bounded_fit": SimpleNamespace(_Problem=
                lambda model, vector, **kw: SimpleNamespace(start=vector)),
        }
        with patch.dict("sys.modules", fake_modules):
            for fixed_c in (False, True):
                with self.subTest(fixed_c=fixed_c):
                    context.fixed_c = fixed_c
                    obs.measured_hz[~mask] = np.arange((~mask).sum())
                    first = fit(context, max_evaluations=24, max_seconds=20)
                    obs.measured_hz[~mask] = [np.nan, np.inf, -np.inf, 1e99, -1e99]
                    second = fit(context, max_evaluations=24, max_seconds=20)
                    assert_array_equal(first["vector"], second["vector"])
                    assert_array_equal(first["nuisance"], second["nuisance"])
                    self.assertEqual(first["diagnostics"]["proposal_surrogate_with_priors"],
                                     second["diagnostics"]["proposal_surrogate_with_priors"])
                    self.assertLessEqual(first["diagnostics"]["evaluations"], 24)
                    if fixed_c:
                        self.assertEqual(first["vector"][6], 0.)

    def test_alias_period_uses_the_scientific_cfo_contract(self):
        self.assertEqual(ALIAS_HZ, 1 / 4.4e-6)
        assert_allclose(circular(np.array([0., 100.]) + ALIAS_HZ), [0., 100.], atol=1e-9)


if __name__ == "__main__":
    unittest.main()
