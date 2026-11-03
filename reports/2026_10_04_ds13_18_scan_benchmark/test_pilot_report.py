import unittest
from render_pilot import validate_comparison


class PilotReportTests(unittest.TestCase):
    def test_consistent_fixed_denominator_score(self):
        validate_comparison(dict(assigned=90,unassigned=10,denominator=100,coverage=.9,satellites=3,objective=60))

    def test_false_coverage_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'coverage'):
            validate_comparison(dict(assigned=90,unassigned=10,denominator=100,coverage=.95,satellites=3,objective=60))

    def test_satellite_penalty_sign(self):
        with self.assertRaisesRegex(ValueError,'objective'):
            validate_comparison(dict(assigned=90,unassigned=10,denominator=100,coverage=.9,satellites=3,objective=120))
