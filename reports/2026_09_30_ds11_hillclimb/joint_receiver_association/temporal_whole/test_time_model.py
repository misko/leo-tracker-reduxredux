import itertools
from pathlib import Path
import sys
import unittest
import numpy as np
from scipy.special import logsumexp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from time_model import TemporalWholeSourcePosition
from batched_filter import filter_subsets
from temporal_receiver import sequence_score
from whole_source_fast import WholeSourcePosition
from test_whole_source_position import fixture
from doppler_pilot import fast


class TemporalWholeTests(unittest.TestCase):
    def test_subset_filter_matches_individual_sequences_and_gradients(self):
        rng = np.random.default_rng(19)
        times = np.arange(6) * .7
        logits = rng.normal(size=(4, 6, 3))
        slopes = rng.normal(size=logits.shape)
        p = np.exp(logits - logsumexp(logits, axis=-1)[..., None])
        derivative = (slopes - (p * slopes).sum(axis=-1)[..., None])[..., None]
        states = np.array([[0, 0, 0, 0, 0, 0], [1, 0, 2, 3, 0, 1], [0, 2, 0, 2, 3, 0], [1, 2, 3, 1, 2, 3]])
        observed = np.array([True, False, True, False, True, True])
        for tau in (0., .1, 8.):
            scores, gradients = filter_subsets(times, np.log(p), states, observed, tau, derivative)
            for i in range(4):
                active = states[i] > 0
                a, g = sequence_score(times[active], np.log(p[i, active])[None], states[i, active], observed[active], tau, derivative[i, active][None])
                self.assertAlmostEqual(scores[i], a[0], places=11)
                np.testing.assert_allclose(gradients[i], g[0], atol=1e-11)
            def shifted(delta):
                z = logits + delta * slopes
                lp = z - logsumexp(z, axis=-1)[..., None]
                return filter_subsets(times, lp, states, observed, tau, np.zeros_like(derivative))[0]
            np.testing.assert_allclose(gradients[:, 0], (shifted(1e-5) - shifted(-1e-5)) / 2e-5, atol=1e-8)

    def test_zero_tau_matches_independent_source_likelihood(self):
        old = WholeSourcePosition(*fixture(), 'signed')
        new = TemporalWholeSourcePosition(*fixture(), 'signed', 0.)
        x = [.1, -.2, .05]
        for held in (False, True):
            a, b = old.evaluate(x, gradient=not held, held=held), new.evaluate(x, gradient=not held, held=held)
            self.assertAlmostEqual(a['score'], b['score'], places=9)
            np.testing.assert_allclose(a['gradient'], b['gradient'], atol=1e-8)

    def test_correlated_assignment_matches_enumeration(self):
        model = TemporalWholeSourcePosition(*fixture(), 'signed', 2.)
        x = np.array([.1, -.2, .05])
        actual = model.evaluate(x)
        tables, rx = {}, {}
        tids = sorted(model.tracks)
        for tid, track in model.tracks.items():
            pred, _ = model.geometry.prediction(track, x)
            tables[tid] = fast.profile(track['y'][None] - pred, track['mask'])[0] - np.log(track['catalogue_size'])
            rx[tid] = model.receiver_probabilities(track, tid, x)
        scores = []
        for assignment in itertools.product(range(2), repeat=len(tids)):
            value = sum(tables[t][c] for t, c in zip(tids, assignment))
            for c in set(assignment):
                members = [t for t, a in zip(tids, assignment) if a == c]
                tid = members[0]
                state = sum(1 << r for r in {model.meta[t]['receiver'] for t in members})
                windows = model.meta[tid]['window_ids']
                times = [model.window_times[w] for w in windows]
                value += sequence_score(times, rx[tid][c][None], np.full(len(times), state), model.tracks[tid]['mask'], 2.)[0][0]
            scores.append(value)
        self.assertAlmostEqual(actual['score'], logsumexp(scores), places=9)
        for axis in range(3):
            d = np.eye(3)[axis] * 1e-4
            numerical = (model.evaluate(x + d, gradient=False)['score'] - model.evaluate(x - d, gradient=False)['score']) / 2e-4
            self.assertAlmostEqual(actual['gradient'][axis], numerical, places=5)
