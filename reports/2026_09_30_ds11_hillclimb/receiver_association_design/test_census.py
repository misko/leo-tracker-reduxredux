import unittest
from census import classify
class CensusTests(unittest.TestCase):
    def test_four_states(self):
        for a,b,want in [(0,0,'neither'),(1,0,'rx0_only'),(0,1,'rx1_only'),(1,1,'both')]:
            self.assertEqual(classify([dict(rx=r,rf=10,counter=100,offset=0,passing=n) for r,n in [(0,a),(1,b)]]),want)
    def test_missing_or_incompatible_is_unknown(self):
        a=dict(rx=0,rf=10,counter=100,offset=0,passing=1)
        self.assertEqual(classify([a]),'unknown')
        self.assertEqual(classify([a,a]),'unknown')
        self.assertEqual(classify([a,dict(a,rx=1,rf=11)]),'unknown')
