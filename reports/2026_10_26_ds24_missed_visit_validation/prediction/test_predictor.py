import copy
import unittest
import numpy as np
import predictor as p


def fabricated(starts=None,acceleration=-3.,initial_rate=20.,target_time=2.):
    starts=[0.,.4,.8,1.2,1.6]if starts is None else starts
    rate=10000000;size=200000;base=1700000000000;period=rate/750
    donors=[]
    for i,t in enumerate(starts):
        origin=base+round(t*rate);reference=origin+size//2;tr=(reference-base)/rate
        phase=250+initial_rate*tr+.5*acceleration*tr*tr
        donors.append(dict(observation_id=f'fabricated/v{i}/rx0/r0',candidate_rank=0,visit_index=i,
            epoch_samples=float((phase-(origin-base))%period),CFO_hz=100000+1000*tr,margin=.1,
            start_counter=origin,stop_counter=origin+size,reference_counter=reference,generation=123,
            stream_generation='fabricated',source_id='fabricated-no-IQ',support=dict(start_counter=origin,
                stop_counter=origin+size,generation=123,IQ_sha256='fabricated-no-IQ')))
    start=base+round(target_time*rate);last=donors[-1]
    header=dict(prediction_id='fabricated/CH7/RX0',request_id='fabricated-CH7-F20',case='fabricated',channel=7,receiver_id=0,
        edge='lower',sample_rate_hz=rate,start_counter=start,stop_counter=start+size,window_samples=size,
        generation=123,stream_generation='fabricated',source_id='fabricated-no-IQ')
    times=np.array([(d['reference_counter']-last['reference_counter'])/rate for d in donors])
    phase=np.array([p.wrap(d['epoch_samples']+(d['start_counter']-last['start_counter'])-last['epoch_samples'],period)for d in donors])
    x=np.column_stack((np.ones(len(times)),times));b=np.linalg.lstsq(x,phase,rcond=None)[0]
    midpoint=start+size//2;dt=(midpoint-last['reference_counter'])/rate
    ep=(last['epoch_samples']-(start-last['start_counter'])+b[0]+b[1]*dt)%period
    full=dict(epoch_samples=float(ep),CFO_hz=100000+1000*(target_time+.01),CFO_rate_hz_per_s=1000.,
        reference_counter=midpoint,CFO_half_width_hz=300.,CFO_sigma_hz=100.,timing_rate_samples_per_s=float(b[1]),
        timing_sigma_samples=1.,timing_half_width_samples=3.)
    mode=dict(hypothesis_id='fabricated-primary',status='multi_donor',donors=donors,full=full)
    return dict(header=header,target_support=dict(start_counter=start,stop_counter=start+size,generation=123,
        IQ_sha256='fabricated-no-IQ'),forecast=dict(primary_mode=0,modes=[mode]))


class QuadraticTests(unittest.TestCase):
    def test_known_curvature_midpoint_and_origin(self):
        row=fabricated();result=p.predict(row);self.assertEqual(result['status'],'quadratic')
        q=result['methods']['quadratic_or_fallback'];period=1e7/750
        target_start=2.;mid=2.01
        expected=(250+20*mid-1.5*mid*mid-target_start*1e7)%period
        origin=(250+20*target_start-1.5*target_start**2-target_start*1e7)%period
        self.assertAlmostEqual(p.wrap(q['epoch_samples']-expected,period),0,places=6)
        self.assertAlmostEqual(p.wrap(q['epoch_at_target_origin_samples']-origin,period),0,places=6)
        self.assertAlmostEqual(result['model']['acceleration_samples_per_s2'],-3,places=6)
        self.assertGreater(q['timing_sigma_samples'],2)
        self.assertGreater(result['model']['acceleration_SE_samples_per_s2'],0)

    def test_primary_CFO_linear_and_legacy_exact(self):
        row=fabricated();saved=copy.deepcopy(row);result=p.predict(row);full=row['forecast']['modes'][0]['full']
        self.assertEqual(row,saved)
        self.assertEqual(result['methods']['linear']['epoch_samples'],full['epoch_samples'])
        for method in result['methods'].values():self.assertEqual(method['cfo_hz'],full['CFO_hz'])
        expected=(full['epoch_samples']+full['timing_rate_samples_per_s']*.01)%(1e7/750)
        self.assertEqual(result['methods']['legacy_adapter_linear']['epoch_samples'],expected)

    def test_support_and_span_fallbacks(self):
        result=p.predict(fabricated(starts=[0,.4,.8,1.2]))
        self.assertEqual(result['status'],'linear_fallback')
        self.assertIn('fewer_than_five_donors',result['model']['fallback_reasons'])
        self.assertEqual(result['methods']['quadratic_or_fallback'],result['methods']['linear'])
        result=p.predict(fabricated(starts=[0,.1,.2,.3,.4]))
        self.assertIn('history_span_below_one_second',result['model']['fallback_reasons'])

    def test_acceleration_and_propagated_rate_gates(self):
        result=p.predict(fabricated(acceleration=11))
        self.assertIn('timing_acceleration_above_10',result['model']['fallback_reasons'])
        result=p.predict(fabricated(acceleration=9,initial_rate=184,target_time=2.4))
        self.assertIn('target_timing_rate_above_200',result['model']['fallback_reasons'])

    def test_conditioning_and_native_causality(self):
        result=p.predict(fabricated(starts=[0,.02,.04,.06,4],target_time=4.4))
        self.assertIn('quadratic_design_condition_above_100',result['model']['fallback_reasons'])
        row=fabricated();row['forecast']['modes'][0]['donors'][-1]['stop_counter']=row['header']['start_counter']+1
        with self.assertRaises(ValueError):p.predict(row)

    def test_response_redaction_alternatives_and_no_donor(self):
        row=fabricated();expected=p.predict(row)
        row['header']['target_candidates']=[dict(epoch_samples=123,CFO_hz=9e8)]
        row['forecast']['modes'].append(dict(invalid_alternative=True))
        self.assertEqual(expected,p.predict(row))
        row['forecast']['modes']=[];row['forecast']['primary_mode']=None
        result=p.predict(row);self.assertEqual(result['status'],'no_donor');self.assertFalse(result['methods'])


if __name__=='__main__':unittest.main()
