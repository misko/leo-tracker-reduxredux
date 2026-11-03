import unittest
import numpy as np
from plot_subset_orbits import alias_background


class BackgroundTests(unittest.TestCase):
    def test_all_unassigned_and_unique_aliases(self):
        alias=np.array([[0,0,1],[0,1,1],[2,2,2]])
        rr,cc=alias_background(alias,np.array([1]))
        self.assertEqual(set(zip(rr,alias[rr,cc])),{(0,0),(0,1),(2,2)})
        self.assertEqual(len(rr),3)

    def test_no_unassigned(self):
        rr,cc=alias_background(np.zeros((2,3),int),np.array([0,1]))
        self.assertEqual(len(rr),0)
        self.assertEqual(len(cc),0)


if __name__ == '__main__':
    unittest.main()
