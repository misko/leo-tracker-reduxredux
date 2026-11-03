import unittest
from pathlib import Path
from screen_hyperparameters import CONFIGS,metrics,run


class ScreeningTests(unittest.TestCase):
    def test_not_a_cartesian_grid(self):
        self.assertEqual(len(CONFIGS),5)
        self.assertIn((10.,600.),CONFIGS)

    def test_common_gate_and_score(self):
        result=metrics(dict(assignments=[dict(residual_hz=50),dict(residual_hz=800)],denominator=4,
                            assigned=2,unassigned=2,coverage=.5,satellites=1))
        self.assertEqual(result['support_300_fraction'],.25)
        self.assertEqual(result['reference_score_p10'],-8)

    def test_test_scans_cannot_be_screened(self):
        with self.assertRaisesRegex(ValueError,'development'):
            run(Path('/tmp'),['N01'])
