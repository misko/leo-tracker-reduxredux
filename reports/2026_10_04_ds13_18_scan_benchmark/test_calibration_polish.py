import unittest
from polish_saved_calibration import verify_reconstruction


class CalibrationPolishTests(unittest.TestCase):
    def test_reconstruction_must_match_saved_objective(self):
        verify_reconstruction(23.0000001,23.)
        for value in (24.,float('nan'),float('inf')):
            with self.assertRaisesRegex(ValueError,'reconstruct'):verify_reconstruction(value,23.)
