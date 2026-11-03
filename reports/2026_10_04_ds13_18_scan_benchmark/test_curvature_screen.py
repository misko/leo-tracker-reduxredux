import unittest
from screen_curvature import exclusions,allowed_cutoffs


class CurvatureScreenTests(unittest.TestCase):
    def test_validation_requires_registration_and_test_stays_locked(self):
        cohort={'scans':[{'label':'D','split':'development'},{'label':'V','split':'validation'},{'label':'T','split':'locked_test'}]}
        protocol={'validation_scans':['V','T'],'curvature_cutoffs':[1.1]}
        self.assertEqual(allowed_cutoffs(cohort,'D'),(1.1,1.05))
        self.assertEqual(allowed_cutoffs(cohort,'V',protocol),(1.1,))
        with self.assertRaises(ValueError):allowed_cutoffs(cohort,'V')
        with self.assertRaises(ValueError):allowed_cutoffs(cohort,'T',protocol)

    def test_any_receiver_freezes_same_satellite_exclusion(self):
        rows=[dict(satellite=1,arm='fitted-c',curvature_ratio=1.2),
              dict(satellite=1,arm='fitted-c',curvature_ratio=1.01),
              dict(satellite=2,arm='zero-c',curvature_ratio=2.),
              dict(satellite=3,arm='fitted-c',curvature_ratio=None),
              dict(satellite=4,arm='fitted-c',curvature_ratio=1.1)]
        self.assertEqual(exclusions(rows,1.1),[1])
        self.assertEqual(exclusions(rows,1.05),[1,4])
