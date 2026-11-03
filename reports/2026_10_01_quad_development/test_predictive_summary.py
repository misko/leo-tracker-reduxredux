import unittest
from summarize_predictive_uncertainty import summarize

class SummaryTests(unittest.TestCase):
    def test_missing_is_not_a_tie(self):
        rows=[dict(unit='a',held_points=10,arms=dict(x=dict(scores=dict(policy=20.,single=0.,robust=10.)))),
              dict(unit='b',held_points=90,arms=dict(x=dict(scores=dict(policy=0.,single=0.,robust=None))))]
        d=summarize(rows,'x');self.assertEqual(d['planned_held_points'],100);self.assertEqual(d['valid_held_points'],10)
        self.assertEqual(d['policy_vs_robust'],1.);self.assertFalse(d['gate'])

if __name__=='__main__':unittest.main()
