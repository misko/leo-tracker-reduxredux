import copy
import unittest
import handoff
import predictor
from test_predictor import fabricated


class HandoffTests(unittest.TestCase):
    def test_native_generation_is_distinct_from_stream_label(self):
        h,history=fabricated();row=dict(header=h,status='complete',forecast=predictor.predict(h,history));saved=copy.deepcopy(row)
        def authority(start,visit):
            return dict(index=dict(acquisition=dict(sample_start=start,sample_end=start+200000,generation=12345),iq_sha256='sha256:iq'),
                source_input=dict(sha256='sha256:input'),index_sha256='sha256:index',global_visit=visit)
        slot=dict(raw_authority=authority(h['start_counter'],9))
        lookup={(h['case'],p['visit_index']):authority(p['valid_start_counter'],p['visit_index'])for p in history}
        packet=handoff.enrich(row,slot,lookup)
        self.assertEqual(packet['header']['generation'],12345)
        self.assertEqual(packet['header']['stream_generation'],'fabricated')
        self.assertEqual(row,saved)
        for original,new in zip(row['forecast']['modes'],packet['forecast']['modes']):
            for k in original['full']:
                self.assertEqual(original['full'][k],new['full'][k])
            self.assertEqual(new['donors'][0]['generation'],12345)
        self.assertEqual(packet['donor_metadata_status'],'verified')


if __name__=='__main__':unittest.main()
