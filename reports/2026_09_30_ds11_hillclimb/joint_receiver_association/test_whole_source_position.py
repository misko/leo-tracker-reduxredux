import copy
import itertools
import unittest
import numpy as np
from scipy.special import logsumexp
from test_sequence_position import fixture as base_fixture
from whole_source_position import WholeSourcePosition
from doppler_pilot import fast


def fixture():
    data = base_fixture()
    data[2]['lanes'][0]['rf_hz'] = 1
    return data


class WholeSourceTests(unittest.TestCase):
    def test_zero_receiver_partition_parity(self):
        model = WholeSourcePosition(*fixture(), 'doppler')
        x = np.array([.1, -.2, .05])
        for held in (False, True):
            a = model.evaluate(x, gradient=not held, held=held)
            b = model.evaluate(x, gradient=not held, held=held, force_partition=True)
            self.assertAlmostEqual(a['score'], b['score'], places=9)
            self.assertAlmostEqual(a['expected_sources'], b['expected_sources'], places=9)
            np.testing.assert_allclose(a['gradient'], b['gradient'], atol=1e-9)

    def test_three_fragments_full_enumeration(self):
        doc, config, bound, calibration = fixture()
        extra = copy.deepcopy(doc['tracks'][0])
        extra['track_id'] = '2'
        extra['y'] += 1.
        doc['tracks'].append(extra)
        meta = copy.deepcopy(bound['tracks'][0])
        meta.update(track_id='2', candidate_ids=['20', '21', '22'])
        bound['tracks'].append(meta)
        bound['lanes'][0]['left'].append('2')
        model = WholeSourcePosition(doc, config, bound, calibration, 'signed')
        x = np.array([.1, -.2, .05])
        actual = model.evaluate(x)
        tables, rx = {}, {}
        for tid, track in model.tracks.items():
            pred, _ = model.geometry.prediction(track, x)
            tables[tid] = fast.profile(track['y'][None] - pred, track['mask'])[0] - np.log(track['catalogue_size'])
            rx[tid] = model.receiver_probabilities(track, tid, x)
        weights, counts = [], []
        for assignment in itertools.product(range(2), repeat=3):
            score = sum(tables[str(i)][c] for i, c in enumerate(assignment))
            for candidate in set(assignment):
                tids = [str(i) for i, c in enumerate(assignment) if c == candidate]
                state = sum(1 << r for r in {model.meta[t]['receiver'] for t in tids})
                score += rx[tids[0]][candidate, [0, 2], state - 1].sum()
            weights.append(score)
            counts.append(len(set(assignment)))
        normal = logsumexp(weights)
        self.assertAlmostEqual(actual['score'], normal, places=9)
        self.assertAlmostEqual(actual['expected_sources'], np.exp(np.array(weights) - normal) @ counts, places=9)
        for axis in range(3):
            d = np.eye(3)[axis] * 1e-4
            numerical = (model.evaluate(x + d, gradient=False)['score'] - model.evaluate(x - d, gradient=False)['score']) / 2e-4
            self.assertAlmostEqual(actual['gradient'][axis], numerical, places=5)
