exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from leo.analysis.regional_position_bootstrap import observation_subset
import time

begun=time.monotonic()
choices=[json.loads((root/name).read_text()) for name in ['excluded_calibration_fitted-c.json','excluded_calibration_fitted-c_from_zero.json']]
accepted=[r for r in choices if r['audit']['accepted']]
fit=min(accepted,key=lambda r:r['audit']['objective'])
v=np.array(fit['fit']['vector']);n=np.array(fit['fit']['nuisance'])
correction=model.original.correction(v,n[:model.clock_count])
allnums=new['provenance']['full_candidate_numbers'];full,_=build_regional_bank(cat,[lookup[num] for num in allnums],origin,obs,prior)
results=[];rng=np.random.default_rng(20261016)
for name,path in [('early_ch2','/tmp/rx1-ch2-50-75'),('ch4','/tmp/rx1-ch4-40-100'),('late_ch2','/tmp/rx1-ch2-170-190')]:
    rows=np.load(path+'/arrays.npz')['rows']
    if name=='early_ch2':rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
    sub=observation_subset(obs,rows);y=obs.measured_hz[rows]-correction[rows];early=sub.times_s<=np.median(sub.times_s)
    splits=[('early_to_late',early),('late_to_early',~early)]
    null_values=[np.array([y[train]]+[rng.permutation(y[train]) for _ in range(8)]) for _,train in splits]
    scores=[np.full((9,len(full.numbers)),np.inf) for _ in splits]
    timings=[np.zeros((9,len(full.numbers))) for _ in splits]
    test_residuals=[np.zeros((np.sum(~train),len(full.numbers))) for _,train in splits]
    train_rms=[np.zeros((9,len(full.numbers))) for _ in splits]
    for shift in np.linspace(-5,5,201):
        pred,visible,_,_=predict_orbits(full,sub,prior,v[:2],np.full(len(full.numbers),shift),derivatives=False)
        for j,(_,train) in enumerate(splits):
            residual=circular(null_values[j][:,:,None]-pred[None,train,:])
            rms=np.sqrt(np.mean(residual*residual,axis=1))
            objective=np.sum((residual/125)**2,axis=1)+(shift/2)**2
            objective[:,~visible[train].all(axis=0)]=np.inf
            take=objective<scores[j];scores[j][take]=objective[take];timings[j][take]=shift;train_rms[j][take]=rms[take]
            # Only the real training sequence has withheld test predictions.
            test_residuals[j][:,take[0]]=circular(y[~train,None]-pred[~train,:])[:,take[0]]
    for j,(split,train) in enumerate(splits):
        order=np.argsort(scores[j],axis=1);best=order[:,0];runnerup=order[:,1]
        records=[]
        for control in range(9):
            k=int(best[control]);second=int(runnerup[control]);rms=float(train_rms[j][control,k]);gap=float(scores[j][control,second]-scores[j][control,k])
            records.append(dict(control='real' if control==0 else f'shuffle_{control}',satellite=int(full.numbers[k]),timing_s=float(timings[j][control,k]),training_rms_hz=rms,penalized_score_gap=gap,passes_predeclared_gate=bool(rms<=375 and gap>=20)))
        real=records[0];k=int(best[0]);rr=test_residuals[j][:,k]
        real.update(test_rms_hz=float(np.sqrt(np.mean(rr**2))),test_count=len(rr),test_within_375hz=int(np.sum(abs(rr)<=375)),test_times_s=sub.times_s[~train].tolist(),test_residuals_hz=rr.tolist())
        result=dict(track=name,split=split,training_count=int(train.sum()),records=records)
        results.append(result);print(json.dumps(dict(track=name,split=split,real=real,shuffled_passes=sum(r['passes_predeclared_gate'] for r in records[1:]))),flush=True)
out=dict(qualification='Generic timing-only coherent-track candidate search; no satellite-specific exception. All 129 original targets excluded from fitted calibration likelihood. Conditional evaluation retains full-scan selected background bank/high-band contrast/saved warm-start; target tracks were inspected. Shuffling controls are exploratory and do not calibrate a global false-alarm rate.',training_fit_objective=fit['audit']['objective'],training_fit_initialization=fit.get('initialization','compressed saved start'),candidate_count=len(full.numbers),controls_per_split=8,gate=dict(maximum_training_rms_hz=375,minimum_penalized_score_gap=20),elapsed_seconds=time.monotonic()-begun,results=results)
(root/'generic_recovery_target_excluded_controls.json').write_text(json.dumps(out,indent=2)+'\n')
