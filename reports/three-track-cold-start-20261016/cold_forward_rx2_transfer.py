exec(open('/tmp/three_track_cold_context.py').read())
from dataclasses import replace
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.sequential_group_calibration import freeze_sequential_calibration
ref_v=v.copy();ref_n=n.copy();ref_sh=ref_v[7]+zero_sum_basis(len(nums))@ref_v[8:]
data=json.loads(Path('/tmp/three-track-investigation/space-track-pipeline-rerun/rx2_counterpart_alias_corrected.json').read_text())
good=[r for r in data['records'] if r['margin']>=.025 and abs(r['rx2_minus_rx1_calibrated_hz'])<1000]
rows=np.array([r['row'] for r in good]);sub=replace(observation_subset(obs,rows),receiver=np.ones(len(rows),int),measured_hz=np.array([r['rx2_peak_hz'] for r in good]))
search=json.loads((root/'cold_candidate_temporal_transfer.json').read_text());satellite=next(r['ranked'][0]['satellite'] for r in search['results'] if r['track']=='late_ch2')
k=nums.index(satellite);one=bank.select([k]);out=[]
for filename in ['generic_joint_early_to_late_fitted-c.json','generic_joint_early_to_late_fitted-c_no_bias_from_band.json']:
    record=json.loads((root/filename).read_text());assert record['audit']['accepted'];vv=np.array(record['fit']['vector']);nn=np.array(record['fit']['nuisance'])
    calibration=freeze_sequential_calibration(model.original,dict(vector=vv,nuisance=nn[:model.clock_count]),shift)
    y=sub.measured_hz-calibration.predict(sub.times_s,sub.rf_hz,sub.receiver,sub.channel>=5)
    sh=vv[7]+zero_sum_basis(len(nums))@vv[8:];p=predict_orbits(one,sub,prior,vv[:2],np.array([sh[k]]),derivatives=False)[0][:,0]
    if record['variant']=='band_bias':
        slots=[x['satellite'] for x in record['hypotheses'] if x['mode']=='lower_band_frequency_basis'];a=record['after']['band_frequency_amplitude_s'][slots.index(satellite)]
        basis=predict_orbits(one,sub,prior,ref_v[:2],np.array([ref_sh[k]]),derivatives=True)[3][:,0];p=p+a*basis
    rr=circular(y-p)
    out.append(dict(model=filename,satellite=satellite,guided_rx2_count=len(rows),rms_hz=float(np.sqrt(np.mean(rr**2))),mean_hz=float(np.mean(rr)),within_250_hz=int(np.sum(abs(rr)<=250)),within_500_hz=int(np.sum(abs(rr)<=500)),residuals_hz=rr.tolist()))
result=dict(qualification='Fixed previously qualified RX1-guided RX2 raw-IQ counterpart detections, not reselected to favor new calibration. Cold forward training-fold calibration/model; no correction fitted to RX2 counterpart values. Detection guidance remains a conditioning assumption.',results=out)
(root/'cold_forward_rx2_transfer.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
