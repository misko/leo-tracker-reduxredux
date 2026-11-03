import unittest
import numpy as np
from bit_ownership import source_bits


class OwnershipBitTests(unittest.TestCase):
    def test_definite_hit_wins_independently_of_iteration_order(self):
        pairs = [('unique', {'A'}), ('ambiguous', {'A', 'B'})]
        views = {'unique': (0, 0), 'ambiguous': (0, 0)}
        for order in (pairs, pairs[::-1]):
            np.testing.assert_array_equal(source_bits('A', dict(order), views, 2), [[1, 0], [0, 0]])
            np.testing.assert_array_equal(source_bits('B', dict(order), views, 2), [[-1, 0], [0, 0]])

    def test_unknown_is_not_missed_detection(self):
        bits = source_bits('A', {'candidate': {'A', 'B'}}, {'candidate': (0, 1)}, 1)
        np.testing.assert_array_equal(bits, [[0, -1]])
