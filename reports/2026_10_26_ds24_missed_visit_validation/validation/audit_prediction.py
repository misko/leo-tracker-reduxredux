"""Independent earlier-only/reference audit; no timing/raw/held outcomes."""
import collections
import importlib.util
import json
from pathlib import Path
import time

import numpy as np

HERE=Path(__file__).resolve().parent
PRED=HERE.parent/'prediction'
PRIOR=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/prediction')


def read(p):return json.loads(Path(p).read_text())


def relative_phase_samples(donor,last,period):
    # Difference exact native integers before mixing in sub-sample timing.
    value=donor['epoch_samples']+(donor['start_counter']-last['start_counter'])-last['epoch_samples']
    return (value+period/2)%period-period/2


def main():
    began=time.monotonic()
    import hashlib
    def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    protocol=read(PRED/'protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    original=read(PRIOR/'prediction_packets.json')['rows'];new=read(PRED/'predictions.json')
    assert new['source_packets_sha256']==sha(PRIOR/'prediction_packets.json')
    spec=importlib.util.spec_from_file_location('independent_constant_epoch_quadratic',PRED/'predictor.py')
    predictor=importlib.util.module_from_spec(spec);spec.loader.exec_module(predictor)
    counts=collections.Counter();timing_corrections=[];legacy_shifts=[]
    for old,row in zip(original,new['rows'],strict=True):
        assert predictor.predict(old)==row
        assert predictor.predict(dict(old,target_original={'secret':1e90}))==row
        counts[row['status']]+=1
        assert row['target_support']==old['target_support']
        if row['status']=='no_donor':assert row['methods']=={};continue
        mode=old['forecast']['modes'][0];h=row['header'];full=mode['full'];rate=h['sample_rate_hz']
        assert row['primary_hypothesis_id']==mode['hypothesis_id']
        assert row['donors']==mode['donors']
        linear=row['methods']['linear'];quad=row['methods']['quadratic_or_fallback'];legacy=row['methods']['legacy_adapter_linear']
        assert linear['epoch_samples']==full['epoch_samples']
        for method in row['methods'].values():
            assert method['cfo_hz']==full['CFO_hz']
            assert method['cfo_rate_hz_s']==full['CFO_rate_hz_per_s']
            assert method['cfo_reference_counter']==full['reference_counter']
            assert method['reference_offset_s']==.01
        expected=(linear['epoch_samples']+full['timing_rate_samples_per_s']*.01)%(rate/750)
        assert abs(predictor.wrap(legacy['epoch_samples']-expected,rate/750))<1e-9
        legacy_shifts.append(predictor.wrap(legacy['epoch_samples']-linear['epoch_samples'],rate/750))
        for donor in row['donors']:
            assert donor['stop_counter']<=h['start_counter']
            assert donor['reference_counter']==(donor['start_counter']+donor['stop_counter'])/2
            assert type(donor['generation']) is int and isinstance(donor['stream_generation'],str)
        if row['status']=='linear_fallback':assert quad==linear;continue
        m=row['model'];donors=row['donors'];last=donors[-1]
        assert len(donors)>=5 and m['history_span_s']>=1 and m['design_rank']==3 and m['design_condition']<=100
        assert abs(m['acceleration_samples_per_s2'])<=10
        assert max(abs(v) for v in m['target_start_mid_end_rates_samples_per_s'])<=200
        t=np.array([(d['reference_counter']-last['reference_counter'])/rate for d in donors])
        u=(t-np.mean(t))/(np.ptp(t)/2);design=np.column_stack((np.ones(len(u)),u,u*u))
        phase=np.array([relative_phase_samples(d,last,rate/750) for d in donors])
        beta=np.linalg.lstsq(design,phase,rcond=None)[0]
        np.testing.assert_allclose(beta,m['coefficients_scaled'],rtol=0,atol=1e-6)
        middle=(h['start_counter']+h['stop_counter'])/2
        evaluated=predictor.evaluate(m,rate,h['start_counter'],middle)
        assert evaluated['epoch_samples']==quad['epoch_samples']
        timing_corrections.append(predictor.wrap(quad['epoch_samples']-linear['epoch_samples'],rate/750))
    out=dict(all_passed=True,rows=576,statuses=dict(counts),fresh_prediction_replays=576,response_redaction_checks=576,
        same_primary_branch_and_CFO_all_methods=True,consistent_linear_equals_round1_primary_full=True,
        legacy_control_separate=True,no_extra_midpoint_advance=True,
        quadratic_correction_samples=dict(min=min(timing_corrections),median=float(np.median(timing_corrections)),max=max(timing_corrections)),
        legacy_extra_shift_samples=dict(min=min(legacy_shifts),median=float(np.median(legacy_shifts)),max=max(legacy_shifts)),
        timing_reference='nominal midpoint-effective measurement, epoch relative to origin; exact sample weighting unknown',
        uncertainty_calibrated=False,held_validation_target_outcomes_opened=False,timing_control_outcomes_read=False,
        raw_IQ_reads=0,geographic_errors_read=False,
        protocol_sha256=sha(PRED/'protocol.json'),predictions_sha256=sha(PRED/'predictions.json'),seconds=time.monotonic()-began)
    with (HERE/'prediction_audit.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
