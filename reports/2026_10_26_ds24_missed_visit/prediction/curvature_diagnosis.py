"""Donor-only curvature/held-donor diagnosis. No target correction or RF calls."""
from pathlib import Path
import json
import numpy as np
import predictor as p
import study
from timing_diagnosis import distribution

HERE=Path(__file__).resolve().parent


def fit(times,values,order):
    matrix=np.column_stack([np.asarray(times)**degree for degree in range(order+1)])
    beta=np.linalg.lstsq(matrix,values,rcond=None)[0]
    residual=np.asarray(values)-matrix@beta
    return beta,residual


def summarize(rows):
    held=[r for r in rows if r['held_last_linear_error_samples']is not None]
    return dict(cells=len(rows),negative_fitted_curvature=sum(r['timing_acceleration_samples_per_s2']<0 for r in rows),
        acceleration_samples_per_s2=distribution([r['timing_acceleration_samples_per_s2']for r in rows]),
        donor_linear_residual_rms_samples=distribution([r['donor_linear_residual_rms_samples']for r in rows]),
        donor_quadratic_residual_rms_samples=distribution([r['donor_quadratic_residual_rms_samples']for r in rows]),
        implied_quadratic_minus_linear_at_target_origin_samples=distribution([r['implied_quadratic_minus_linear_at_target_origin_samples']for r in rows]),
        held_last_donor=dict(cells=len(held),linear_error_samples=distribution([r['held_last_linear_error_samples']for r in held]),
            quadratic_error_samples=distribution([r['held_last_quadratic_error_samples']for r in held]),
            quadratic_lower_absolute_error=sum(abs(r['held_last_quadratic_error_samples'])<abs(r['held_last_linear_error_samples'])for r in held)))


def main():
    study.bound()
    names=['curvature_diagnosis.py','timing_diagnosis.py','protocol.json','predictions.json','timing_diagnosis.json']
    study.write(HERE/'curvature_diagnosis_protocol.json',dict(schema='posthoc-donor-curvature-diagnosis/v1',
        files={str(HERE/n):study.sha(HERE/n)for n in names},posthoc_descriptive=True,
        input_data='earlier donor epochs/counters only; no target epochs enter a fit',
        diagnostic_cohorts='all primary histories >=3donors, plus explicitly labeled existing CFOcompatible cohort',
        held_last_donor='fit older donors and predict latest earlier donor; >=4donors required',
        target_prediction_changes=False,accepted_new_estimator=False,raw_IQ_reads=0,validation_outcomes=False))
    compatible={r['prediction_id']for r in study.read(HERE/'timing_diagnosis.json')['rows']}
    rows=[]
    for row in study.read(HERE/'predictions.json')['rows']:
        if row['status']!='complete' or not row['forecast']['modes']:continue
        h=row['header'];m=row['forecast']['modes'][0];donors=m['donors']
        if len(donors)<3:continue
        first=donors[0];rate=h['sample_rate_hz'];period=rate/750
        times=np.array([(d['start_counter']-first['start_counter'])/rate for d in donors])
        phase=np.array([p.wrap(d['epoch_samples']+(d['start_counter']-first['start_counter'])-first['epoch_samples'],period)for d in donors])
        linear,lr=fit(times,phase,1);quadratic,qr=fit(times,phase,2)
        target_time=(h['start_counter']-first['start_counter'])/rate
        discrepancy=float(np.polyval(quadratic[::-1],target_time)-np.polyval(linear[::-1],target_time))
        held_lin=held_quad=None
        if len(donors)>=4:
            hl,_=fit(times[:-1],phase[:-1],1);hq,_=fit(times[:-1],phase[:-1],2)
            held_lin=float(phase[-1]-np.polyval(hl[::-1],times[-1]))
            held_quad=float(phase[-1]-np.polyval(hq[::-1],times[-1]))
        rows.append(dict(prediction_id=h['prediction_id'],channel=h['channel'],receiver_id=h['receiver_id'],
            donor_count=len(donors),history_span_s=float(times[-1]),elapsed_s=m['full']['elapsed_s'],
            existing_CFOcompatible_target_cohort=h['prediction_id']in compatible,
            timing_acceleration_samples_per_s2=float(2*quadratic[2]),
            donor_linear_residual_rms_samples=float(np.sqrt(np.mean(lr*lr))),
            donor_quadratic_residual_rms_samples=float(np.sqrt(np.mean(qr*qr))),
            implied_quadratic_minus_linear_at_target_origin_samples=discrepancy,
            donor_times_s=times.tolist(),donor_linear_residual_samples=lr.tolist(),
            held_last_linear_error_samples=held_lin,held_last_quadratic_error_samples=held_quad))
    result=dict(schema='posthoc-donor-curvature-diagnosis/v1',protocol_sha256=study.sha(HERE/'curvature_diagnosis_protocol.json'),
        all_primary_histories=summarize(rows),existing_CFOcompatible_cohort=summarize([r for r in rows if r['existing_CFOcompatible_target_cohort']]),
        by_channel={str(ch):summarize([r for r in rows if r['channel']==ch])for ch in study.CHANNELS},
        rows=rows,target_epochs_used_in_any_fit=False,sealed_forecasts_unchanged=True,raw_IQ_reads=0)
    study.write(HERE/'curvature_diagnosis.json',result)
    print(json.dumps({k:v for k,v in result.items()if k in ['all_primary_histories','existing_CFOcompatible_cohort']},indent=2))


if __name__=='__main__':main()
