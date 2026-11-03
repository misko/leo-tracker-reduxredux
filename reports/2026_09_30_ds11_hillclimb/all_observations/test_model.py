import copy
import unittest
from unittest.mock import patch

import numpy as np
from scipy.special import logsumexp

import model


def prediction(self, track, x):
    t = track['times_s']
    values = np.array([30*t+2*t*t, -40*t+3*t*t])
    values += x[0]*t+x[1]*t*t+x[2]*np.sin(t)
    # Candidate 1 is visible only on a formerly held observation. This catches
    # accidental expansion of the candidate visibility support.
    return values, np.array([True, bool(track['mask'][0])])


class AllObservationTests(unittest.TestCase):
    def setUp(self):
        t = np.linspace(-2, 2, 21)
        self.track = dict(times_s=t, y=500+30*t+2*t*t+25*np.sin(3*t),
                          mask=np.arange(21)%3 != 0, catalogue_size=8000)
        self.doc = dict(tracks=[self.track])
        self.config = dict(geographic_prior_center_deg=[38., -122.], timing_grid_s=[-5., 5.])
        self.x = np.array([.2, -.1, .3])
        self.mock = patch.object(model.fast.Stationary, 'prediction', prediction)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def test_original_exact_parity_and_input_mask_isolation(self):
        original = self.track['mask'].copy()
        wrapper = model.Model([self.doc], self.config, 'original')
        expected = model.fast.Stationary(self.doc, self.config).evaluate(self.x, True)
        actual = wrapper.evaluate(self.x)
        self.assertEqual(actual['score'], expected[0])
        np.testing.assert_array_equal(actual['gradient'], expected[1])
        all_data = model.Model([self.doc], self.config, 'all')
        all_data.evaluate(self.x)
        np.testing.assert_array_equal(self.track['mask'], original)
        self.assertFalse(np.shares_memory(all_data.engine.document['tracks'][0]['mask'], original))

    def test_all_density_and_original_visibility(self):
        wrapper = model.Model([self.doc], self.config, 'all')
        pred, visible = prediction(None, self.track, self.x)
        score, _, _, _ = model.fast.profile(self.track['y'][None, :]-pred,
                                            np.ones_like(self.track['mask']))
        expected = logsumexp(np.where(visible, score, -np.inf))-np.log(8000)
        self.assertEqual(wrapper.evaluate(self.x)['score'], expected)
        self.assertEqual(wrapper.metadata['fitting_observations'], 21)
        self.assertFalse(wrapper.metadata['held_diagnostic_independent'])

    def test_gradient_and_former_held_values_enter_fit(self):
        wrapper = model.Model([self.doc], self.config, 'all')
        result = wrapper.evaluate(self.x)
        for axis in range(3):
            delta = np.eye(3)[axis]*1e-4
            numeric = (wrapper.evaluate(self.x+delta)['score']-wrapper.evaluate(self.x-delta)['score'])/2e-4
            self.assertAlmostEqual(result['gradient'][axis], numeric, places=6)
        changed = copy.deepcopy(self.doc)
        changed['tracks'][0]['y'][~self.track['mask']] += 400
        other = model.Model([changed], self.config, 'all').evaluate(self.x)
        self.assertNotAlmostEqual(result['score'], other['score'])
        before = model.Model([self.doc], self.config, 'original').evaluate(self.x)
        after = model.Model([changed], self.config, 'original').evaluate(self.x)
        self.assertEqual(before['score'], after['score'])
