import unittest
from prepare_validation import prior_evidence


class ValidationShortlistTests(unittest.TestCase):
    def test_failed_zero_error_start_is_not_valid_accuracy(self):
        rows=[dict(scan=n,arm=a,prior_width_scale=s,best_joint_stationary=n=='ok',boundary=False,
                   radius_m=0 if n=='failed' else 100*s)
              for n in ('ok','failed') for a in ('fitted-c','zero-c') for s in (.5,1.,2.)]
        evidence=prior_evidence(rows)
        self.assertEqual(evidence['fitted-c']['common_valid_scans'],['ok'])
        self.assertEqual(evidence['fitted-c']['by_scale']['1.0']['mean_error_common_valid_m'],100)
        self.assertEqual(evidence['fitted-c']['by_scale']['1.0']['nonstationary'],1)
