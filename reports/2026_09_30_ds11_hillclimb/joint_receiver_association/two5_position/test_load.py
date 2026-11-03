import unittest
import numpy as np
from load import seeds


class SeedTests(unittest.TestCase):
    def test_failed_original_coordinates_are_not_used(self):
        expected=np.array([[0,0,0],[0,0,2]])
        np.testing.assert_array_equal(seeds(None),expected)
        np.testing.assert_array_equal(seeds(dict(qualified=False,x=[-12,3,1])),expected)

    def test_qualified_original_and_center_retained(self):
        np.testing.assert_array_equal(seeds(dict(qualified=True,x=[1,2,3])),[[1,2,3],[0,0,0]])
