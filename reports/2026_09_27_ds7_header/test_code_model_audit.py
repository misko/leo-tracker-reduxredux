"""Tests distinguish binary rank from real rank and bound affine seed models."""

import unittest

import numpy as np
from code_model_audit import binary_rank


class RankTests(unittest.TestCase):
    def test_binary_dependence_differs_from_real_rank(self):
        a = np.array([[1, 1, 0], [1, 0, 1], [0, 1, 1]], dtype=np.uint8)
        self.assertEqual(binary_rank(a), 2)
        self.assertEqual(np.linalg.matrix_rank(a), 3)

    def test_fixed_seed_affine_bound_and_extra_variable(self):
        rng = np.random.default_rng(123)
        seeds = np.vstack([np.zeros((1, 15), dtype=np.uint8), np.eye(15, dtype=np.uint8)])
        mapping = np.c_[np.eye(15, dtype=np.uint8), rng.integers(0, 2, (15, 45))]
        constant = rng.integers(0, 2, 60, dtype=np.uint8)
        words = ((seeds @ mapping) % 2).astype(np.uint8) ^ constant
        self.assertEqual(binary_rank(words ^ words[0]), 15)
        extra = constant.copy()
        extra[-1] ^= 1
        extended = np.vstack([words, extra])
        self.assertEqual(binary_rank(extended ^ extended[0]), 16)


if __name__ == "__main__":
    unittest.main()
