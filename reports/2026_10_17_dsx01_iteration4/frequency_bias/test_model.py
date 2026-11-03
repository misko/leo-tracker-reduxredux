"""Synthetic component tests for the empirical satellite-bias objective."""
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'2026_10_16_dsx01_models'))
import common
from model import ConstantBiasObjective
from profiles import BiasProfiles, fit
from leo.application.channel_group_refinement import objective
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import observer, circular
from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior


def toy(masked=False, horizon=False):
    prior = RegionalPrior()
    site, up = observer(prior, np.zeros(2))
    east = np.cross([0., 0., 1.], up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    nodes = np.linspace(-100., 200., 31)
    position, velocity = [], []
    for k in range(3):
        vel = east*(6.5+.4*k)+north*(.5*k)
        origin = site+up*(1100+150*k)+north*(100*k)
        position.append(origin+nodes[:, None]*vel)
        velocity.append(np.broadcast_to(vel, (len(nodes), 3)))
    if horizon:
        position[-1] = np.broadcast_to(site+east*1000., (len(nodes), 3))
        velocity[-1] = np.zeros((len(nodes), 3))
    bank = PositionOrbitBank([101, 102, 103], nodes, position, velocity)
    times = np.repeat(np.linspace(0., 80., 12), 16)
    rx, channel = np.tile(np.repeat([0, 1], 8), 12), np.tile(np.arange(1, 9), 24)
    rf = 10.7e9+channel*1e8
    obs = PositionObservations(tuple(f'row-{i}' for i in range(len(times))), times,
        np.zeros(len(times)), rf, rx, channel, np.ones(len(times)))
    pred = predict_orbits(bank, obs, prior, np.zeros(2), np.zeros(3), derivatives=False)[0]
    identity = np.arange(len(times)) % 3
    low = np.where(rx == 0, -25000., 12000.)
    delta = np.where(rx == 0, -15000., 40000.)
    bias = np.array([180., -140., 90.])
    obs = replace(obs, measured_hz=circular(pred[np.arange(len(times)), identity]
        +low+(channel >= 5)*delta+bias[identity]))
    clock_nodes = np.linspace(0., 80., 5)
    joint = objective(SimpleNamespace(observations=obs), bank, prior, clock_nodes)
    shift = SequentialShift((0, 1), np.array([-15000., 40000.]))
    raw = fixed_shift_objective(joint.base, shift)
    mask = times <= 40. if masked else np.ones(len(times), bool)
    base = SharedScanObjective(raw, shift, mask=mask)
    v = np.zeros(base.size)
    v[2], v[4] = -25000., 12000.
    n = base.initial_nuisance.copy()
    return common.Context('toy', base, SharedScanObjective(raw, shift), v, n,
        obs, bank, prior, mask, clock_nodes, {})


class ConstantBiasTests(unittest.TestCase):
    def test_zero_bias_exactly_nests_original_value_gradients_and_posteriors(self):
        context = toy()
        v, n = context.vector, context.nuisance
        e, d = context.model.evaluate_details(v, n)
        model = ConstantBiasObjective(context.model, 300.)
        actual, details = model.evaluate_details(v, np.r_[n, np.zeros(3)])
        self.assertEqual(actual[0], e[0])
        np.testing.assert_array_equal(actual[1], e[1])
        np.testing.assert_array_equal(actual[2][:len(n)], e[2])
        np.testing.assert_array_equal(actual[3].responsibilities, e[3].responsibilities)
        np.testing.assert_array_equal(details['detection_probability'], d['detection_probability'])

    def test_all_physical_clock_q_and_bias_gradients(self):
        context = toy(horizon=True)
        model = ConstantBiasObjective(context.model, 300.)
        v, n = context.vector.copy(), np.r_[context.nuisance, [120., -80., 50.]]
        v[:2] = [1e-5, -1e-5]
        v[3], v[5], v[6], v[7] = .01, -.02, 10., .01
        n[-5:-3] = [.1, -.2]  # nonuniform q: includes its exact normalizer derivative
        value, gradient, extra, _ = model.evaluate_joint(v, n)
        for offset in range(len(v)+len(n)):
            a, b = v.copy(), n.copy()
            step = 1e-4 if offset < len(v) else 1e-3
            if offset < len(v):
                a[offset] += step
                high = model.evaluate_joint(a, b)[0]
                a[offset] -= 2*step
                low = model.evaluate_joint(a, b)[0]
                expected = gradient[offset]
            else:
                index = offset-len(v)
                b[index] += step
                high = model.evaluate_joint(a, b)[0]
                b[index] -= 2*step
                low = model.evaluate_joint(a, b)[0]
                expected = extra[index]
            numerical = (high-low)/(2*step)
            self.assertAlmostEqual(numerical, expected,
                delta=3e-4*max(1., abs(numerical)), msg=f'coordinate {offset}')

    def test_prior_once_absolute_hz_physics_and_bounds(self):
        context = toy()
        a, b = ConstantBiasObjective(context.model, 300.), ConstantBiasObjective(context.model, 1000.)
        bias = np.array([200., -150., 100.])
        n = np.r_[context.nuisance, bias]
        ea = a.evaluate_joint(context.vector, n)
        eb = b.evaluate_joint(context.vector, n)
        self.assertAlmostEqual(ea[0]-eb[0], .5*np.sum(bias**2)*(1/300.**2-1/1000.**2))
        np.testing.assert_allclose(ea[2][-3:]-eb[2][-3:], bias*(1/300.**2-1/1000.**2))
        base = context.model.evaluate_joint(context.vector, context.nuisance)
        # One same-Hz shift per satellite at every actual RF, receiver and channel.
        np.testing.assert_allclose(circular(base[3].residual_hz-ea[3].residual_hz),
            np.broadcast_to(bias, ea[3].residual_hz.shape), atol=1e-9)
        bad = n.copy()
        bad[-1] = 4000.01
        with self.assertRaises(ValueError):
            a.evaluate_joint(context.vector, bad)

    def test_profiles_match_exact_candidate_substitution_on_all_rows(self):
        context = toy()
        model = ConstantBiasObjective(context.model, 1000.)
        n = np.r_[context.nuisance, [80., -50., 20.]]
        profiles = BiasProfiles(model, context.vector, n)
        trials = np.array([-3000., 250., 4000.])
        expected = profiles.score(trials)
        for k in range(3):
            nn = n.copy()
            nn[model.bias_start+k] = trials[k]
            self.assertAlmostEqual(expected[k], model.evaluate_joint(context.vector, nn)[0], places=8)

    def test_proper_bias_prior_regularizes_the_common_intercept_gauge(self):
        context = toy()
        model = ConstantBiasObjective(context.model, 300.)
        n = np.r_[context.nuisance, np.zeros(3)]
        original = model.evaluate_joint(context.vector, n)
        v, shifted = context.vector.copy(), n.copy()
        v[[2, 4]] -= 500.
        shifted[model.bias_start:] = 500.
        trial = model.evaluate_joint(v, shifted)
        np.testing.assert_allclose(original[3].residual_hz, trial[3].residual_hz, atol=2e-10, rtol=0)
        self.assertAlmostEqual(original[3].nll, trial[3].nll, places=9)
        self.assertAlmostEqual(trial[0]-original[0], .5*3*500.**2/300.**2)

    def test_held_cfo_invariance_through_profiles_and_final_fit_c_zero(self):
        context = toy(masked=True)
        changed_obs = replace(context.observations, measured_hz=context.observations.measured_hz
            +np.where(context.train_mask, 0., 1234567.))
        raw = context.model.original
        changed_raw = object.__new__(type(raw))
        changed_raw.__dict__.update(raw.__dict__)
        changed_raw.base = object.__new__(type(raw.base))
        changed_raw.base.__dict__.update(raw.base.__dict__)
        changed_raw.base.observations = changed_obs
        # Frozen shift is recoverable from this controlled synthetic baseline.
        shift = SequentialShift((0, 1), np.array([-15000., 40000.]))
        altered_base = SharedScanObjective(changed_raw, shift, mask=context.train_mask)
        a = ConstantBiasObjective(context.model, 300.)
        b = ConstantBiasObjective(altered_base, 300.)
        ca = replace(context, model=a, nuisance=np.r_[context.nuisance, np.zeros(3)], fixed_c=True)
        cb = replace(ca, model=b, observations=changed_obs)
        first = fit(ca, max_evaluations=30, max_seconds=15)
        second = fit(cb, max_evaluations=30, max_seconds=15)
        np.testing.assert_array_equal(first['vector'], second['vector'])
        np.testing.assert_array_equal(first['nuisance'], second['nuisance'])
        self.assertEqual(first['diagnostics']['rounds'], second['diagnostics']['rounds'])
        self.assertLessEqual(first['diagnostics']['evaluations'], 30)
        self.assertEqual(first['vector'][6], 0.)


if __name__ == '__main__':
    unittest.main()
