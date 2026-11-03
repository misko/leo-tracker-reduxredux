import unittest
from run import validate_slots
class SlotTests(unittest.TestCase):
    def test_exact_order(self):
        validate_slots([2,5,7],[2,5,7])
        with self.assertRaises(AssertionError):validate_slots([5,2,7],[2,5,7])
    def test_loss_and_duplicates_rejected(self):
        with self.assertRaises(AssertionError):validate_slots([2,5],[2,5,7])
        with self.assertRaises(AssertionError):validate_slots([2,2],[2,2])
