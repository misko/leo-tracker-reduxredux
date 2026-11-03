import unittest
import numpy as np
from audit_consistent_bound import validate


class BoundAuditTests(unittest.TestCase):
    def test_mode_switch_rejected_independently(self):
        p=[dict(catalog_number=1,segments=[dict(eligible_rows=[0])]),dict(catalog_number=1,segments=[dict(eligible_rows=[1])])]
        records=[dict(row_index=i,catalog_number=1,proposal=i) for i in range(2)]
        with self.assertRaises(ValueError):validate(records,p,np.array([0,1]),{0,1})

    def test_unproposed_edge_rejected(self):
        with self.assertRaises(ValueError):validate([dict(row_index=1,catalog_number=1,proposal=0)],
            [dict(catalog_number=1,segments=[dict(eligible_rows=[0])])],np.array([0,1]),{0,1})


if __name__=='__main__':unittest.main()
