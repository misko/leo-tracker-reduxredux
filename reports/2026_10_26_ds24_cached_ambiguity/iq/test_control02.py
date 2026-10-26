import unittest
import numpy as np
import control as c
from test_control import ControlTests


class ContinuousLawTests(unittest.TestCase):
    def test_all_right_boundary_values_from_analytic_coefficients(self):
        from leo.analysis.starlink.templates import qin_edge_pilot_symbols, edge_frequencies_hz
        coefficient = qin_edge_pilot_symbols('upper').astype(np.complex128)
        frequencies = edge_frequencies_hz('upper')
        expected = (coefficient*np.exp(-2j*np.pi*frequencies*(2/15*1e-6))).sum(axis=1)/np.sqrt(8)
        boundary = np.arange(2, 302)*44
        np.testing.assert_allclose(c.pilot(boundary, 0), expected, rtol=0, atol=2e-7)
        np.testing.assert_allclose(c.pilot(boundary+1e-8, 0), c.pilot(boundary, 0), rtol=0, atol=2e-7)

    def test_off_boundary_template_agreement_keeps_original_tolerance(self):
        from leo.analysis.starlink.templates import qin_edge_pilot_frame
        expected = qin_edge_pilot_frame(c.RATE, 'upper')
        n = np.arange(len(expected)); keep = n%44 != 0
        self.assertLess(float(np.max(np.abs(c.pilot(n, 0)[keep]-expected[keep]))), 5e-7)


def suite():
    tests = unittest.defaultTestLoader.loadTestsFromTestCase(ContinuousLawTests)
    for name in ('test_fractional_time_translation_and_supported_symbols',
                 'test_iq_noise_is_paired_across_scenarios_and_no_clipping',
                 'test_report_keeps_actual_margin_winner_and_fractional_gate'):
        tests.addTest(ControlTests(name))
    return tests


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(suite())
    raise SystemExit(not result.wasSuccessful())
