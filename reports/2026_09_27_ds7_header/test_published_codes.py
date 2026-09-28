"""Ensure reference matching permits only declared rotation/polarity ambiguity."""

import unittest

import numpy as np
from compare_published_codes import distance_modulo_rotation_polarity


class PublishedCodeTests(unittest.TestCase):
    def test_rotation_and_polarity_equivalence(self):
        a = np.random.default_rng(405).integers(0, 2, 60)
        self.assertEqual(distance_modulo_rotation_polarity(a, 1 - np.roll(a, 17)), 0)

    def test_one_bit_error_is_not_exact_match(self):
        a = np.random.default_rng(405).integers(0, 2, 60)
        b = a.copy()
        b[9] ^= 1
        self.assertEqual(distance_modulo_rotation_polarity(a, b), 1)


if __name__ == "__main__":
    unittest.main()
