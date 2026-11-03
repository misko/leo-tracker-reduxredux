"""Retiming and detection-probability controls under the full saved objective."""
import json
from types import SimpleNamespace
import numpy as np
from scipy.optimize import minimize
from search import ROOT,observations
from leo.contracts.regional_position import PositionOrbitBank,PositionObservations,RegionalPrior
from leo.application.shared_orbit_replay import selected_model
from leo.analysis.regional_position_score import circular
from leo.analysis.hard60_score import predict_orbits


def restore():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz')
    ctx=json.loads((ROOT/'context.json').read_text());evidence=json.loads((ROOT/'saved-evidence.json').read_text())
    terminal=evidence['terminal'];prior=RegionalPrior(**ctx['prior'])
    full=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities']);look={int(num):j for j,num in enumerate(full.numbers)}
    bank=full.select([look[num] for num in terminal['candidate_numbers']])
    obs=PositionObservations(tuple(ctx['window_ids']),a['times'],a['measured'],a['rf'],a['receiver'],a['channel'],a['margin'])
    model,fit,audit=selected_model({'all':SimpleNamespace(observations=obs)},bank,prior,
        np.array(evidence['nodes_s']),terminal,evidence['stages'])
    return a,ctx,full,model,fit,audit


def main():
    a,ctx,full,model,fit,audit=restore();shape=json.loads((ROOT/'shape-controls.json').read_text())
    groups=[g for g in shape['groups'] if g['part']==0];v,n=(np.array(fit[k]) for k in ['vector','nuisance'])
    nums=list(model.bank.numbers);tau=v[7]+model.basis@v[8:];look={int(num):j for j,num in enumerate(full.numbers)}
    primary=[66544,60127,67704];profiles=[]
    for group,num in zip(groups,primary):
        rows=np.array(group['rows']);obs=observations(a,ctx,rows);one=full.select([look[num]])
        y=a['measured'][rows]-a['correction'][rows]
        arms={'fitted-c':y,'zero-c-fixed':y+v[6]*(a['rf'][rows]-ctx['rf_center_hz'])/1e9}
        masks={'all':np.ones(len(rows),bool),'early_to_late':obs.times_s<=np.median(obs.times_s),'late_to_early':obs.times_s>np.median(obs.times_s)}
        best={(arm,split):(float('inf'),None) for arm in arms for split in masks}
        for shift in np.linspace(-5,5,401):
            pred,visible,_,_=predict_orbits(one,obs,model.prior,v[:2],np.array([shift]),derivatives=False)
            for arm,yy in arms.items():
                r=circular(yy-pred[:,0])
                for split,mask in masks.items():
                    score=float(np.sum((r[mask]/125)**2)+(shift/2)**2)
                    if visible[mask].all() and score<best[arm,split][0]:
                        best[arm,split]=(score,dict(timing_s=float(shift),training_rms_hz=float(np.sqrt(np.mean(r[mask]**2))),
                            test_rms_hz=float(np.sqrt(np.mean(r[~mask]**2))) if (~mask).any() else None))
        profiles.append(dict(group=group['group'],satellite=num,rows=rows.tolist(),count=len(rows),
            saved_timing_s=float(tau[nums.index(num)]),arms={arm:{split:best[arm,split][1] for split in masks} for arm in arms}))
    def vector(changes):
        target=tau.copy()
        for num,value in changes.items():target[nums.index(num)]=value
        vv=v.copy();vv[7]=target.mean();vv[8:]=model.basis.T@(target-vv[7])
        np.testing.assert_allclose(vv[7]+model.basis@vv[8:],target,atol=1e-12,rtol=0)
        return vv
    def record(label,vv,nn):
        ev,details=model.evaluate_details(vv,nn);terms=ev[3];best=terms.responsibilities.argmax(axis=1)
        assoc=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
        records=[]
        for group,num in zip(groups,primary):
            rows=np.array(group['rows']);k=nums.index(num)
            records.append(dict(group=group['group'],satellite=num,count=len(rows),
                associated=int(assoc[rows].sum()),intended_associated=int(np.sum(assoc[rows]&(best[rows]==k))),
                detection_probability=float(details['detection_probability'][k]),
                mean_candidate_posterior=float(terms.responsibilities[rows,k].mean())))
        return dict(label=label,objective=float(ev[0]),NLL=float(terms.nll),associated=int(assoc.sum()),groups=records)
    changes={p['satellite']:p['arms']['fitted-c']['all']['timing_s'] for p in profiles}
    trials=[record('baseline',v,n)]
    for num in primary:trials.append(record('retime_'+str(num),vector({num:changes[num]}),n))
    vv=vector(changes);trials.append(record('retime_all_three',vv,n))
    start=model.base_nuisance_count
    def objective(tail):
        nn=n.copy();nn[start:]=tail;e=model.evaluate_joint(vv,nn)
        return e[0],e[2][start:]
    limits=model.group_limits[model.original.group_count:]
    solved=minimize(objective,n[start:],jac=True,method='L-BFGS-B',bounds=list(zip(-limits,limits)),
        options={'maxiter':150,'gtol':1e-7,'ftol':1e-12,'maxls':30})
    nn=n.copy();nn[start:]=solved.x
    trials.append(record('retime_all_then_q_only',vv,nn))
    result=dict(profiles=profiles,trials=trials,q_fit=dict(success=bool(solved.success),message=str(solved.message),iterations=int(solved.nit)),
        qualification='Target-informed full-objective diagnostics at unchanged position/calibration. '
        'No new candidate or per-track frequency offset. Timing profiles use each training half '
        'for temporal tests; target membership and calibration are full-scan derived. Retiming '
        'trials are not new accepted full endpoints. Final q-only optimization updates the existing '
        'bounded detection-probability coefficients using all observations, keeping frequencies '
        'and receiver calibration fixed; classification changes are not identity truth or position accuracy.')
    (ROOT/'timing-trials.json').write_text(json.dumps(result,indent=2)+'\n')
    np.savez_compressed(ROOT/'trial-endpoint.npz',vector=vv,nuisance=nn)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
