"""Pure synthetic public-contract tests; no archive, hardware or database access."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '2026_10_16_dsx01_models'))
import common
import donors
import causal_calibration as calibration
from leo.application.channel_group_refinement import objective
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import observer, circular
from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior


def toy_context(fixed_c=False):
    prior = RegionalPrior()
    site, up = observer(prior, np.zeros(2))
    east = np.cross([0., 0., 1.], up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    orbit_nodes = np.linspace(-100., 200., 31)
    positions, velocities = [], []
    for k in range(3):
        velocity = east*(6.5+.4*k)+north*(.4*k)
        origin = site+up*(1100+150*k)+north*(100*k)
        positions.append(origin+orbit_nodes[:, None]*velocity)
        velocities.append(np.broadcast_to(velocity, (len(orbit_nodes), 3)))
    bank = PositionOrbitBank([101, 102, 103], orbit_nodes, positions, velocities)
    times = np.repeat(np.linspace(0., 100., 17), 16)
    rx, ch = np.tile(np.repeat([0, 1], 8), 17), np.tile(np.arange(1, 9), 34)
    rf = np.where(ch < 5, 10.7e9+ch*1e7, 11.8e9+ch*1e7)
    obs = PositionObservations(tuple(f'point-{i}' for i in range(len(times))), times,
        np.zeros(len(times)), rf, rx, ch, np.ones(len(times)))
    orbit = predict_orbits(bank, obs, prior, np.zeros(2), np.zeros(3), derivatives=False)[0]
    low, delta = np.where(rx == 0, -25000., 12000.), np.where(rx == 0, -15000., 40000.)
    obs = replace(obs, measured_hz=circular(orbit[:, 0]+low+(ch >= 5)*delta))
    nodes = np.linspace(0., 100., 7)
    joint = objective(SimpleNamespace(observations=obs), bank, prior, nodes)
    shift = SequentialShift(joint.frame.receivers, np.zeros(2))
    raw = fixed_shift_objective(joint.base, shift)
    mask = (times <= 50.) & ~((rx == 0) & (ch >= 7)) & ~((rx == 1) & (ch < 3))
    model = SharedScanObjective(raw, shift, mask=mask)
    return common.Context('toy', model, SharedScanObjective(raw, shift), np.zeros(model.size),
        model.initial_nuisance.copy(), obs, bank, prior, mask, nodes, {}, fixed_c=fixed_c)


def donor():
    return dict(available=True, donor=dict(band=dict(receivers=[0, 1], offsets_hz=[-15000., 40000.])))


class CalibrationTests(unittest.TestCase):
    def test_held_values_and_unused_donor_position_cannot_change_fit(self):
        ctx = toy_context()
        changed = replace(ctx, observations=replace(ctx.observations,
            measured_hz=ctx.observations.measured_hz+np.where(ctx.train_mask, 0., 1234567.)))
        prior = donor()
        altered = deepcopy(prior)
        altered['donor']['position'] = [999999., -999999.]
        a, da = calibration.bootstrap(ctx, prior, max_evaluations=20, max_seconds=10)
        b, db = calibration.bootstrap(changed, altered, max_evaluations=20, max_seconds=10)
        np.testing.assert_array_equal(a.vector, b.vector)
        np.testing.assert_array_equal(a.nuisance, b.nuisance)
        self.assertEqual(da['seed'], db['seed'])
        self.assertLess(da['correction_transport_max_hz'], 1e-7)
        self.assertLess(da['masked_objective_closure_error'], 1e-7)
        self.assertEqual(da['physical_band_columns'], 2)
        self.assertTrue(da['seed']['donor_used'])

    def test_shared_delta_no_donor_fallback_is_training_derived(self):
        ctx = toy_context()
        trained, diag = calibration.bootstrap(ctx, None, max_evaluations=20, max_seconds=10)
        self.assertFalse(diag['seed']['donor_used'])
        values = [row['inferred_delta_hz'] for row in diag['seed']['fallback_paired_delta']]
        np.testing.assert_allclose(values, [-15000., 40000.], atol=150.)
        self.assertTrue(all(row['pairs'] > 0 for row in diag['seed']['fallback_paired_delta']))

    def test_c_zero_and_budget_accounting_includes_partial_seed_scores(self):
        trained, diag = calibration.bootstrap(toy_context(True), donor(),
            max_evaluations=16, max_seconds=10)
        self.assertEqual(trained.vector[6], 0.)
        self.assertLessEqual(diag['evaluations'], 16)
        self.assertEqual(diag['evaluations'], diag['partial_density_evaluations']
            + diag['full_objective_evaluations'])
        self.assertGreater(diag['partial_density_evaluations'], 0)
        self.assertEqual(diag['accepted'], diag['fit']['accepted'])

    def test_causal_selection_checks_end_completion_hardware_and_rf(self):
        meta = dict(first_sample_utc_ns=1000, capture_end_utc_ns=1200,
            radio_id='radioA', stream_generation='continuous-iio-aaa', sample_rate_hz=2500000,
            capture_mode='adaptive', rf_mapping=[[0, 1, 'lower', 11e9]])
        target = dict(job_id='target', metadata=meta)
        good = dict(job_id='good', metadata=dict(meta, first_sample_utc_ns=700,
            capture_end_utc_ns=800, stream_generation='continuous-iio-bbb'),
            completion_upper_bound_utc_ns=900)
        overlap = deepcopy(good)
        overlap.update(job_id='overlap')
        overlap['metadata']['capture_end_utc_ns'] = 1001
        late = dict(good, job_id='late', completion_upper_bound_utc_ns=1001)
        wrong_rf = deepcopy(good)
        wrong_rf.update(job_id='rf')
        wrong_rf['metadata']['rf_mapping'] = [[0, 1, 'lower', 12e9]]
        wrong_radio = deepcopy(good)
        wrong_radio.update(job_id='radio')
        wrong_radio['metadata']['radio_id'] = 'radioB'
        result = donors.select_donor(target, [overlap, late, wrong_rf, wrong_radio, good])
        self.assertEqual(result['donor']['job_id'], 'good')
        self.assertFalse(result['selected_generation_equal'])
        missing = donors.select_donor(target, [overlap, late, wrong_rf, wrong_radio])
        self.assertFalse(missing['available'])


if __name__ == '__main__':
    unittest.main()
