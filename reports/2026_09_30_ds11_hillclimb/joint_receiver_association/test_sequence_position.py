import copy
import unittest
import numpy as np
from joint_position import JointPosition
from sequence_position import SequencePosition


def fixture():
    times = np.array([0., 1., 2.])
    taus = np.array([-1., 0., 1.])
    positions = np.zeros((2, 3, 3, 3))
    velocities = np.broadcast_to(np.array([[0., 7., 1.], [0., -6., 2.]])[:, None, None, :], positions.shape).copy()
    for c in range(2):
        positions[c] = np.array([6900., 200. + c * 100., 300.]) + velocities[c] * (taus[:, None, None] + times[None, :, None])
    tracks, meta = [], []
    for receiver in (0, 1):
        tid = str(receiver)
        tracks.append(dict(track_id=tid, y=np.array([300., 298., 296.]) + receiver * 2., mask=np.array([1, 0, 1], bool), candidate_position_km=positions.copy(), candidate_velocity_km_s=velocities.copy(), catalogue_size=100))
        meta.append(dict(track_id=tid, receiver=receiver, rf_hz=1, candidate_ids=[tid + str(i) for i in range(3)], window_ids=['0', '1', '2'], candidate_norad=[10, 20]))
    opportunities = [dict(source_window_id=str(i), window_start_utc_ns=i * 10**9, window_end_utc_ns=i * 10**9 + 20000000, receivers={r: dict(receiver_status='observed_candidate_present') for r in ('rx0', 'rx1')}) for i in range(3)]
    bound = dict(tracks=meta, opportunities=opportunities, lanes=[dict(left=['0'], right=['1'], edges=[dict(left='0', right='1')], ownership_alternatives=[dict(assignment={}, log_prior=0.)])])
    config = dict(geographic_prior_center_deg=[0., 0.], timing_grid_s=taus)
    calibration = dict(frequencies=[1], arms=dict(signed=dict(selected=dict(parameters=[-.5, .2, 2.]))))
    return dict(tracks=tracks), config, bound, calibration


class SequencePositionTests(unittest.TestCase):
    def test_independent_parity(self):
        args = fixture()
        old = JointPosition(*args, 'signed')
        new = SequencePosition(*args, 'signed', 0.)
        x = np.array([.1, -.2, .05])
        for held in (False, True):
            a = old.evaluate(x, gradient=not held, held=held)
            b = new.evaluate(x, gradient=not held, held=held)
            self.assertAlmostEqual(a['score'], b['score'], places=9)
            np.testing.assert_allclose(a['gradient'], b['gradient'], atol=1e-9)

    def test_training_isolation_and_full_derivative(self):
        args = fixture()
        model = SequencePosition(*args, 'signed', 3.)
        x = np.array([.1, -.2, .05])
        out = model.evaluate(x)
        changed = copy.deepcopy(args)
        for track in changed[0]['tracks']:
            track['y'][1] += 10000.
        other = SequencePosition(*changed, 'signed', 3.).evaluate(x)
        self.assertAlmostEqual(out['score'], other['score'], places=10)
        for axis in range(3):
            d = np.eye(3)[axis] * 1e-4
            numerical = (model.evaluate(x + d, gradient=False)['score'] - model.evaluate(x - d, gradient=False)['score']) / 2e-4
            self.assertAlmostEqual(out['gradient'][axis], numerical, places=5)

    def test_held_gradient_is_explicitly_unsupported(self):
        model = SequencePosition(*fixture(), 'signed', 3.)
        with self.assertRaises(ValueError):
            model.evaluate([0., 0., 0.], held=True)
