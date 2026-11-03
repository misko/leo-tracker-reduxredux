"""Component tests for automatic timing rescue; no storage or hardware access."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from scipy.special import expit

from leo.contracts.regional_position import PositionObservations
from leo.analysis.regional_position_score import ALIAS_HZ, circular
import model_a


def observations(times, measured):
    n = len(times)
    return PositionObservations(tuple(f"window-{i}" for i in range(n)), np.asarray(times),
        np.asarray(measured), np.full(n, 11e9), np.zeros(n, int),
        np.ones(n, int), np.ones(n))


def prediction(bank, obs, prior, point, shifts, derivatives=False):
    slopes = np.asarray(bank.slopes)
    predicted = obs.times_s[:, None] * slopes + 1000 * np.asarray(shifts)[None, :]
    return predicted, np.ones_like(predicted, bool), None, None


def context(obs, mask=None, slopes=(80.,)):
    n, k = len(obs.times_s), len(slopes)
    mask = np.ones(n, bool) if mask is None else np.asarray(mask)
    base = SimpleNamespace(design=np.zeros((n, 5)), baseline=np.zeros(n),
        group_design=np.zeros((n, 0)), clock_design=np.zeros((n, 0)),
        group_count=0, split=lambda unused: (np.empty(0), np.empty(0)))
    bank = SimpleNamespace(numbers=np.arange(10, 10+k), slopes=slopes,
        nodes_s=np.array([-30., 100.]))
    model = SimpleNamespace(original=base, base_nuisance_count=0,
        basis=np.empty((1, 0)) if k == 1 else np.array([[1.], [-1.]]) / np.sqrt(2),
        group_limits=np.array([2.]))
    v = np.zeros(7 + k)

    def evaluate(vv, nn):
        tau = vv[7] + model.basis @ vv[8:]
        predicted = prediction(bank, obs, None, vv[:2], tau)[0][:, 0]
        residual = circular(obs.measured_hz[mask] - predicted[mask])
        gaussian = np.exp(-.5 * (residual / 125.)**2)
        q = expit(nn[0])
        density = .01 + q * gaussian
        value = float(-np.log(density).sum() + .5 * nn[0]**2 + .05 * np.sum(tau**2))
        gradient = np.zeros_like(vv)
        q_gradient = float(np.sum(-gaussian / density) * q * (1-q) + nn[0])
        return value, gradient, np.array([q_gradient]), None

    model.evaluate_joint = evaluate
    return SimpleNamespace(model=model, bank=bank, observations=obs, prior=None,
        vector=v, nuisance=np.array([-2.]), train_mask=mask, fixed_c=False)


class TimingRescueTests(unittest.TestCase):
    @patch.object(model_a, 'predict_orbits', side_effect=prediction)
    def test_timing_trap_rescued_and_shared_q_recovers(self, unused):
        t = np.arange(25.)
        ctx = context(observations(t, 80*t + 2000))
        initial = ctx.model.evaluate_joint(ctx.vector, ctx.nuisance)[0]
        fake_common = SimpleNamespace(refit=lambda ctx, v, n, **kw:
            dict(vector=v, nuisance=n, diagnostics=dict(evaluations=0)))
        with patch.dict('sys.modules', common=fake_common):
            fitted = model_a.fit(ctx, max_evaluations=80, max_seconds=10)
        self.assertAlmostEqual(fitted['vector'][7], 2., places=6)
        self.assertGreater(fitted['nuisance'][0], 0.)
        self.assertLess(fitted['diagnostics']['final_objective'], initial - 30)
        self.assertTrue(any(r['accepted'] for r in fitted['diagnostics']['rescue_trials']))

    def test_crossing_tracks_outliers_and_alias_boundary(self):
        t = np.repeat(np.arange(25.), 2)
        y = np.empty(50)
        y[::2] = ALIAS_HZ/2 - 600 + 80*t[::2]
        y[1::2] = ALIAS_HZ/2 + 1400 - 80*t[1::2]
        # Outliers remain observations, but cannot define the coherent arcs.
        t = np.r_[t, [.2, 4.2, 8.2, 12.2, 16.2, 20.2]]
        y = np.r_[circular(y), [30000., -70000., 41000., 0., -50000., 60000.]]
        obs = observations(t, y)
        tracks = model_a.extract_tracks(obs, np.ones(len(t), bool), np.zeros(len(t)))
        self.assertTrue(tracks)
        support_a = max(len(set(track) & set(range(0, 50, 2))) for track in tracks)
        support_b = max(len(set(track) & set(range(1, 50, 2))) for track in tracks)
        self.assertGreaterEqual(support_a, 15)
        self.assertGreaterEqual(support_b, 15)
        self.assertFalse(any(np.any(track >= 50) for track in tracks))

    @patch.object(model_a, 'predict_orbits', side_effect=prediction)
    def test_held_cfo_values_do_not_change_tracks_proposals_or_fit(self, unused):
        t = np.arange(36.)
        mask = np.arange(36) % 4 != 0
        obs = observations(t, 80*t + 2000)
        changed = replace(obs, measured_hz=obs.measured_hz + np.where(mask, 0., 9876543.))
        a, b = context(obs, mask), context(changed, mask)
        pa, da = model_a.propose_timings(a, a.vector, a.nuisance)
        pb, db = model_a.propose_timings(b, b.vector, b.nuisance)
        self.assertEqual(pa, pb)
        self.assertEqual(da, db)
        tracks = model_a.extract_tracks(changed, mask, np.zeros(len(t)))
        self.assertTrue(all(np.all(mask[track]) for track in tracks))
        fake_common = SimpleNamespace(refit=lambda ctx, v, n, **kw:
            dict(vector=v, nuisance=n, diagnostics=dict(evaluations=0)))
        with patch.dict('sys.modules', common=fake_common):
            fa = model_a.fit(a, max_evaluations=80, max_seconds=10)
            fb = model_a.fit(b, max_evaluations=80, max_seconds=10)
        np.testing.assert_array_equal(fa['vector'], fb['vector'])
        np.testing.assert_array_equal(fa['nuisance'], fb['nuisance'])

    @patch.object(model_a, 'predict_orbits', side_effect=prediction)
    def test_objective_allowance_is_shared_with_final_refit(self, unused):
        t = np.arange(25.)
        ctx = context(observations(t, 80*t + 2000))
        calls = []
        original = ctx.model.evaluate_joint

        def counted(v, n):
            calls.append(1)
            return original(v, n)

        def refit(ctx, v, n, *, max_evaluations, **kw):
            for _ in range(max_evaluations):
                e = ctx.model.evaluate_joint(v, n)
            return dict(vector=v, nuisance=n,
                diagnostics=dict(evaluations=max_evaluations, objective=e[0]))

        ctx.model.evaluate_joint = counted
        with patch.dict('sys.modules', common=SimpleNamespace(refit=refit)):
            fit = model_a.fit(ctx, max_evaluations=3, max_seconds=10)
        self.assertEqual(len(calls), 3)
        self.assertEqual(fit['diagnostics']['evaluations'], 3)
        np.testing.assert_array_equal(ctx.vector, np.zeros(8))
        np.testing.assert_array_equal(ctx.nuisance, [-2.])


if __name__ == '__main__':
    unittest.main()
