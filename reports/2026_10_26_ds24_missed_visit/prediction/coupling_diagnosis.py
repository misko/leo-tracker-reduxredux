"""Earlier-donor coefficient coupling only; no new estimator or target fit."""
from pathlib import Path
import json
import math
import numpy as np
import predictor as p
import study
from timing_diagnosis import distribution

HERE=Path(__file__).resolve().parent
SCORER=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src/leo/analysis/starlink/fast_scan_scores.py')


def coefficient(times,values,order,index,floor):
    x=np.column_stack([np.asarray(times)**degree for degree in range(order+1)])
    beta=np.linalg.lstsq(x,values,rcond=None)[0];residual=np.asarray(values)-x@beta
    df=len(times)-order-1
    inv=np.linalg.inv(x.T@x)
    se=math.sqrt(max(0,float(np.sum(residual**2)/df*inv[index,index])))if df>0 else None
    floor_se=math.sqrt(max(0,float(max(floor**2,np.sum(residual**2)/df if df>0 else floor**2)*inv[index,index])))
    return float(beta[index]),se,floor_se


def summarize(rows):
    if not rows:return dict(cells=0)
    a=np.array([r['timing_acceleration_samples_per_s2']for r in rows]);z=np.array([r['positive_scaled_CFO_slope_samples_per_s2']for r in rows])
    slope=float(z@a/(z@z));residual=a-slope*z
    return dict(cells=len(rows),Pearson_correlation=float(np.corrcoef(a,z)[0,1])if len(rows)>1 and np.std(a)>0 and np.std(z)>0 else None,
        slope_through_origin=slope,slope_descriptive_se=float(np.sqrt(np.sum(residual**2)/max(1,len(rows)-1)/(z@z))),
        positive_relation_residual_samples_per_s2=distribution((a-z).tolist()),
        negative_relation_residual_samples_per_s2=distribution((a+z).tolist()),
        acceleration_to_positive_scaled_CFO_ratio=distribution((a/z).tolist()),
        acceleration_floor_SE_samples_per_s2=distribution([r['timing_acceleration_floor_SE']for r in rows]),
        CFO_slope_floor_SE_Hz_per_s=distribution([r['CFO_slope_floor_SE']for r in rows]))


def main():
    study.bound()
    files=[HERE/'coupling_diagnosis.py',HERE/'protocol.json',HERE/'predictions.json',HERE/'panel.json',SCORER]
    study.write(HERE/'coupling_diagnosis_protocol.json',dict(schema='earlier-donor-timing-CFO-coupling/v1',
        files={str(path):study.sha(path)for path in files},target_outcome_inputs=False,
        cohorts='all primary histories with >=3donors; no target availability or compatibility selection',
        comparisons='a_timing against both signs of Fs/actual_rf_hz times earlier CFO slope',
        coefficient_uncertainty='conditional OLS SE plus engineering floors0.75sample/75Hz; uncalibrated, correlated coefficients',
        new_estimator=False,raw_IQ_reads=0,validation_outcomes=False))
    rows=[]
    for row in study.read(HERE/'predictions.json')['rows']:
        if row['status']!='complete'or not row['forecast']['modes']:continue
        h=row['header'];m=row['forecast']['modes'][0];donors=m['donors']
        if len(donors)<3:continue
        rate=h['sample_rate_hz'];last=donors[-1]
        times=np.array([(d['start_counter']-last['start_counter'])/rate for d in donors])
        phase=np.array([p.wrap(d['epoch_samples']+(d['start_counter']-last['start_counter'])-last['epoch_samples'],rate/750)for d in donors])
        b,se,sefloor=coefficient(times,phase,2,2,.75)
        c,cs,csfloor=coefficient(times,[d['CFO_hz']for d in donors],1,1,75.)
        scale=rate/h['actual_rf_hz']
        rows.append(dict(prediction_id=h['prediction_id'],channel=h['channel'],receiver_id=h['receiver_id'],donor_count=len(donors),
            actual_rf_hz=h['actual_rf_hz'],Fs_over_RF_samples_per_Hz=scale,
            timing_acceleration_samples_per_s2=2*b,timing_acceleration_OLS_SE=None if se is None else 2*se,
            timing_acceleration_floor_SE=2*sefloor,CFO_slope_hz_per_s=c,CFO_slope_OLS_SE=cs,CFO_slope_floor_SE=csfloor,
            positive_scaled_CFO_slope_samples_per_s2=scale*c,negative_scaled_CFO_slope_samples_per_s2=-scale*c,
            positive_difference_floor_SE=float(math.hypot(2*sefloor,scale*csfloor))))
    result=dict(schema='earlier-donor-timing-CFO-coupling/v1',protocol_sha256=study.sha(HERE/'coupling_diagnosis_protocol.json'),
        overall=summarize(rows),by_channel={str(ch):summarize([r for r in rows if r['channel']==ch])for ch in study.CHANNELS},
        by_channel_receiver={f'CH{ch}-RX{rx}':summarize([r for r in rows if r['channel']==ch and r['receiver_id']==rx])for ch in study.CHANNELS for rx in [0,1]},
        rows=rows,uncertainty_calibrated=False,target_epochs_or_target_CFO_used=False,
        physical_RF_mapping_verified=False,raw_IQ_reads=0,new_estimator=False)
    study.write(HERE/'coupling_diagnosis.json',result)
    print(json.dumps(result['overall'],indent=2))


if __name__=='__main__':main()
