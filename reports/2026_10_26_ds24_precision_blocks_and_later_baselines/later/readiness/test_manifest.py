import copy
import unittest
from manifest import selected_four,clock_authority,assert_identity


class ManifestTests(unittest.TestCase):
    def test_four_unchanged_identities_and_chronology(self):
        rows=[dict(recording_id=str(i),session_id='s'+str(i),name_time_proxy_utc_ns=i,proposed_fixed4_metadata_member=True)for i in range(4)]
        self.assertEqual(selected_four(dict(rows=rows)),rows)
        with self.assertRaises(ValueError):selected_four(dict(rows=rows[:3]))
        rows[3]['session_id']='s0'
        with self.assertRaises(ValueError):selected_four(dict(rows=rows))

    def test_acquisition_bracket_not_manifest_creation(self):
        d=dict(clock_anchor=dict(sample_counter=100,before=dict(realtime_ns=1000,monotonic_ns=100),after=dict(realtime_ns=1100,monotonic_ns=200)),
            delivery_clocks=[dict(realtime_ns=1200,monotonic_ns=300)],source=dict(capture_start_utc_ns=None,probes=[dict(valid_start_counter=100)]),manifest_created=999999)
        r=clock_authority(d)
        self.assertEqual(r['anchor_utc_ns'],1050);self.assertEqual(r['causal_cutoff_utc_ns'],1000)
        self.assertIsNone(r['source_capture_start_utc_ns'])
        d['clock_anchor']['after']['realtime_ns']=999
        with self.assertRaises(ValueError):clock_authority(d)

    def test_raw_authority_transition_is_not_silent(self):
        item=dict(recording_id='r',session_id='s',contract_metadata=[dict(declared_raw_authority_digest='raw')])
        row=dict(sample_member=dict(recording_id='r',session_id='s',raw_authority_digest='raw'))
        assert_identity(item,row)
        row['sample_member']['raw_authority_digest']='changed'
        with self.assertRaises(ValueError):assert_identity(item,row)


if __name__=='__main__':unittest.main()
