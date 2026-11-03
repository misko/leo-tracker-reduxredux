import copy
import itertools
from pathlib import Path
import sys
import unittest
import numpy as np
from scipy.special import logsumexp
PARENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(PARENT / 'temporal_whole'))
from ratio_model import GeometryRatioPosition
from whole_source_fast import WholeSourcePosition
from temporal_receiver import sequence_score
from test_whole_source_position import fixture as base_fixture
from doppler_pilot import fast


def fixture(ownership=False):
    doc, config, bound, calibration = base_fixture()
    calibration['arms']['receiver'] = dict(selected=dict(parameters=[-.2, .4]))
    extra = copy.deepcopy(doc['tracks'][0])
    extra['track_id'] = '2'
    doc['tracks'].append(extra)
    meta = copy.deepcopy(bound['tracks'][0])
    meta.update(track_id='2', candidate_ids=['20', '01' if ownership else '21', '22'])
    bound['tracks'].append(meta)
    bound['lanes'][0]['left'].append('2')
    if ownership:
        bound['lanes'][0]['ownership_alternatives'] = [dict(assignment={'01': t}, log_prior=-np.log(2.)) for t in ('0', '2')]
    return doc, config, bound, calibration


class GeometryRatioTests(unittest.TestCase):
    def test_equal_emissions_cancel_including_ownership_and_held(self):
        args = fixture(True)
        control = WholeSourcePosition(*args, 'doppler')
        for tau in (0., .1, 8.):
            model = GeometryRatioPosition(*args, 'receiver', tau)
            for held in (False, True):
                a = model.evaluate([.1, -.2, .05], gradient=not held, held=held)
                b = control.evaluate([.1, -.2, .05], gradient=not held, held=held)
                self.assertAlmostEqual(a['score'], b['score'], places=9)
                self.assertAlmostEqual(a['expected_sources'], b['expected_sources'], places=9)
                np.testing.assert_allclose(a['gradient'], b['gradient'], atol=1e-8)

    def test_sequence_ratio_assignments_match_enumeration_and_derivatives(self):
        args = fixture()
        model = GeometryRatioPosition(*args, 'signed', 3.)
        null = GeometryRatioPosition(*args, 'receiver', 3.)
        x = np.array([.1, -.2, .05])
        tables, rx, nrx = {}, {}, {}
        for tid, track in model.tracks.items():
            pred, _ = model.geometry.prediction(track, x)
            tables[tid] = fast.profile(track['y'][None] - pred, track['mask'])[0] - np.log(track['catalogue_size'])
            rx[tid] = model.receiver_probabilities(track, tid, x)
            nrx[tid] = null.receiver_probabilities(track, tid, x)
        scores = []
        for assignment in itertools.product(range(2), repeat=3):
            value = sum(tables[str(i)][c] for i, c in enumerate(assignment))
            for c in set(assignment):
                members = [str(i) for i, a in enumerate(assignment) if a == c]
                tid = members[0]
                state = sum(1 << r for r in {model.meta[t]['receiver'] for t in members})
                times = [model.window_times[w] for w in model.meta[tid]['window_ids']]
                for sign, probabilities in ((1., rx), (-1., nrx)):
                    value += sign * sequence_score(times, probabilities[tid][c][None], np.full(len(times), state), model.tracks[tid]['mask'], 3.)[0][0]
            scores.append(value)
        actual = model.evaluate(x)
        self.assertAlmostEqual(actual['score'], logsumexp(scores), places=9)
        for axis in range(3):
            d = np.eye(3)[axis] * 1e-4
            numerical = (model.evaluate(x + d, gradient=False)['score'] - model.evaluate(x - d, gradient=False)['score']) / 2e-4
            self.assertAlmostEqual(actual['gradient'][axis], numerical, places=5)

    def test_held_frequency_does_not_change_training_objective(self):
        args = fixture()
        before = GeometryRatioPosition(*args, 'signed', 3.).evaluate([.1, -.2, .05])
        for track in args[0]['tracks']:
            track['y'][1] += 10000.
        after = GeometryRatioPosition(*args, 'signed', 3.).evaluate([.1, -.2, .05])
        self.assertAlmostEqual(before['score'], after['score'], places=10)
        np.testing.assert_allclose(before['gradient'], after['gradient'], atol=1e-10)
