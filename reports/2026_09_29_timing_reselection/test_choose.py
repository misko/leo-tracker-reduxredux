import unittest

from run import choose


class Tests(unittest.TestCase):
    def test_preserve_continuous_optimum_and_tie(self):
        self.assertEqual(choose(0.13, 10.0, [-1, 0, 1], [9, 10, 9]), (0.13, 0.0))

    def test_switch_only_on_training_score_gain(self):
        self.assertEqual(choose(0.13, 10.0, [-1, 0, 1], [9, 12, 11]), (0.0, 2.0))


if __name__ == "__main__":
    unittest.main()
