import unittest
from application import make_slots,materialize,ports


def source():
    probes=[]
    for visit in range(21):
        for rx in [0,1]:
            probes.append(dict(channel=1,receiver_id=rx,edge='upper',valid_start_counter=visit*3000000,
                visit_index=visit,probe_index=visit,actual_rf_hz=12e9,candidates=['target poison']))
    return dict(sample_rate_hz=10000000,probe_ms=20,stream_generation='stream-example',
        session_id='public-example',raw_recording_authority_digest='sha256:example',probes=probes)


class ApplicationTests(unittest.TestCase):
    def test_target_candidates_excluded_and_selection_unchanged(self):
        one=source();two=source()
        for p in two['probes']:p['candidates']=[{'epoch_samples':1e99}]
        a=make_slots('example',one,'tracking','hash','input','inputhash')
        b=make_slots('example',two,'tracking','hash','input','inputhash')
        self.assertEqual([s.get('probe_metadata')for s in a],[s.get('probe_metadata')for s in b])
        self.assertEqual(len(a),24);self.assertEqual(sum(len(s['cells'])for s in a),48)
        self.assertEqual([s['probe_metadata']['visit_index']for s in a[:4]],[4,8,12,16])
        self.assertTrue(all('candidates'not in s.get('probe_metadata',{})for s in a))

    def test_strictly_earlier_bounded_history_and_early_tie(self):
        original=source();slots=make_slots('example',original,'tracking','hash','input','inputhash')
        history=slots[3]['cells'][0]['history']
        self.assertEqual([p['visit_index']for p in history],list(range(4,16)))
        self.assertTrue(all(p['receiver_id']==0 and p['valid_start_counter']+200000<=48000000 for p in history))
        # 20% of a ten-counter extent is 2, equidistant from starts1 and3.
        test=source();test['probes']=[dict(p,valid_start_counter=v,visit_index=i)
            for i,v in enumerate([0,1,3,10])for p in test['probes'][:2]]
        chosen=make_slots('example',test,'tracking','hash','input','inputhash')[0]
        self.assertEqual(chosen['probe_metadata']['valid_start_counter'],1)

    def test_serialized_alias_boundary_with_original_enricher(self):
        handoff=ports()['handoff'];donor=dict(visit_index=1,generation='stream',start_counter=0,stop_counter=200000)
        mode=dict(donors=[donor],model=dict(donors=[donor]),full={},halves=[])
        row=dict(header=dict(case='example',generation='stream'),forecast=dict(modes=[mode,mode]))
        authority=dict(index=dict(acquisition=dict(sample_start=0,sample_end=200000,generation=42),iq_sha256='IQ'),
            source_input=dict(sha256='input'),index_sha256='index',global_visit=1)
        result=handoff.enrich(materialize(row),dict(raw_authority=authority),{('example',1):authority})
        for m in result['forecast']['modes']:
            self.assertEqual(m['donors'][0]['stream_generation'],'stream')
            self.assertEqual(m['donors'][0]['generation'],42)
        self.assertEqual(donor['generation'],'stream')


if __name__=='__main__':unittest.main()
