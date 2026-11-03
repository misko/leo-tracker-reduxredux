"""Synthetic component tests, with real objective math and no data store access."""
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '2026_10_16_dsx01_models'))
import common
import cold_band_calibration as calibration
from leo.application.channel_group_refinement import objective
from leo.analysis.regional_position_score import observer, circular, ALIAS_HZ
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior


def toy_context(*, fixed_c=False):
    prior = RegionalPrior()
    site, up = observer(prior, np.zeros(2))
    east = np.cross(np.array([0., 0., 1.]), up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    orbit_nodes = np.linspace(-100., 200., 31)
    positions, velocities = [], []
    for k in range(3):
        velocity = east * (6.5 + .4*k) + north * (.4*k)
        origin = site + up*(1100 + 150*k) + north*(100*k)
        positions.append(origin + orbit_nodes[:, None]*velocity)
        velocities.append(np.broadcast_to(velocity, (len(orbit_nodes), 3)))
    bank = PositionOrbitBank(np.array([101, 102, 103]), orbit_nodes,
        np.asarray(positions), np.asarray(velocities))
    times = np.repeat(np.linspace(0., 100., 17), 16)
    rx = np.tile(np.repeat([0, 1], 8), 17)
    ch = np.tile(np.arange(1, 9), 34)
    rf = np.where(ch < 5, 10.7e9 + ch*1e7, 11.8e9 + ch*1e7)
    obs = PositionObservations(tuple(f'point-{i}' for i in range(len(times))), times,
        np.zeros(len(times)), rf, rx, ch, np.ones(len(times)))
    orbit = predict_orbits(bank, obs, prior, np.zeros(2), np.zeros(3), derivatives=False)[0]
    low = np.where(rx == 0, -25000., 12000.)
    delta = np.where(rx == 0, -15000., 40000.)
    obs = replace(obs, measured_hz=circular(orbit[:, 0] + low + (ch >= 5)*delta))
    nodes = np.linspace(0., 100., 7)
    joint = objective(SimpleNamespace(observations=obs), bank, prior, nodes)
    shift = SequentialShift(joint.frame.receivers, np.zeros(2))
    raw = fixed_shift_objective(joint.base, shift)
    mask = (times <= 50.) & ~((rx == 0) & (ch >= 7)) & ~((rx == 1) & (ch < 3))
    model = SharedScanObjective(raw, shift, mask=mask)
    return common.Context('toy', model, SharedScanObjective(raw, shift),
        np.zeros(model.size), model.initial_nuisance.copy(), obs, bank, prior, mask,
        nodes, {}, fixed_c=fixed_c)


class ColdBandCalibrationTests(unittest.TestCase):
    def test_centered_seed_and_raw_freeze_are_exact(self):
        ctx = toy_context()
        trained, diagnostics = calibration.bootstrap(ctx, max_evaluations=8, max_seconds=15)
        self.assertEqual(diagnostics['physical_band_column_count'], 2)
        self.assertEqual(diagnostics['training_group_design_rank'], 2)
        self.assertEqual(diagnostics['training_augmented_design_rank']
            - diagnostics['training_common_design_rank'], 2)
        self.assertEqual(trained.model.original.group_count, 0)
        self.assertGreater(abs(diagnostics['learned_offsets_hz'][0]), 10000.)
        self.assertGreater(abs(diagnostics['learned_offsets_hz'][1]), 30000.)
        self.assertLess(diagnostics['correction_transport_max_hz'], 1e-7)
        self.assertLess(diagnostics['masked_objective_likelihood_residual_max_error'], 1e-7)
        self.assertAlmostEqual(diagnostics['fixed_contrast_prior_penalty'],
            .5*np.sum(np.square(diagnostics['learned_offsets_hz']))/50000.**2)
        # Raw low offsets differ from centered intercepts by fraction*contrast.
        seed = diagnostics['seed']['receivers']
        self.assertAlmostEqual(seed[0]['high_minus_low_hz'], -15000., delta=100.)
        self.assertAlmostEqual(seed[1]['high_minus_low_hz'], 40000., delta=100.)

    def test_held_cfo_invariance_including_optimizer_and_seed(self):
        ctx = toy_context()
        changed_obs = replace(ctx.observations, measured_hz=ctx.observations.measured_hz
            + np.where(ctx.train_mask, 0., 1234567.))
        changed = replace(ctx, observations=changed_obs)
        a, da = calibration.bootstrap(ctx, max_evaluations=12, max_seconds=15)
        b, db = calibration.bootstrap(changed, max_evaluations=12, max_seconds=15)
        self.assertEqual(da['seed'], db['seed'])
        np.testing.assert_array_equal(a.vector, b.vector)
        np.testing.assert_array_equal(a.nuisance, b.nuisance)
        np.testing.assert_array_equal(da['learned_offsets_hz'], db['learned_offsets_hz'])

    def test_c_zero_and_shared_exact_evaluation_budget(self):
        ctx = toy_context(fixed_c=True)
        observed = []
        original_refit = common.refit

        def counted(ctx, v, n, **options):
            observed.append(options['max_evaluations'])
            return original_refit(ctx, v, n, **options)

        with patch.object(common, 'refit', side_effect=counted):
            trained, diagnostics = calibration.bootstrap(ctx, max_evaluations=9, max_seconds=15)
        self.assertEqual(observed, [6])
        self.assertLessEqual(diagnostics['evaluations'], 9)
        self.assertEqual(diagnostics['evaluations'], 3 + diagnostics['fit']['evaluations'])
        self.assertEqual(trained.vector[6], 0.)
        self.assertTrue(diagnostics['fixed_c'])
        self.assertEqual(diagnostics['accepted'], diagnostics['fit']['accepted'])
        self.assertLessEqual(diagnostics['elapsed_seconds'], 15.)

    def test_histogram_wraps_alias_boundary(self):
        values = np.array([ALIAS_HZ/2 - 30., -ALIAS_HZ/2 + 30., ALIAS_HZ/2 - 10.])
        peak, _, _ = calibration._histogram_peak(values, np.ones(3))
        self.assertLess(abs(circular(peak - ALIAS_HZ/2)), 20.)


if __name__ == '__main__':
    unittest.main()
