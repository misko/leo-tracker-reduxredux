import unittest
from epoch_pairs import delta_us, label_pair


class EpochTests(unittest.TestCase):
    def test_wrap_and_fraction(self):
        a = dict(integer_epoch_sample=999, fractional_epoch_offset_samples=.25)
        b = dict(integer_epoch_sample=1, fractional_epoch_offset_samples=.75)
        self.assertAlmostEqual(delta_us(a, b, 750000, 750), 2.5/750000*1e6)
        self.assertAlmostEqual(delta_us(b, a, 750000, 750), -2.5/750000*1e6)

    def test_ambiguous_is_not_different(self):
        self.assertEqual(label_pair({1}, {1}), 'same')
        self.assertEqual(label_pair({1}, {2}), 'different')
        self.assertEqual(label_pair({1, 2}, {1}), 'unknown')
        self.assertEqual(label_pair(set(), {1}), 'unknown')
