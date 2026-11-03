import unittest
from run import select_time


class SelectionTests(unittest.TestCase):
    def test_training_score_and_tie_rule(self):
        self.assertEqual(select_time([{'tau_s': 100, 'score': 1},
                                      {'tau_s': 10, 'score': 1},
                                      {'tau_s': 1, 'score': 0}]), 10)

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            select_time([{'tau_s': 1, 'score': float('nan')}])
