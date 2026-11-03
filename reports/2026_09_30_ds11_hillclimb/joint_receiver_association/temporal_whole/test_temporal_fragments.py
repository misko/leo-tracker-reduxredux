import copy
import itertools
from pathlib import Path
import sys
import unittest
import numpy as np
from scipy.special import logsumexp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from time_model import TemporalWholeSourcePosition
from temporal_receiver import sequence_score
from test_whole_source_position import fixture
from doppler_pilot import fast


class MultiFragmentTemporalTests(unittest.TestCase):
    def test_same_receiver_fragments_share_one_source_state(self):
        doc, config, bound, calibration = fixture()
        extra = copy.deepcopy(doc['tracks'][0])
        extra['track_id'] = '2'
        extra['y'] += 1.
        doc['tracks'].append(extra)
        meta = copy.deepcopy(bound['tracks'][0])
        meta.update(track_id='2', candidate_ids=['20', '21', '22'])
        bound['tracks'].append(meta)
        bound['lanes'][0]['left'].append('2')
        model = TemporalWholeSourcePosition(doc, config, bound, calibration, 'signed', 3.)
        x = [.1, -.2, .05]
        tables, rx = {}, {}
        for tid, track in model.tracks.items():
            pred, _ = model.geometry.prediction(track, x)
            tables[tid] = fast.profile(track['y'][None] - pred, track['mask'])[0] - np.log(track['catalogue_size'])
            rx[tid] = model.receiver_probabilities(track, tid, x)
        scores, counts = [], []
        for assignment in itertools.product(range(2), repeat=3):
            value = sum(tables[str(i)][c] for i, c in enumerate(assignment))
            for c in set(assignment):
                members = [str(i) for i, a in enumerate(assignment) if a == c]
                tid = members[0]
                state = sum(1 << r for r in {model.meta[t]['receiver'] for t in members})
                times = [model.window_times[w] for w in model.meta[tid]['window_ids']]
                value += sequence_score(times, rx[tid][c][None], np.full(len(times), state), model.tracks[tid]['mask'], 3.)[0][0]
            scores.append(value)
            counts.append(len(set(assignment)))
        result = model.evaluate(x)
        normal = logsumexp(scores)
        self.assertAlmostEqual(result['score'], normal, places=9)
        self.assertAlmostEqual(result['expected_sources'], np.exp(np.array(scores) - normal) @ counts, places=9)
