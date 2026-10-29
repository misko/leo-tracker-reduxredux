"""Controlled full-position inclusion of an independently annotated new family."""
import argparse
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from diagnose_all_large_tracks import context
from debug_fast_graph_unassociated import read,write,memberships
from leo.analysis.research.grouped_prediction import identity_consensus
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from algo02_scan import pair_passes
from predictive_new_family import NewFamily


def run(args):
    began=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);d=context(inv);p0,_=d['problems']['c0']
    targets=[];used={o for entry in d['entries'] for o in entry['observation_ids']}
    used.update(o for i,sl in zip(p0.members,p0.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],d['keep'][sl],strict=True) if k)
    for folder in args.validation:
        r=read(folder/'result.json');a=identity_consensus(r['folds'],score_name='conditional_target')
        if a['status']!='conditionally_supported_identity':raise ValueError('identity not supported under supplied validation')
        t=next(t for t in inv['tracks'] if t['track_id']==r['track_id']);track=d['scan'].tracks[t['track_index']]
        j=int(np.flatnonzero(d['scan'].norads==a['norad'])[0])
        if j in p0.labels:raise ValueError('use existing-family inclusion for an existing label')
        aliases={q['alias'] for f in r['folds'] for q in f['proposals'] if q['norad']==a['norad']}
        if len(aliases)!=1:raise ValueError('alias not stable across randomized partitions')
        if used.intersection(track['observation_ids']):raise ValueError('target duplicates retained observations')
        used.update(track['observation_ids'])
        targets.append(dict(track_index=t['track_index'],component=track['key'],candidate_index=j,norad=a['norad'],alias=next(iter(aliases)),points=len(track['times']),observation_ids=track['observation_ids']))
    family=NewFamily(d['scan'],targets,d['model'],phase_step=args.phase_step)
    write(out/'protocol.json',dict(job=inv['job'],targets=targets,validation=[str(p) for p in args.validation],family_prior=family.receipt,
        optimizer='L-BFGS-B normalized joint objective',maxiter=48,maxfun=240,phase_rounds=5,start=[0,0],box_width_km=25,
        control_uses_same_optimizer=True,c0_vs_fitted_c=True,GPS_used=False,future_TLE=False,phase_step_s=args.phase_step))
    for variant,include in [('control',False),('new_family',True)]:
        pair={}
        for arm in ('c0','fitted_c'):
            x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                def objective(z):
                    c=p.calculate(z);penalty=float(np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)
                    return c['negative_twice_elbo']+penalty+(family.evaluate(p,z,d['powers'],d['entries']) if include else 0.)
                opt=minimize(objective,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
                    options=dict(maxiter=48,maxfun=240,eps=.001,ftol=1e-10,gtol=1e-4,maxls=20))
                x=np.asarray(opt.x);phase=np.clip(p.state(x)['phases'][p.labels],-15,15);delta=float(np.max(abs(phase-reference)));reference=phase
                history.append(dict(endpoint_east_north_km=x,objective=float(opt.fun),success=bool(opt.success),message=str(opt.message),nfev=opt.nfev,phase_change_s=delta))
            row=summary(p,x,d['entries']);_,_,ids,_=memberships(p,x,d['entries']);old=set(inv['policy'][arm]['proposed_associated_ids'])
            if include:
                detail=family.evaluate(p,x,d['powers'],d['entries'],details=True);row['family']=detail
                row['incumbent_objective']=row['negative_twice_elbo'];row['negative_twice_elbo']+=detail['negative_twice_log_density']
                row['linear_gates']+=detail['gates'];ids.update(o for e in targets for o in e['observation_ids'])
            row.update(history=history,final_phase_change_s=delta,proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids))
            pair[arm]=row
            print(inv['job']['label'],variant,arm,'endpoint',x,'seconds',round(time.monotonic()-began,1),flush=True)
        valid=pair_passes(pair,include_linear=True) and all(v['lost_points']==0 and v['history'][-1]['success'] for v in pair.values())
        if include:valid=valid and all(v['family']['phase_boundary_mass']<.01 for v in pair.values())
        write(out/(variant+'.json'),dict(job=inv['job'],arms=pair,baseline=inv['policy'],paired_valid=valid,target_entries=targets if include else [],
            no_production_change=True,receiver_calibration_from_target=False,shared_predictive_uncertainty=True,seconds=time.monotonic()-began))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['inventory','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--validation',type=Path,nargs='+',required=True);p.add_argument('--phase-step',type=float,default=.1);run(p.parse_args())
