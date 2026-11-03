import itertools
import math
import unittest

from study import scores


class MixtureTests(unittest.TestCase):
    def test_shared_and_independent_against_explicit_enumeration(self):
        p = [[0.9, 0.1], [0.1, 0.9], [0.8, 0.2]]
        result = scores([[math.log(v) for v in row] for row in p])
        shared = sum(math.prod(row[i] for row in p) for i in range(2)) / 2
        independent = (
            sum(
                math.prod(p[j][i] for j, i in enumerate(indices))
                for indices in itertools.product(range(2), repeat=3)
            )
            / 8
        )
        self.assertAlmostEqual(result["shared"], math.log(shared))
        self.assertAlmostEqual(result["independent"], math.log(independent))
        self.assertGreater(result["independent"], result["shared"])

    def test_agreement_can_favor_shared_mixture(self):
        r = scores([[math.log(0.9), math.log(0.1)]] * 3)
        self.assertGreater(r["shared"], r["independent"])
        self.assertAlmostEqual(sum(r["shared_posterior"]), 1)

    def test_permutation_and_log_offset_invariance(self):
        matrix = [[-10000.0, -10002.0], [-10001.0, -10004.0]]
        a = scores(matrix)
        b = scores([row[::-1] for row in matrix[::-1]])
        self.assertAlmostEqual(a["shared"], b["shared"])
        c = scores([[v + 10000 for v in row] for row in matrix])
        self.assertAlmostEqual(a["independent"] - a["shared"], c["independent"] - c["shared"])


if __name__ == "__main__":
    unittest.main()
