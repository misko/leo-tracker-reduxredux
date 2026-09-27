"""Requires the deployed analysis environment; no RF source is loaded by tests."""
import unittest
from audit_track_sources import transitions


def row(n,t,cfo,channel=1,normalization=0):
    return {'utc_ns':int(t*1e9),'observation_id':str(n),'normalized_cfo_hz':cfo,
            'source_cfo_hz':cfo-normalization,'normalization_hz':normalization,
            'channel':channel,'edge':'lower','actual_rf_hz':10e9+channel*1e8,
            'partition':'X' if n%2==0 else 'Y','receiver_id':1}


class Tests(unittest.TestCase):
    def test_sorted_time_and_gap(self):
        out=transitions([row(2,12,30),row(0,0,10),row(1,2,20)])
        self.assertEqual(out['span_s'],12)
        self.assertEqual(out['largest_gaps'][0]['dt_s'],10)
        self.assertEqual(out['channel_transitions'],0)

    def test_channel_and_normalization_are_separate(self):
        out=transitions([row(0,0,10),row(1,1,110,2,100)])
        step=out['transitions'][0]
        self.assertTrue(step['channel_changed'])
        self.assertTrue(step['actual_rf_changed'])
        self.assertEqual(step['delta_normalized_hz'],100)
        self.assertEqual(step['delta_source_hz'],0)
        self.assertEqual(step['normalization_change_hz'],100)


if __name__=='__main__':unittest.main()
