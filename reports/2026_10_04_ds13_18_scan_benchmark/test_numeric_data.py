import unittest
import numpy as np
from numeric_data import Data, view
from calibration import blocked_folds


class NumericDataTests(unittest.TestCase):
    def test_group_cannot_straddle_fold_boundary(self):
        self.assertEqual(blocked_folds([9.999,10.001,22.],[7,7,8]).tolist(), [1,1,2])

    def test_blocked_partition_has_no_overlap(self):
        folds=blocked_folds(np.arange(300.),np.arange(300))
        for fold in range(5):
            self.assertEqual(sum(folds==fold),60)
            self.assertFalse(np.any((folds==fold)&(folds!=fold)))

    def test_view_preserves_original_identity(self):
        data=Data(**{key:np.arange(5) for key in ('times','measured','rf','receiver','channel','group','margin','original_rows')})
        data.numbers=np.array([12,13])
        part=view(data,[1,4])
        self.assertEqual(part.original_rows.tolist(),[1,4])
        part.measured[0]=99
        self.assertEqual(data.measured[1],1)
        self.assertIs(part.numbers,data.numbers)


if __name__=='__main__':
    unittest.main()
