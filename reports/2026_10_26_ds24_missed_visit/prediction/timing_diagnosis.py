"""Posthoc signed timing diagnosis; no predictor changes or raw scoring."""
from pathlib import Path
import json
import numpy as np
import predictor as p
import study

HERE=Path(__file__).resolve().parent


def distribution(values):
    if not values:return dict(n=0)
    x=np.asarray(values,float)
    return dict(n=len(x),mean=float(np.mean(x)),median=float(np.median(x)),sd=float(np.std(x)),
        median_absolute_error=float(np.median(abs(x))),
        mean_absolute_error=float(np.mean(abs(x))),rmse=float(np.sqrt(np.mean(x*x))),
        p05=float(np.quantile(x,.05)),p25=float(np.quantile(x,.25)),p75=float(np.quantile(x,.75)),p95=float(np.quantile(x,.95)),
        within_2_samples=int(np.sum(abs(x)<=2)),within_16_samples=int(np.sum(abs(x)<=16)))


def summarize(rows):
    return dict(cells=len(rows),fitted_signed_timing_error_samples=distribution([r['fitted_error_samples']for r in rows]),
        carry_signed_timing_error_samples=distribution([r['carry_error_samples']for r in rows]),
        fitted_minus_carry_absolute_error_samples=distribution([abs(r['fitted_error_samples'])-abs(r['carry_error_samples'])for r in rows]))


def main():
    study.bound()
    names=['timing_diagnosis.py','protocol.json','predictions.json','evaluation_targets.json']
    study.write(HERE/'timing_diagnosis_protocol.json',dict(schema='posthoc-signed-timing-diagnosis/v1',
        files={str(HERE/n):study.sha(HERE/n)for n in names},posthoc_descriptive=True,
        cohort='primary predictor mode with an original gatepassing target within500Hz',
        target_match='minimum absolute CFOdifference then original rank among CFOcompatible targets; timing unused in selection',
        error_sign='target epoch minus prediction, circular sample difference',
        comparisons='same matched target: frozen fitted prediction versus latest-donor zero-rate carry',
        predictor_changes=False,raw_IQ_reads=0,validation_outcomes=False))
    target={r['prediction_id']:r['target_original']for r in study.read(HERE/'evaluation_targets.json')['rows']}
    rows=[]
    for row in study.read(HERE/'predictions.json')['rows']:
        if row['status']!='complete' or not row['forecast']['modes']:continue
        h=row['header'];mode=row['forecast']['modes'][0];full=mode['full'];rate=h['sample_rate_hz'];period=rate/750
        original=target[h['prediction_id']]
        candidates=p.measured_candidates(original,h)if original else []
        compatible=[c for c in candidates if abs(c['CFO_hz']-full['CFO_hz'])<=500]
        if not compatible:continue
        chosen=min(compatible,key=lambda c:(abs(c['CFO_hz']-full['CFO_hz']),c['candidate_rank']))
        last=mode['donors'][-1]
        carry=(last['epoch_samples']-(h['start_counter']-last['start_counter']))%period
        rows.append(dict(prediction_id=h['prediction_id'],case=h['case'],channel=h['channel'],receiver_id=h['receiver_id'],
            donor_count=mode['donor_count'],elapsed_s=full['elapsed_s'],mode_order=1,
            target_original_rank=chosen['candidate_rank'],CFO_compatible_target_count=len(compatible),
            CFO_error_hz=chosen['CFO_hz']-full['CFO_hz'],
            fitted_error_samples=p.wrap(chosen['epoch_samples']-full['epoch_samples'],period),
            carry_error_samples=p.wrap(chosen['epoch_samples']-carry,period),
            fitted_minus_carry_prediction_samples=p.wrap(full['epoch_samples']-carry,period),
            timing_rate_samples_per_s=full['timing_rate_samples_per_s'],
            timing_fit_max_residual_samples=mode['model']['timing_fit']['max_residual'],
            timing_half_width_samples=full['timing_half_width_samples']))
    result=dict(schema='posthoc-signed-timing-diagnosis/v1',protocol_sha256=study.sha(HERE/'timing_diagnosis_protocol.json'),
        overall=summarize(rows),by_channel={str(ch):summarize([r for r in rows if r['channel']==ch])for ch in study.CHANNELS},
        by_channel_receiver={f'CH{ch}-RX{rx}':summarize([r for r in rows if r['channel']==ch and r['receiver_id']==rx])for ch in study.CHANNELS for rx in [0,1]},
        by_gap_s={f'{lo}..{hi}':summarize([r for r in rows if lo<=r['elapsed_s']<hi])for lo,hi in [(0,.5),(.5,1),(1,2),(2,4.51)]},
        by_donor_count={label:summarize([r for r in rows if lo<=r['donor_count']<=hi])for label,lo,hi in [('one',1,1),('two',2,2),('three_plus',3,12)]},
        by_case={case:summarize([r for r in rows if r['case']==case])for case in study.read(HERE.parent/'split.json')['development']},
        rows=rows,cohort_is_posthoc_CFOcompatible=False if not rows else True,
        external_identity_truth=False,predictor_unchanged=True)
    study.write(HERE/'timing_diagnosis.json',result)
    print(json.dumps(result['overall'],indent=2))


if __name__=='__main__':main()
