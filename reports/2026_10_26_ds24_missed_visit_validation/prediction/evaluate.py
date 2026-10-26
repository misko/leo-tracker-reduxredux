"""Sealed development archived timing diagnostic. No target-dependent tuning."""
from pathlib import Path
from collections import Counter
import json
import numpy as np
import predictor
import study

HERE=Path(__file__).resolve().parent


def candidates(probe,period):
    out=[]
    if probe is None:return out
    for c in sorted(probe['candidates'],key=lambda c:c['candidate_rank']):
        if not 0<=c['candidate_rank']<=8 or not c['passed_fractional_margin_gate']or c['fractional_margin']<.025:continue
        ep=c['integer_epoch_sample']+c['fractional_epoch_offset_samples'];cfo=c['fractional_tracking_cfo_hz']
        if any(abs(predictor.wrap(ep-a['epoch_samples'],period))<=2 and abs(cfo-a['cfo_hz'])<=200 for a in out):continue
        out.append(dict(rank=c['candidate_rank'],epoch_samples=ep,cfo_hz=cfo))
    return out


def stats(values):
    if not values:return dict(n=0)
    x=np.asarray(values)
    return dict(n=len(x),mean=float(np.mean(x)),median=float(np.median(x)),
        median_absolute_error=float(np.median(abs(x))),rmse=float(np.sqrt(np.mean(x*x))),
        p05=float(np.quantile(x,.05)),p95=float(np.quantile(x,.95)),
        within_2_samples=int(np.sum(abs(x)<=2)),within_16_samples=int(np.sum(abs(x)<=16)))


def summarize(rows):
    return dict(cells=len(rows),**{method:stats([r['errors_samples'][method]for r in rows])for method in
        ['linear','quadratic_or_fallback','legacy_adapter_linear']})


def main():
    study.bound();seal=study.read(HERE/'forecast_seal.json')
    assert study.sha(HERE/'predictions.json')==seal['predictions_sha256']
    predictions=study.read(HERE/'predictions.json');targets={r['prediction_id']:r['target_original']for r in
        study.read(study.PRIOR/'evaluation_targets.json')['rows']}
    rows=[];original_passing=0
    for row in predictions['rows']:
        period=row['header']['sample_rate_hz']/750
        original=candidates(targets[row['prediction_id']],period);original_passing+=bool(original)
        if not row['methods']:continue
        cfo=row['methods']['linear']['cfo_hz'];compatible=[c for c in original if abs(c['cfo_hz']-cfo)<=500]
        if not compatible:continue
        chosen=min(compatible,key=lambda c:(abs(c['cfo_hz']-cfo),c['rank']))
        rows.append(dict(prediction_id=row['prediction_id'],case=row['header']['case'],channel=row['header']['channel'],
            receiver_id=row['header']['receiver_id'],status=row['status'],target_original_rank=chosen['rank'],
            CFO_error_hz=chosen['cfo_hz']-cfo,donor_count=len(row['donors']),
            legacy_adapter_minus_consistent_linear_epoch_samples=row['legacy_adapter_minus_consistent_linear_epoch_samples'],
            errors_samples={method:predictor.wrap(chosen['epoch_samples']-point['epoch_samples'],period)for method,point in row['methods'].items()}))
    result=dict(schema='development-archived-primary-timing-diagnostic/v2',forecast_seal_sha256=study.sha(HERE/'forecast_seal.json'),
        predictions_sha256=study.sha(HERE/'predictions.json'),requested_receiver_cells=576,
        original_target_gatepassing_cells=original_passing,forecast_statuses=seal['statuses'],
        overall=summarize(rows),by_predictor_status={key:summarize([r for r in rows if r['status']==key])for key in seal['statuses']},
        by_channel={str(ch):summarize([r for r in rows if r['channel']==ch])for ch in [1,4,5,6,7,8]},
        by_channel_receiver={f'CH{ch}-RX{rx}':summarize([r for r in rows if r['channel']==ch and r['receiver_id']==rx])for ch in [1,4,5,6,7,8]for rx in [0,1]},
        rows=rows,match_policy='unchanged primary CFO within500Hz; nearest absolute CFO then original rank; timing unused',
        archived_fullwindow_acquisition_exposed=True,external_truth=False,raw_IQ_reads=0,validation_outcomes_opened=False,
        tuning_after_evaluation=False)
    study.write(HERE/'archived_diagnostic.json',result)
    print(json.dumps(result['overall'],indent=2),flush=True)


if __name__=='__main__':main()
