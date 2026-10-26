import copy
import unittest
import natural_adapter as adapter


class NaturalAdapterTests(unittest.TestCase):
    def fixture(self):
        authority=dict(index=dict(acquisition=dict(sample_start=4000000,sample_end=4200000,
            generation=9,device_session=12,actual_if_center_hz=999),iq_sha256='iq'),
            target=dict(rf_center_hz=10e9),source_input={'path':'source','sha256':'sourcehash'},
            index_path='index',index_sha256='indexhash',global_visit=10)
        slot=dict(request_id='case-CH5',case='case',channel=5,raw_authority=authority,
            target_original=dict(secret_target_winner=777))
        prediction=dict(target_start_counter=4000000,target_visit_index=10,sample_rate_hz=10_000_000,
            receiver_id=0,edge='lower',forecast=dict(status='available',primary_mode=0,modes=[dict(
            status='complete',seed_rank=1,donor_counters=[1000000],donor_ranks=[2],donor_CFO_hz=[120.],
            linear=dict(epoch_samples=456.25,CFO_hz=140.),constant=dict(CFO_hz=120.),
            CFO_fit=dict(heuristic_half_width_3scale=600.),horizon_s=.3)]))
        donor=copy.deepcopy(authority);donor['index']['acquisition'].update(sample_start=1000000,sample_end=1200000)
        return slot,prediction,{('case',1000000,0):donor}

    def test_target_response_redaction_and_units(self):
        slot,pred,auth=self.fixture();a=adapter.map_packet(slot,pred,auth,100000)
        slot['target_original']=dict(secret_target_winner=-99999)
        b=adapter.map_packet(slot,pred,auth,100000)
        self.assertEqual(a,b);self.assertEqual(a['target_support']['start_counter'],4100000)
        self.assertEqual(a['hypotheses'][0]['prediction_sigma_hz'],200.)
        self.assertAlmostEqual(a['hypotheses'][0]['elapsed_s'],.31)
        self.assertEqual(a['hypotheses'][0]['donors'][0]['support']['generation'],9)
        self.assertEqual(a['independent_doppler_observations'],0)

    def test_ambiguous_and_missing_do_not_create_hypotheses(self):
        slot,pred,auth=self.fixture()
        for state in ['ambiguous_earlier_matches','missing_earlier_matches']:
            pred['forecast']['modes'][0]['status']=state
            out=adapter.map_packet(slot,pred,auth)
            self.assertEqual(out['hypotheses'],[])


if __name__=='__main__':unittest.main(verbosity=2)
