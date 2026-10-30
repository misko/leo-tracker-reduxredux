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
from predictive_new_family import NewFamily,resolution_audit
from phase_reference_checks import phase_refresh


def run(args):
    began=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);d=context(inv);p0,_=d['problems']['c0']
    original_graph_count=len(d['scan'].tracks)
    targets=[];inactive_sources=[];used={o for entry in d['entries'] for o in entry['observation_ids']}
    used.update(o for i,sl in zip(p0.members,p0.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],d['keep'][sl],strict=True) if k)
    for folder in args.validation:
        r=read(folder/'result.json');a=identity_consensus(r['folds'],score_name='conditional_target')
        if a['status']!='conditionally_supported_identity':raise ValueError('identity not supported under supplied validation')
        if r.get('inactive_graph_fragment'):
            from inactive_graph_fragment import validated_inactive_context
            d,t=validated_inactive_context(d,inv,folder);inactive_sources.append(str(folder))
        else:t=next(t for t in inv['tracks'] if t['track_id']==r['track_id'])
        track=d['scan'].tracks[t['track_index']]
        j=int(np.flatnonzero(d['scan'].norads==a['norad'])[0])
        if j in p0.labels:
            if not args.uncalibrated_label:raise ValueError('use existing-family inclusion for an existing label')
            if any(row['candidate_index']==j and d['keep'][sl].any() for row,sl in zip(p0.rows,p0.slices,strict=True)):
                raise ValueError('target family has active calibration observations')
        if any(e['candidate_index']==j for e in d['entries']):raise ValueError('target family already has predictive observations; shared conditioning required')
        aliases={q['alias'] for f in r['folds'] for q in f['proposals'] if q['norad']==a['norad']}
        if len(aliases)!=1:raise ValueError('alias not stable across randomized partitions')
        if used.intersection(track['observation_ids']):raise ValueError('target duplicates retained observations')
        used.update(track['observation_ids'])
        targets.append(dict(track_index=t['track_index'],component=track['key'],candidate_index=j,norad=a['norad'],alias=next(iter(aliases)),points=len(track['times']),observation_ids=track['observation_ids']))
    family=NewFamily(d['scan'],targets,d['model'],phase_step=args.phase_step,allow_uncalibrated_label=args.uncalibrated_label,
        integrate_orbit_uncertainty=not args.omit_orbit_uncertainty,integrate_receiver_uncertainty=not args.omit_receiver_uncertainty)
    write(out/'protocol.json',dict(job=inv['job'],targets=targets,validation=[str(p) for p in args.validation],family_prior=family.receipt,
        inactive_fragment_sources=inactive_sources,
        original_graph_count=original_graph_count,
        optimizer=args.optimizer+' normalized joint objective',maxiter=48,maxfun=240,phase_rounds=5,start=[0,0],box_width_km=25,
        control_uses_same_optimizer=True,c0_vs_fitted_c=True,GPS_used=False,future_TLE=False,phase_step_s=args.phase_step,
        uncalibrated_label=args.uncalibrated_label,phase_resolution_audit=not args.skip_phase_audit,
        postfit_audit_evaluations_per_arm=0 if args.skip_phase_audit else 15))
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
                if args.optimizer=='lbfgsb':
                    opt=minimize(objective,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
                        options=dict(maxiter=48,maxfun=240,eps=.001,ftol=1e-10,gtol=1e-4,maxls=20))
                else:
                    opt=minimize(objective,x,method='Powell',bounds=[(-12.5,12.5)]*2,
                        options=dict(maxiter=48,maxfev=240,ftol=1e-10,xtol=1e-5))
                x=np.asarray(opt.x);phase,check=phase_refresh(p.state(x)['phases'][p.labels],reference);delta=check['phase_change_s'];reference=phase
                history.append(dict(endpoint_east_north_km=x,objective=float(opt.fun),success=bool(opt.success),message=str(opt.message),nfev=opt.nfev,**check))
            from inactive_graph_fragment import original_graph_view
            row=summary(p,x,d['entries']);_,_,ids,_=memberships(original_graph_view(p,original_graph_count),x,d['entries']);old=set(inv['policy'][arm]['proposed_associated_ids'])
            if include:
                detail=family.evaluate(p,x,d['powers'],d['entries'],details=True);row['family']=detail
                row['incumbent_objective']=row['negative_twice_elbo'];row['negative_twice_elbo']+=detail['negative_twice_log_density']
                row['linear_gates']+=detail['gates'];ids.update(o for e in targets for o in e['observation_ids'])
                if not args.skip_phase_audit:
                    row['phase_resolution_audit']=resolution_audit(family,p,x,d['powers'],d['entries'],d['model'])
            row.update(history=history,final_phase_change_s=delta,proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids))
            pair[arm]=row
            print(inv['job']['label'],variant,arm,'endpoint',x,'seconds',round(time.monotonic()-began,1),flush=True)
        valid=pair_passes(pair,include_linear=True) and all(v['lost_points']==0 and v['history'][-1]['success'] and v['final_phase_change_s']<=.01 for v in pair.values())
        if include:valid=valid and all(v['family']['phase_boundary_mass']<.01 for v in pair.values())
        if include and not args.skip_phase_audit:valid=valid and all(v['phase_resolution_audit']['local_agreement'] for v in pair.values())
        write(out/(variant+'.json'),dict(job=inv['job'],arms=pair,baseline=inv['policy'],paired_valid=valid,target_entries=targets if include else [],
            no_production_change=True,receiver_calibration_from_target=False,shared_predictive_uncertainty=True,
            phase_resolution_checked=bool(include and not args.skip_phase_audit),seconds=time.monotonic()-began))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['inventory','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--validation',type=Path,nargs='+',required=True);p.add_argument('--phase-step',type=float,default=.1)
    p.add_argument('--uncalibrated-label',action='store_true')
    p.add_argument('--omit-orbit-uncertainty',action='store_true',help='Diagnostic ablation only; removes physical mode covariance')
    p.add_argument('--omit-receiver-uncertainty',action='store_true',help='Diagnostic ablation only; keeps conditional receiver mean, removes its covariance')
    p.add_argument('--skip-phase-audit',action='store_true',help='Historical replay only; results lack the numerical inclusion guard')
    p.add_argument('--optimizer',choices=['lbfgsb','powell'],default='lbfgsb');run(p.parse_args())
