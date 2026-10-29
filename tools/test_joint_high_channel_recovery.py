"""Bounded alternative-family attachment with frozen covariance-aware tests."""
import argparse
from functools import partial
import hashlib
import itertools
from pathlib import Path
import time

import numpy as np
from debug_fast_graph_unassociated import read,write,screen
from benchmark_graph_covariance import load_case,baseline_pair,support_recovery
from validate_fast_target_guard import target_guard
from provisional_family_recovery import reconstitute
from probe_high_channel_correlated_noise import (calibrate,entries_for_targets,prediction_geometry,
    validation,position_trial)
from correlated_curve_prediction import gaussian,randomized_blocks
from leo.analysis.research.covariance_structure import prepare,evaluate

ARMS=('c0','fitted_c');SEEDS=(20261029,0,1,2,3,4,5,6,7)


def physical(raw,cov,times,owners):
    masks=[randomized_blocks(times,seed=s)[0] for s in SEEDS]
    prepared=prepare(cov,times,owners,masks)
    return evaluate(prepared,raw)


def context(root,case,source):
    d=load_case(root,case);base=baseline_pair(d);d,support,_=support_recovery(d,base)
    current=read(source/'result.json')
    unconstrained=read(source/'unconstrained.json') if current['status']=='accepted' else None
    if target_guard(current,unconstrained):
        k=current['proposal']['row'];sigma=current['selected_sigma_hz']
        d=reconstitute(d,current['policy'],k,sigma,True)
        from probe_ds23_history_calibrated_phase import make_problem
        def factory(*args,**kwargs):
            p=make_problem(*args,**kwargs,support_policy=d['support_policy']);p.constants[:,k]*=sigma/300.;return p
        d['problem_factory']=factory;baseline=current['policy']
    else:baseline=support
    expected=current['policy'] if target_guard(current,unconstrained) else current['support']
    for a in ARMS:
        assert set(baseline[a]['proposed_associated_ids'])==set(expected[a]['proposed_associated_ids'])
        assert np.linalg.norm(np.asarray(baseline[a]['endpoint_east_north_km'])-expected[a]['endpoint_east_north_km'])<1e-5
    d['capture_target_covariance']=True
    return d,baseline


def nominate(d,baseline):
    p,_=d['problems']['c0'];owned=set().union(*(set(r['proposed_associated_ids']) for r in baseline.values()));eligible=[]
    for k,i in enumerate(p.members):
        t=d['scan'].tracks[i]
        if t['channel'] in (7,8) and len(t['times'])>=20 and np.ptp(t['times'])>=24 and not owned.intersection(t['observation_ids']):eligible.append(k)
    pairs=[]
    for left,right in itertools.combinations(eligible,2):
        a,b=[d['scan'].tracks[p.members[k]] for k in (left,right)]
        if a['receiver']==b['receiver'] and a['channel']!=b['channel'] and min(a['times'].max(),b['times'].max())-max(a['times'].min(),b['times'].min())>=20:
            pairs.append(sorted((left,right),key=lambda k:d['scan'].tracks[p.members[k]]['channel']))
    offers=pairs or [[k] for k in eligible]
    return max(offers,key=lambda rows:(sum(len(d['scan'].tracks[p.members[k]]['times']) for k in rows),tuple(-k for k in rows))) if offers else []


def geometry(d,extras,model,arm):
    p,x=d['problems'][arm];fn,view,_,order,_=prediction_geometry(p,[],d['powers'],extras,model)
    _,raw,cov,g=fn(x);owners=np.repeat(np.arange(len(extras)),[e['points'] for e in extras])
    return raw[order],cov[np.ix_(order,order)],view.flat_times[order],owners[order],float(g['elevation'].min())


def old_pass(v):
    return v['noise']['noise_screen_pass'] and all(r['noise_screen_pass'] for r in v.get('per_track_noise',{}).values())


def case(args, *, supplied_context=None):
    start=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    d,baseline=context(args.root,args.case,args.source) if supplied_context is None else supplied_context
    targets=nominate(d,baseline)
    result=dict(case=args.case,status='running',baseline=baseline,variants={},targets=targets)
    write(out/'fallback.json',result)
    if not targets:result.update(status='no_eligible_high_channel',seconds=time.monotonic()-start);write(out/'result.json',result);return
    p,_=d['problems']['c0'];scans=[];nominees={int(p.rows[k]['candidate_norad']) for k in targets};candidates=set(nominees)
    for k in targets:
        t=d['scan'].tracks[p.members[k]];r={}
        for a,(q,x) in d['problems'].items():
            r[a]={name:screen(q,x,t,np.arange(len(t['times'])),full) for name,full in (('active',False),('catalogue',True))}
            candidates.update(v['norad'] for v in r[a].values() if v.get('status')=='screened')
        scans.append(dict(component=t['key'],points=len(t['times']),screens=r))
    # Only families represented in the current prior/design can be attached.
    represented={int(d['scan'].norads[j]) for j in p.labels};unrepresented=sorted(candidates-represented)
    candidates=sorted(candidates&represented)
    write(out/'nomination.json',dict(tracks=scans,candidates=candidates,unrepresented=unrepresented,original_nominees=sorted(nominees)))
    calibration=calibrate(d,targets,sorted(set(candidates)|nominees));write(out/'calibration.json',calibration)
    if len({r['norad'] for r in calibration['rows']})<2:raise ValueError('need two independent covariance-training families')
    entries={j:entries_for_targets(d,targets,j) for j in candidates}
    result.update(target_components=[s['component'] for s in scans],target_points=sum(s['points'] for s in scans))
    for name,model in (('white_existing',calibration['null']),('covariance_existing',calibration['best_correlated']),('covariance_physical',calibration['best_correlated'])):
        scores={j:{a:gaussian(*geometry(d,e,model,a)[:2])['objective'] for a in ARMS} for j,e in entries.items()}
        best={a:min(candidates,key=lambda j:scores[j][a]) for a in ARMS};j=best['c0'];extras=entries[j]
        margin={a:min((s[a] for k,s in scores.items() if k!=j),default=scores[j][a])-scores[j][a] for a in ARMS}
        # Challenge the common-family explanation against independently labeled lanes.
        split=[]
        if len(targets)==2:
            for first,second in itertools.permutations(candidates,2):
                e=[entries[first][0],entries[second][1]]
                split.append(dict(norads=[first,second],scores={a:gaussian(*geometry(d,e,model,a)[:2])['objective']+2*np.log(max(2,len(candidates))) for a in ARMS}))
        split_margin={a:min((s['scores'][a] for s in split),default=scores[j][a])-scores[j][a] for a in ARMS}
        checks={};white_checks={};used=set()
        for seed in SEEDS:
            trial=validation(d,extras,model,seed);key=tuple(trial['c0']['split']['withheld_blocks'])
            if key in used:continue
            used.add(key);checks[str(seed)]=trial;white_checks[str(seed)]=validation(d,extras,calibration['null'],seed)
        phys={a:physical(*geometry(d,extras,model,a)[:4]) for a in ARMS}
        old=all(old_pass(r['held']) and r['joint']['noise']['noise_screen_pass'] for v in checks.values() for r in v.values())
        gains={a:sum(white_checks[s][a]['held']['objective']-v[a]['held']['objective'] for s,v in checks.items()) for a in ARMS}
        physical_bounds=all(geometry(d,extras,model,a)[4]>=0 for a in ARMS)
        identity=all(best[a]==j and margin[a]>=10 and split_margin[a]>=0 for a in ARMS)
        screen_pass=all(r['compatible'] for r in phys.values()) if name=='covariance_physical' else old
        covariance_ok=name=='white_existing' or (calibration['qualified'] and all(v>0 for v in gains.values()))
        valid=identity and physical_bounds and covariance_ok and screen_pass
        # All three diagnostics get the same bounded fit, even when prechecks fail.
        pair=position_trial(d,extras,model)
        final_physical={a:physical(r['target_raw_hz'],r['target_covariance_hz2'],r['target_times_s'],r['target_owners']) for a,r in pair.items()}
        from algo02_scan import pair_passes
        final_existing=all(old_pass(r['target']) for r in pair.values())
        final_screen=all(r['compatible'] for r in final_physical.values()) if name=='covariance_physical' else final_existing
        final_bounds=all(r['target_min_elevation_deg']>=0 and all(abs(v['bias_hz'])<=3000 and v['raw_RMS_after_bias_hz']<=450 for v in r['physical_target_checks']) for r in pair.values())
        preserves=all(set(baseline[a]['proposed_associated_ids'])<=set(pair[a]['proposed_associated_ids']) for a in ARMS)
        accepted=valid and final_screen and final_bounds and pair_passes(pair,include_linear=True) and preserves
        record=dict(candidate=j,identity_pass=identity,common_scores=scores,common_margin=margin,split_challenges=split,split_margin=split_margin,
            model=model,calibration_qualified=calibration['qualified'],checks=checks,held_density_gains=gains,physical=phys,
            existing_screen_pass=old,precheck_pass=valid,final_physical=final_physical,final_existing_pass=final_existing,
            final_original_gates_pass=pair_passes(pair,include_linear=True),preserves_old_points=preserves,
            accepted=accepted,proposal=pair,policy=pair if accepted else baseline,extras=extras)
        write(out/(name+'.json'),record)
        result['variants'][name]=dict(candidate=j,accepted=accepted,identity_pass=identity,precheck_pass=valid,
            old_screen=old,physical_screen=all(r['compatible'] for r in phys.values()),policy=record['policy'])
        print(args.case,name,'accepted',accepted,'identity',identity,'old',old,'physical',all(r['compatible'] for r in phys.values()),flush=True)
    result.update(status='complete',seconds=time.monotonic()-start);write(out/'result.json',result)


def synthetic(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);rng=np.random.default_rng(94721);rows=[]
    for kind in ('white','correlated','interleaved'):
        n=60;t=np.arange(n,dtype=float) if kind!='interleaved' else np.repeat(np.arange(30,dtype=float)*2,2)+np.tile([0,.3],30)
        owners=np.zeros(n,int) if kind!='interleaved' else np.tile([0,1],30)
        cov=80.**2*np.eye(n)
        if kind!='white':cov+=80.**2*np.exp(-abs(t[:,None]-t[None,:])/2)
        cov+=300.**2*(owners[:,None]==owners[None,:])
        masks=[randomized_blocks(t,seed=s)[0] for s in SEEDS];p=prepare(cov,t,owners,masks)
        noise=rng.normal(size=(1000,n))@np.linalg.cholesky(cov).T
        x=(t-t.mean())/np.ptp(t)
        errors={'null':np.zeros(n),'offset':np.ones(n)*1500,'slope':x*1000,'curvature':(x*x-np.mean(x*x))*3000,'step':(x>=0)*700}
        for label,error in errors.items():
            rejected=sum(not evaluate(p,y+error)['compatible'] for y in noise)
            rows.append(dict(geometry=kind,injection=label,trials=len(noise),rejections=rejected,rate=rejected/len(noise),threshold=p['threshold']))
    write(out/'synthetic.json',dict(seed=94721,calibration_seed=82137,alpha=.01,rows=rows,
        source_sha256=hashlib.sha256((Path(__file__).parents[1]/'src/leo/analysis/research/covariance_structure.py').read_bytes()).hexdigest(),
        note='Null and injections evaluated before real-data tests; fixed known covariance, not uncertainty in estimated hyperparameters.'))
    print(rows,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('case','synthetic'))
    for name in ('root','source','output'):p.add_argument('--'+name,type=Path,required=name=='output')
    p.add_argument('--case');a=p.parse_args();case(a) if a.mode=='case' else synthetic(a)
