"""Sigma1 own-arm timing-branch probe; no reference/cross-arm inference seeds."""
import json,time,importlib.util
from pathlib import Path
from dataclasses import replace
import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
SPEC=importlib.util.spec_from_file_location('timing_probe_loader',REPORTS/'2026_10_07_sigma1_root_cause/oracle.py')
loader=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(loader)
controls=loader.CONTROLS
OPTIONS=('control','individual-collapse','all-relative-zero','timing-grid')

def run(case):
    from leo.analysis.regional_position_score import PositionObjective,coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    begun=time.monotonic();target=HERE/(case+'.json')
    if target.exists():raise FileExistsError(target)
    doc,old,obs,prior,bank,checkpoint,prefix=loader.load(case)
    prior_receipt=json.loads((REPORTS/'2026_10_07_sigma1_cones'/case/'polished.json').read_text())
    prior_pool=[r for r in prior_receipt['candidates'] if r['option']=='control' and r['feasible']]
    # Predeclared basin selection uses fitted-control objective only, not reference.
    basin=min((r for r in prior_pool if r['arm']=='fitted-c'),key=lambda r:r['selection_score'])['basin']
    region=prior_receipt['basins'][basin];center=np.array(region['center']);radius=region['radius_km']
    cal=checkpoint.get(prefix+':'+basin+':calibration')['result']
    assoc=checkpoint.get(prefix+':'+basin+':association')['result']
    subset=bank.select(assoc['selected_indices'])
    objective=PositionObjective(obs,subset,prior,replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
    score_penalty=next(r['calibration_penalty'] for r in prior_pool if r['basin']==basin)
    seeds={arm:min((r for r in prior_pool if r['arm']==arm and r['basin']==basin),key=lambda r:r['selection_score']) for arm in controls.ARMS}
    timing_min=max(-20.,subset.nodes_s[0]-obs.times_s.min());timing_max=min(20.,subset.nodes_s[-1]-obs.times_s.max())
    out=dict(case=case,session_id=old['session_id'],protocol_sha256=controls.digest_bytes(Path(__file__).read_bytes()),source_receipt_sha256=controls.digest_bytes((REPORTS/'2026_10_07_sigma1_cones'/case/'polished.json').read_bytes()),relative_sigma_s=1.,input_sha256=doc['input_manifest_sha256'],analysis_sha256=doc['analysis_manifest_sha256'],evidence_sha256=doc['evidence_sha256'],basin=basin,basin_selection='minimum prior full-control fitted-c score, conditional only',center=center,radius_km=radius,satellite_numbers=subset.numbers,baseline_sha256=controls.vector_digest(cal['receiver_baseline_hz']),seconds_per_option_arm=16.,options=OPTIONS,runs=[],candidates=[],selections=[],status='running')
    def record(vector,arm,origin,**extra):
        value,g,t=objective.evaluate(vector);mass=float(t.responsibilities.sum())
        return dict(arm=arm,basin=basin,origin=origin,vector=vector,objective=value,selection_score=value+score_penalty,data_nll=t.nll,timing_penalty=value-t.nll,calibration_penalty=score_penalty,signal_fraction=mass/len(obs.window_ids),posterior_rms_hz=float(np.sqrt(np.sum(t.responsibilities*t.residual_hz**2)/mass)),**controls.audit(vector,g,objective.basis,arm,prior.radius_km,center,radius,timing_min,timing_max),**extra)
    def save():target.with_suffix('.progress.json').write_text(json.dumps(out,default=controls.encode,indent=2))
    for option in OPTIONS:
        for arm in controls.ARMS:
            seed=np.asarray(seeds[arm]['vector']).copy();seed_digest=controls.vector_digest(seed)
            value=objective.evaluate(seed)[0];assert abs(value-seeds[arm]['objective'])<1e-6
            start_time=time.monotonic();deadline=start_time+16;interventions=[]
            if option=='all-relative-zero':seed[8:]=0
            elif option=='individual-collapse':
                for j,number in enumerate(subset.numbers):
                    if time.monotonic()>deadline-.1:break
                    trial=controls.timing_trial(seed,objective.basis,j);trial_value=objective.evaluate(trial)[0]
                    accepted=trial_value<value-1e-8
                    interventions.append(dict(number=int(number),before=value,trial=trial_value,accepted=accepted))
                    if accepted:seed=trial;value=trial_value
            elif option=='timing-grid':
                for j,number in enumerate(subset.numbers):
                    original_shifts=seed[7]+objective.basis@seed[8:]
                    best_value,best_vector=value,seed
                    for delta in (-4.,-2.,-1.,1.,2.,4.):
                        if time.monotonic()>deadline-.2:break
                        shifts=original_shifts.copy();shifts[j]=np.clip(shifts[j]+delta,timing_min+1e-9,timing_max-1e-9)
                        trial=seed.copy();trial[7]=shifts.mean();trial[8:]=objective.basis.T@shifts
                        if abs(trial[7])>10:continue
                        trial_value=objective.evaluate(trial)[0]
                        accepted=trial_value<best_value-1e-8
                        interventions.append(dict(number=int(number),delta_s=delta,before=value,trial=trial_value,accepted=accepted))
                        if accepted:best_value,best_vector=trial_value,trial
                    seed,value=best_vector,best_value
                    if time.monotonic()>deadline-.2:break
            out['candidates'].append(record(seed,arm,'proposal',option=option))
            remaining=deadline-time.monotonic()
            fit=fit_position(objective,seed,rf_arm=arm,maximum_seconds=max(.001,remaining),maximum_iterations=600,local_center=center,local_radius_km=radius)
            row=record(fit.vector,arm,'fit',option=option,stop_reason=fit.stop_reason,elapsed_s=fit.elapsed_s,evaluations=fit.evaluations)
            assert abs(row['objective']-fit.objective)<1e-6
            assert abs(row['stationarity']-fit.stationarity)<1e-5
            out['candidates'].append(row)
            out['runs'].append(dict(option=option,arm=arm,seed_sha256=seed_digest,fit_budget_s=remaining,total_elapsed_s=time.monotonic()-start_time,interventions=interventions,result=row))
            print(case,option,arm,round(row['selection_score'],3),row['converged'],row['stop_reason'],flush=True);save()
    # Retain every incumbent for score selection; reference is read only afterwards.
    for option in OPTIONS:
        for arm in controls.ARMS:
            pool=[dict(r,option=option,origin='prior-incumbent') for r in prior_pool if r['arm']==arm]
            pool += [r for r in out['candidates'] if r['option']==option and r['arm']==arm and r['feasible']]
            selected=min(pool,key=lambda r:r['selection_score']);out['selections'].append(selected)
    for row in out['candidates']+out['selections']:
        lat,lon=np.radians(coordinates(prior,np.asarray(row['vector'])[:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    out.update(status='complete',elapsed_s=time.monotonic()-begun);save();target.write_text(json.dumps(out,default=controls.encode,indent=2))

if __name__=='__main__':
    for case in ('1939','2139'):run(case)
