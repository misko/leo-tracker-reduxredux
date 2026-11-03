import unittest
import math
from ensemble import combine


class EnsembleTests(unittest.TestCase):
    def test_three_collinear_median(self):
        self.assertEqual(combine([[0,0],[2,0],[9,0]],'three_median'),[2,0])

    def test_equilateral_and_translation(self):
        points=[[0,0],[2,0],[1,math.sqrt(3)]]
        self.assertAlmostEqual(combine(points,'three_median')[1],math.sqrt(3)/3,places=8)
        moved=[[x+5,y-7] for x,y in points]
        answer=combine(moved,'three_median')
        self.assertAlmostEqual(answer[0],6,places=8)
        self.assertAlmostEqual(answer[1],math.sqrt(3)/3-7,places=8)

    def test_mean_uses_only_declared_components(self):
        self.assertEqual(combine([[0,0],[900,900],[2,4]],'iid_corr_mean'),[1,2])


if __name__ == '__main__':
    unittest.main()
