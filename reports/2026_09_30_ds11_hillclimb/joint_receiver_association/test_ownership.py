import math
import unittest
from ownership import alternatives
class OwnershipTests(unittest.TestCase):
    def test_unique_observation_ownership_and_prior(self):
        rows=alternatives(dict(a=['left','right'],b=['first','second']))
        self.assertEqual(len(rows),4);self.assertAlmostEqual(sum(math.exp(w) for _,w in rows),1)
        self.assertTrue(all(set(r)=={'a','b'} and len(r)==2 for r,_ in rows))
    def test_empty_and_budget(self):
        self.assertEqual(alternatives({}),[({},0.)])
        with self.assertRaises(ValueError):alternatives(dict(a=['a','b']),max_states=1)
        with self.assertRaises(ValueError):alternatives(dict(a=['a','a']))
