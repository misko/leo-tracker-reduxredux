exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from dataclasses import replace
from scipy.optimize import minimize_scalar
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.sequential_group_calibration import SequentialShift,freeze_sequential_calibration

choices=[json.loads((root/name).read_text()) for name in ['excluded_calibration_fitted-c.json','excluded_calibration_fitted-c_from_zero.json']]
f=min((x for x in choices if x['audit']['accepted']),key=lambda x:x['audit']['objective']);v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance'])
correction=model.original.correction(v,n[:model.clock_count]);sh=v[7]+zero_sum_basis(len(nums))@v[8:]
discovery=json.loads((root/'generic_recovery_target_excluded_controls.json').read_text())
high=stages[new['selection']['source']+'-high']['result']['fit'];shift=SequentialShift(tuple(high['group_receivers']),np.array(high['group_offsets_hz']))
cal=freeze_sequential_calibration(model.original,dict(vector=v,nuisance=n[:model.clock_count]),shift)
counterparts=json.loads((root/'rx2_counterpart_alias_corrected.json').read_text())
good=[r for r in counterparts['records'] if r['margin']>=.025 and abs(r['rx2_minus_rx1_calibrated_hz'])<1000]
rx2rows=np.array([r['row'] for r in good]);rx2obs=replace(observation_subset(obs,rx2rows),receiver=np.ones(len(good),int),measured_hz=np.array([r['rx2_peak_hz'] for r in good]))
rx2y=rx2obs.measured_hz-cal.predict(rx2obs.times_s,rx2obs.rf_hz,rx2obs.receiver,rx2obs.channel>=5)
assert np.allclose(cal.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5),correction,atol=1e-6)
out=[]
for name,path in [('early_ch2','/tmp/rx1-ch2-50-75'),('ch4','/tmp/rx1-ch4-40-100'),('late_ch2','/tmp/rx1-ch2-170-190')]:
    rows=np.load(path+'/arrays.npz')['rows']
    if name=='early_ch2':rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
    sub=observation_subset(obs,rows);y=obs.measured_hz[rows]-correction[rows]
    early=sub.times_s<=np.median(sub.times_s)
    for split,train in [('early_to_late',early),('late_to_early',~early)]:
        satellite=next(r['records'][0]['satellite'] for r in discovery['results'] if r['track']==name and r['split']==split)
        k=nums.index(satellite);one=bank.select([k]);p0=predict_orbits(one,sub,prior,v[:2],np.array([sh[k]]),derivatives=False)[0][:,0]
        derivative=predict_orbits(one,sub,prior,v[:2],np.array([sh[k]]),derivatives=True)[3][:,0]
        base=circular(y-p0);center=float(np.mean(sub.times_s[train]));x=sub.times_s-center
        rx2p=predict_orbits(one,rx2obs,prior,v[:2],np.array([sh[k]]),derivatives=False)[0][:,0] if name=='late_ch2' else None
        for mode in ['baseline','frequency_offset','frequency_affine','doppler_derivative_bias','timing']:
            params={};rx2rr=None
            if mode in ['baseline','frequency_offset','frequency_affine']:
                width=0 if mode=='baseline' else 1 if mode=='frequency_offset' else 2
                design=np.column_stack([np.ones(len(x)),x])[:,:width]
                coef=np.linalg.lstsq(design[train],base[train],rcond=None)[0] if width else np.zeros(0)
                rr=base-design@coef;params=dict(frequency_offset_hz=float(coef[0]) if width else 0.,frequency_drift_hz_s=float(coef[1]) if width==2 else 0.,time_center_s=center)
                if name=='late_ch2':rx2rr=circular(rx2y-rx2p-np.column_stack([np.ones(len(good)),rx2obs.times_s-center])[:,:width]@coef)
            elif mode=='doppler_derivative_bias':
                amplitude=float(derivative[train]@base[train]/(derivative[train]@derivative[train]))
                rr=base-amplitude*derivative;params=dict(frequency_basis_amplitude_s=amplitude,qualification='Frequency-domain Doppler-derivative basis; no measurement timestamp or orbital state is shifted.');width=1
                if name=='late_ch2':
                    rx2derivative=predict_orbits(one,rx2obs,prior,v[:2],np.array([sh[k]]),derivatives=True)[3][:,0]
                    rx2rr=circular(rx2y-rx2p-amplitude*rx2derivative)
            else:
                def loss(timing):
                    pp=predict_orbits(one,sub,prior,v[:2],np.array([timing]),derivatives=False)[0][:,0]
                    return float(np.mean(circular(y[train]-pp[train])**2))
                grid=np.linspace(-5,5,201);start=grid[np.argmin([loss(t) for t in grid])]
                opt=minimize_scalar(loss,bounds=(max(-5,start-.06),min(5,start+.06)),method='bounded')
                pp=predict_orbits(one,sub,prior,v[:2],np.array([opt.x]),derivatives=False)[0][:,0];rr=circular(y-pp)
                params=dict(total_timing_s=float(opt.x),extra_timing_s=float(opt.x-sh[k]));width=1
                if name=='late_ch2':rx2rr=circular(rx2y-predict_orbits(one,rx2obs,prior,v[:2],np.array([opt.x]),derivatives=False)[0][:,0])
            record=dict(track=name,split=split,satellite=satellite,mode=mode,parameters=params,parameter_count=width,training_count=int(train.sum()),test_count=int((~train).sum()),training_rms_hz=float(np.sqrt(np.mean(rr[train]**2))),test_rms_hz=float(np.sqrt(np.mean(rr[~train]**2))))
            if rx2rr is not None:record.update(guided_rx2_count=len(good),guided_rx2_rms_hz=float(np.sqrt(np.mean(rx2rr**2))))
            out.append(record)
result=dict(qualification='Conditional emission-model comparison at automatically training-selected satellite identities; all 129 target measurements excluded from calibration likelihood. Models fitted on one RX1 temporal half, evaluated on the other half and guided RX2 counterparts where available. Candidate bank/high contrast/saved warm start remain conditioned on original full scan. No independent position accuracy claim.',results=out)
(root/'emission_model_target_excluded_transfer.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(out,indent=2),flush=True)
