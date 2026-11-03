exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from leo.analysis.regional_position_bootstrap import observation_subset
import time

begun=time.monotonic()
allnums=new['provenance']['full_candidate_numbers']
full,_=build_regional_bank(cat,[lookup[num] for num in allnums],origin,obs,prior)
# Freeze the original unseeded Space-Track solution, before any inspected-track repair.
correction=model.original.correction(v,n[:model.clock_count])
results=[]
for name,path in [('early_ch2','/tmp/rx1-ch2-50-75'),('ch4','/tmp/rx1-ch4-40-100'),('late_ch2','/tmp/rx1-ch2-170-190')]:
    rows=np.load(path+'/arrays.npz')['rows']
    if name=='early_ch2':rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
    sub=observation_subset(obs,rows); y=obs.measured_hz[rows]-correction[rows]
    early=sub.times_s<=np.median(sub.times_s)
    splits=[('early_to_late',early),('late_to_early',~early)]
    best=[np.full(len(full.numbers),np.inf) for _ in splits]
    timings=[np.zeros(len(full.numbers)) for _ in splits]
    train_rms=[np.zeros(len(full.numbers)) for _ in splits]
    test_rms=[np.zeros(len(full.numbers)) for _ in splits]
    for shift in np.linspace(-5,5,201):
        pred,visible,_,_=predict_orbits(full,sub,prior,v[:2],np.full(len(full.numbers),shift),derivatives=False)
        residual=circular(y[:,None]-pred)
        for j,(_,train) in enumerate(splits):
            # Same one-parameter timing family and 2-second prior for every satellite.
            rms_train=np.sqrt(np.mean(residual[train]**2,axis=0))
            score=np.sum((residual[train]/125)**2,axis=0)+(shift/2)**2
            score[~visible[train].all(axis=0)]=np.inf
            take=score<best[j];best[j][take]=score[take];timings[j][take]=shift
            train_rms[j][take]=rms_train[take]
            # Test measurements never select candidate or timing.
            test_rms[j][take]=np.sqrt(np.mean(residual[~train]**2,axis=0))[take]
    for j,(split,train) in enumerate(splits):
        ranked=[dict(satellite=int(full.numbers[k]),timing_s=float(timings[j][k]),training_objective=float(best[j][k]),training_rms_hz=float(train_rms[j][k]),test_rms_hz=float(test_rms[j][k])) for k in np.argsort(best[j])[:5]]
        results.append(dict(track=name,split=split,training_count=int(train.sum()),test_count=int((~train).sum()),ranked=ranked))
        print(json.dumps(results[-1]),flush=True)
result=dict(qualification='Conditional temporal transfer only: original unseeded Space-Track position/calibration and candidate bank are frozen from the full scan; target definitions were inspected. No held-out localization claim. Satellite identity and its one timing parameter are selected from training observations only, with no satellite-specific exception.',candidate_count=len(full.numbers),timing_domain_s=[-5,5],timing_grid_step_s=.05,timing_prior_sigma_s=2,frequency_sigma_hz=125,elapsed_seconds=time.monotonic()-begun,results=results)
(root/'train_only_candidate_temporal_transfer.json').write_text(json.dumps(result,indent=2)+'\n')
