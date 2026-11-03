import unittest
import numpy as np
from audit_identity_modes import challenge


class IdentityModeTests(unittest.TestCase):
    def test_same_identity_modes_are_not_identity_competitors(self):
        best,margin,passed=challenge(-10,100,[0,-20],[100,200])
        self.assertEqual(best,1);self.assertEqual(margin,10);self.assertTrue(passed)

    def test_better_alternative_mode_can_reject_identity(self):
        self.assertTrue(challenge(-10,100,[-20],[200])[2])
        best,margin,passed=challenge(-10,100,[-20,-9],[200,200])
        self.assertEqual(best,1);self.assertEqual(margin,-1);self.assertFalse(passed)

    def test_invisible_alternative_does_not_compete(self):
        best,margin,passed=challenge(-10,100,[-np.inf],[200])
        self.assertIsNone(best);self.assertIsNone(margin);self.assertTrue(passed)


if __name__=='__main__':unittest.main()
