import unittest
from census import census


class DetectionCensusTests(unittest.TestCase):
    def test_passing_untracked_candidate_is_not_detector_absence(self):
        candidate = dict(projected_candidate_id='unused', passed_fractional_margin_gate=True, fractional_exact_score=.6, fractional_control_score=.1, fractional_margin=.5)
        doc = dict(tracks=[], opportunities=[dict(receivers=dict(rx0=dict(receiver_status='observed_candidate_present', candidates=[candidate]), rx1=dict(receiver_status='observed_candidate_absent', candidates=[])))])
        out = census(doc)
        self.assertEqual(out['counts']['detected_but_no_retained_track'], 1)
        self.assertEqual(out['paired_states'], {'detector:10/tracks:00': 1})
