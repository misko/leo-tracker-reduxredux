import unittest
from run_native import mask_for


class MaskTests(unittest.TestCase):
    def test_threshold_boundary_and_original_bin_identity(self):
        p=dict(ranking=list(range(11)),sqrt_ranking=list(reversed(range(11))),sqrt_confidence=.2)
        self.assertEqual(mask_for(p,'full',.1),2047)
        self.assertEqual(mask_for(p,'sqrt3',.1),(1<<10)|(1<<9)|(1<<8))
        self.assertEqual(mask_for(p,'log9',.1),(1<<9)-1)
        self.assertEqual(mask_for(p,'guard5',.2),2047)
        self.assertEqual(mask_for(p,'guard5',.1),sum(1<<f for f in (10,9,8,7,6)))


if __name__=='__main__':unittest.main()
