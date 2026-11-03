import unittest
import numpy as np
from benchmark import ALIAS_HZ,canonical_rows,group_folds,split_masks


class BenchmarkTests(unittest.TestCase):
    def test_exact_alias_only_and_same_group(self):
        rows,mapping=canonical_rows([10,10+ALIAS_HZ,10.01,10],[1,1,1,2])
        np.testing.assert_array_equal(rows,[0,2,3]);np.testing.assert_array_equal(mapping,[0,0,2,3])

    def test_group_cannot_cross_folds(self):
        f=group_folds([9.999,10.001,15],[1,1,2])
        self.assertEqual(f[0],f[1])

    def test_embargo_is_group_safe(self):
        t=np.array([8.5,9.1,10,19.9,20.5,22.,30.])
        g=np.array([0,0,1,2,3,4,5])
        train,test=split_masks(t,g,1)
        self.assertFalse(np.any(train&test))
        self.assertFalse(np.any(train[:5]));self.assertTrue(train[5])
        self.assertEqual(set(g[train])&set(g[test]),set())

    def test_bad_measurements(self):
        with self.assertRaises(ValueError):canonical_rows([float('nan')],[0])


if __name__=='__main__':unittest.main()
