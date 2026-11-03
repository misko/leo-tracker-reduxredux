import unittest
from policy import choose,family


class DonorSelectionTests(unittest.TestCase):
    def test_late_finalization_and_wrong_hardware_excluded(self):
        base=dict(sample_rate_hz=2500000,radio_id='radio_pluto_5d4d',receiver_ids=[0,1],
                  utc_qualified=True,exclusion_reasons=[],capture_end_utc_ns=20,
                  finalized_utc_ns=30,capture_start_utc_ns=10,session_id='a')
        rows=[dict(base,session_id='later',capture_start_utc_ns=12),base,
              dict(base,session_id='late',finalized_utc_ns=100),
              dict(base,session_id='wrong',radio_id='other')]
        self.assertEqual([c['session_id'] for c in choose(rows,100,2)],['a','later'])

    def test_frequency_subset_is_not_compatible(self):
        families=[dict(family=0,sample_rate_hz=2500000,rf_hz=[10,20])]
        self.assertIsNone(family(2500000,[10],families))
        self.assertEqual(family(2500000,[20,10,10],families),0)
        self.assertIsNone(family(5000000,[10,20],families))
