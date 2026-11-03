import unittest
from seal import choose


class SelectionTests(unittest.TestCase):
    def test_qualification_and_training_score_only(self):
        a=dict(qualified=True,score=1.,distance_m=1.)
        b=dict(qualified=True,score=2.,distance_m=9000.)
        c=dict(qualified=False,score=10.,distance_m=0.)
        self.assertIs(choose([a,b,c]),b)
        self.assertIsNone(choose([c]))
