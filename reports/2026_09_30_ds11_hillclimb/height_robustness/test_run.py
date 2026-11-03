import unittest
from run import select

class SelectionTests(unittest.TestCase):
    def test_failed_or_unqualified_high_scores_cannot_win(self):
        valid = dict(qualified=True, score=2, x=[0, 0, 0])
        self.assertIs(select([None, dict(qualified=False, score=100), valid]), valid)
        self.assertIsNone(select([None, dict(qualified=False, score=100)]))

    def test_selection_uses_training_score_only(self):
        first = dict(qualified=True, score=2, held=100, geographic_error=0)
        second = dict(qualified=True, score=3, held=-100, geographic_error=10000)
        self.assertIs(select([first, second]), second)
