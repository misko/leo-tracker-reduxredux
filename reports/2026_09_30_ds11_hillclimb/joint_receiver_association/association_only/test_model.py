import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from model import AssociationOnlyPosition, WholeSourcePosition


class FrozenReceiverTests(unittest.TestCase):
    def test_all_candidates_retained_and_emissions_frozen(self):
        def initialize(instance, *args):
            instance.tracks = {'track': object()}
        calls = []
        def probabilities(instance, track, tid, x):
            calls.append(x.copy())
            return np.log(np.full((4, 6, 3), 1 / 3))
        initial = np.array([2., 3., 1.])
        with patch.object(WholeSourcePosition, '__init__', initialize), patch.object(WholeSourcePosition, 'receiver_probabilities', probabilities):
            model = AssociationOnlyPosition(None, None, None, None, 'signed', initial)
        initial[:] = 99.
        for x in (np.zeros(3), np.ones(3) * 4):
            p = model.receiver_probabilities(None, 'track', x)
            self.assertEqual(p.shape, (4, 6, 3))
            np.testing.assert_allclose(np.exp(p).sum(axis=-1), 1.)
            self.assertFalse(p.flags.writeable)
        self.assertEqual(len(calls), 1)
        np.testing.assert_array_equal(model.receiver_reference_x, [2., 3., 1.])
