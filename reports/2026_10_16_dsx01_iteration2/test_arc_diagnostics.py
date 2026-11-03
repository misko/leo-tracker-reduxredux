"""Evidence-accounting and frozen extraction/profile replay tests."""
from dataclasses import dataclass
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from numpy.testing import assert_array_equal

from arc_diagnostics import MODELS, arc_profile, summarize_overlap

sys.path.insert(0, str(MODELS))
from model_a import extract_tracks
from leo.analysis.regional_position_score import circular


@dataclass
class Observations:
    window_ids: tuple
    times_s: np.ndarray
    measured_hz: np.ndarray
    rf_hz: np.ndarray
    receiver: np.ndarray
    channel: np.ndarray
    margin: np.ndarray


def observations(measured):
    measured = np.asarray(measured, float)
    n = len(measured)
    return Observations(tuple(str(k) for k in range(n)), np.arange(n)*.5,
        measured, np.full(n, 11.2e9), np.zeros(n, int), np.ones(n, int), np.ones(n))


class ArcDiagnosticTests(unittest.TestCase):
    def test_overlap_union_never_counts_a_row_twice(self):
        report = summarize_overlap([np.array([0,1,2]), np.array([1,2,3]),
                                    np.array([9,10])], [0,1,2,3,4])
        self.assertEqual(report['covered'], 4)
        self.assertEqual(report['best_overlap'], 3)
        self.assertEqual(report['overlapping_arcs'], 2)
        self.assertEqual(report['total'], 5)

    def test_empty_arc_list_preserves_missing_denominator(self):
        report = summarize_overlap([], [1,2,3])
        self.assertEqual(report['covered'], 0)
        self.assertEqual(report['total'], 3)
        self.assertEqual(report['best_arcs'], [])

    def test_frozen_extraction_alias_crossing_and_held_cfo_invariance(self):
        obs = observations(circular(-110000. - 500*np.arange(48)*.5))
        mask = np.arange(48) < 24
        first = extract_tracks(obs, mask, np.zeros(48), maximum_tracks=512)
        self.assertGreater(len(first), 0)
        covered = summarize_overlap(first, np.flatnonzero(mask))
        self.assertEqual(covered['covered'], 24)
        obs.measured_hz[~mask] = np.resize([np.nan, np.inf, -np.inf, 1e99], (~mask).sum())
        second = extract_tracks(obs, mask, np.zeros(48), maximum_tracks=512)
        self.assertEqual(len(first), len(second))
        for left, right in zip(first, second):
            assert_array_equal(left, right)
            self.assertTrue(mask[right].all())

    def test_eleven_of_sixteen_fails_frozen_seventy_percent_gate(self):
        obs = observations([0.]*11 + [500.]*5)
        bank = SimpleNamespace(numbers=np.array([1001]))

        def prediction(bank, selected, prior, position, tau, **kwargs):
            # tau=0 is the poor saved phase; tau=1 fits eleven selected samples.
            values = np.full((len(selected.times_s), 1), 2000. if tau[0] == 0 else 0.)
            return values, np.ones_like(values, dtype=bool), None, None

        with patch('leo.analysis.hard60_score.predict_orbits', prediction):
            result = arc_profile(obs, np.zeros(16), bank, None, np.zeros(9),
                                 [np.arange(16)], np.array([0.]), grid=[1.])
        self.assertEqual(result['max_coherent_fraction'][0][0], 11/16)
        self.assertEqual(result['gains'][0], 0.)
        self.assertEqual(result['supporting_arcs'][0], 0)
        self.assertEqual(result['projection_calls'], 2)

    def test_twelve_of_sixteen_produces_positive_profile_gain(self):
        obs = observations([0.]*12 + [500.]*4)
        bank = SimpleNamespace(numbers=np.array([1001]))

        def prediction(bank, selected, prior, position, tau, **kwargs):
            values = np.full((len(selected.times_s), 1), 2000. if tau[0] == 0 else 0.)
            return values, np.ones_like(values, dtype=bool), None, None

        with patch('leo.analysis.hard60_score.predict_orbits', prediction):
            result = arc_profile(obs, np.zeros(16), bank, None, np.zeros(9),
                                 [np.arange(16)], np.array([0.]), grid=[1.])
        self.assertEqual(result['max_coherent_fraction'][0][0], 12/16)
        self.assertGreater(result['gains'][0], 25.)
        self.assertEqual(result['shifts'][0], 1.)


if __name__ == '__main__':
    unittest.main()
