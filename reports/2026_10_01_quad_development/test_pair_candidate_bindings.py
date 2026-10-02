import copy
import unittest
from export_pair_candidates import validate_groups,FIELDS

class BindingTests(unittest.TestCase):
    def fixture(self):
        p={k:0 for k in FIELDS};p.update(candidate_id='a',source_group_id='g')
        return p
    def test_competitors_preserved(self):
        p=self.fixture();other=dict(p,candidate_id='b',candidate_rank=1)
        self.assertEqual(len(validate_groups([p],[p,other])['g']),2)
    def test_missing_duplicate_corrupt_rejected(self):
        p=self.fixture()
        for rows in ([],[p,p],[dict(p,measured_cfo_hz=1)],[p,dict(p,candidate_id='b',source_group_id='wrong')]):
            with self.assertRaises(ValueError):validate_groups([p],rows)

if __name__=='__main__':unittest.main()
