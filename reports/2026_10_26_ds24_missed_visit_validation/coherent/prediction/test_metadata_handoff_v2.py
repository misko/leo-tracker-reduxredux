import unittest
import metadata_handoff_v2 as v2
import study


class JSONBoundaryTests(unittest.TestCase):
    def test_shared_donor_aliases_are_materialized_before_exact_R01_enrich(self):
        donor=dict(start_counter=100,stop_counter=300,generation='stream',visit_index=1)
        row=dict(header=dict(case='fake',generation='stream'),forecast=dict(modes=[
            dict(donors=[donor],model=dict(donors=[donor]),full=dict(CFO_hz=7.,epoch_samples=3.),halves=[]),
            dict(donors=[donor],model=dict(donors=[donor]),full=dict(CFO_hz=8.,epoch_samples=4.),halves=[])]))
        def authority(start,visit):return dict(index=dict(acquisition=dict(sample_start=start,sample_end=start+200,generation=123),iq_sha256='fake'),
            source_input=dict(sha256='fake'),index_sha256='fake',global_visit=visit)
        result=study.ports()['handoff'].enrich(v2.materialize(row),dict(raw_authority=authority(1000,9)),{('fake',1):authority(100,1)})
        self.assertEqual(donor['generation'],'stream')
        for mode in result['forecast']['modes']:
            self.assertEqual(mode['donors'][0]['generation'],123)
            self.assertEqual(mode['donors'][0]['stream_generation'],'stream')
            self.assertEqual(mode['model']['donors'][0]['stream_generation'],'stream')
        self.assertEqual([m['full']['CFO_hz']for m in result['forecast']['modes']],[7.,8.])


if __name__=='__main__':unittest.main()
