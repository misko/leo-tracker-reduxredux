"""Training-only catalogue nomination and joint grouped prediction of a curve.

Conditional on the frozen graph and incumbent identities; no GPS selection.
Predictive/linear tracks are excluded from training in this first prototype.
"""
import argparse
import copy
from pathlib import Path
import time
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context,PHASES,ARMS
from leo.analysis.research.grouped_prediction import grouped_split,predictive_score
from leo.analysis.research.track_recovery_diagnostics import shortlist,profile_rate
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from prototype_dsx01_continuous_position import latlon

SEEDS=(20261029,94721,4081)


def prior_means(d,node):
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    p,_=d['problems']['c0'];old=dict(zip(p.labels,d['means'],strict=True))
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']});new=[j for j in labels if j not in old]
    receipts=[]
    if new:
        _,receipts=phase_widths(d['scan'],new)
        old.update(zip(new,forecast_phase_mean(receipts,d['model']['shrinkage']),strict=True))
    return np.array([old[j] for j in labels]),receipts


def training_factory(d,orbital_policy=None,target_family=None):
    from probe_ds23_history_calibrated_phase import make_problem
    def factory(*args,**kwargs):
        p=d.get('problem_factory',make_problem)(*args,**kwargs)
        if orbital_policy is not None and (orbital_policy!='target_uncertainty' or target_family is not None):
            constants=p.constants.copy()
            config=({'support_policy':d['support_policy'],'extra_orbital_families':[target_family]}
                    if orbital_policy=='target_uncertainty' else {'support_policy':orbital_policy})
            p=make_problem(*args,**kwargs,**config)
            p.constants[:]=constants
        # Fixed predeclared noise; no full-data BIC noise selection or RF-derived
        # family confidence weights can leak a withheld point into this fit.
        p.point_noise=np.full(len(p.values),150.)
        return p
    return factory


def fit_training(d,node,keep,arm,*,start=(0.,0.),predictive=False,orbital_policy=None,target_family=None,events=None):
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_frequency_events import cached
    from investigate_dsx01_localization_failures import fit
    means,receipts=prior_means(d,node);reference=np.zeros(len(means));x=np.asarray(start,float);history=[]
    factory=training_factory(d,orbital_policy,target_family)
    powers=np.ones(len(d['powers']))
    for epoch in range(5):
        p=make_event_problem(d['scan'],node,keep,arm,reference,powers,means,d['model'],events or [],base_problem_factory=factory)
        if predictive:attach_event_predictive(p,d['entries'],powers)
        cached(p);f=fit(p,x,iterations=48);x=np.asarray(f['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        delta=float(np.max(abs(phase-reference)));history.append(dict(endpoint=x,phase_change_s=delta));reference=phase
    return p,x,dict(history=history,new_prior_receipts=receipts,training_objective=p.calculate(x)['negative_twice_elbo'],
                    final_phase_change_s=delta,endpoint_east_north_km=x)


def corrected(p,x,i):
    t=p.scan.tracks[i];s=p.state(x)
    return t['values']-p.scan.hardware(t,s['beta'])-t['rf_hz']/11.5e9*p.scan.rx_basis[i]@s['smooth'][t['receiver']-1]


def nominate(d,base,target_index,target_train,max_candidates):
    track=d['scan'].tracks[target_index];available=np.flatnonzero(target_train)
    pick=available[np.unique(np.linspace(0,len(available)-1,min(16,len(available))).astype(int))]
    times=track['times'][pick];positions={'center':np.zeros(2)}
    for a,(_,x,_) in base.items():positions['trained_'+a]=x
    for e in (-10.,0.,10.):
        for n in (-10.,0.,10.):positions[f'{e}_{n}']=np.array([e,n])
    ys={a:corrected(p,x,target_index)[pick] for a,(p,x,_) in base.items()};offers=[]
    for name,x in positions.items():
        ff=[];ee=[]
        for phi in PHASES:
            f,e=phase_frequency_grid(d['scan'].sky,times,*latlon(x),phase_seconds=phi);ff.append(f);ee.append(e)
        for arm in ARMS:
            for q in shortlist(ys[arm],times,track['rf_hz']/11.5e9,np.array(ff),np.array(ee),times,PHASES,top=3):
                offers.append(dict(q,position=x,arm=arm))
    offers.sort(key=lambda q:q['cost']);selected={}
    for offer in offers:
        selected.setdefault(offer['candidate_index'],offer)
        if len(selected)>=max_candidates:break
    return list(selected.values()),dict(training_indices=pick,offers=offers,nomination_uses_held_points=False)


def held_scores(p,x,held,target_slice,old_mask):
    c=p.calculate(x);f=c['features'];g=p.noise_groups
    w=c['noise_precision'][g[p.keep]]/p.point_noise[p.keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+f[p.keep].T@(f[p.keep]*w[:,None])
    target=np.zeros(len(held),bool);target[target_slice]=True
    scores={}
    precision=np.where(c['noise_precision']>1e-12,c['noise_precision'],1.)
    for name,mask in [('target',held&target),('existing',held&old_mask&~target),('joint',held&(old_mask|target))]:
        if not mask.any():raise ValueError('empty held evaluation group')
        sigma=p.point_noise[mask]/np.sqrt(precision[g[mask]])
        scores[name]=predictive_score(c['conditional_residual_hz'][mask],f[mask],gram,sigma)
    scores['per_existing_track']=[]
    for row,sl in zip(p.rows,p.slices):
        ix=np.arange(sl.start,sl.stop);ix=ix[held[ix]&old_mask[ix]]
        if not len(ix):continue
        q=predictive_score(c['conditional_residual_hz'][ix],f[ix],gram,p.point_noise[ix]/np.sqrt(precision[g[ix]]))
        scores['per_existing_track'].append(dict(component=row['component'],norad=row['candidate_norad'],**q))
    scores['target_training_noise_precision']=float(c['noise_precision'][g[target_slice.start]])
    return scores


def run(args):
    started=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    inv=read(args.inventory);d=context(inv);p0,_=d['problems']['c0']
    eligible={r['track_id']:r for r in inv['tracks'] if r['current_large'] and r['track_index'] in p0.members}
    if args.track:target=eligible[args.track]
    else:target=max(eligible.values(),key=lambda r:len(r['observation_ids']))
    k=p0.members.index(target['track_index']);sl=p0.slices[k];track=d['scan'].tracks[target['track_index']]
    from annotation_partition_plan import selected_seeds
    seeds,partition_plan=selected_seeds(getattr(args,'partition_audit',None),target['track_id'],p0.flat_times,track['times'],SEEDS,
        distinct=getattr(args,'distinct_partitions',False))
    write(out/'protocol.json',dict(job=inv['job'],target=target,seed_list=seeds[:args.folds],partition_plan=partition_plan,block_s=12,guard_s=2,
        common_scan_wide_split=True,fixed_noise_hz=150,RF_family_weights='all one',phase_rounds=5,steps=48,
        GPS_used=False,future_TLE=False,conditional_on_frozen_graph_and_incumbent_identities=True,
        predictive_linear_rows_in_training=False,nomination='training-only full causal bank; shared candidate union across c arms',
        candidate_limit=args.candidates,incumbent_nominee_always_added=True,
        position_uncertainty_integrated=False,learned_noise_uncertainty_integrated=False))
    all_results=[]
    for seed in seeds[:args.folds]:
        if len(np.unique(np.floor(np.asarray(track['times'])/12)))<3:
            write(out/f'seed-{seed}.json',dict(status='insufficient_group_support',
                reason='fewer than three 12-second target blocks',seed=seed))
            continue
        train,held,split=grouped_split(p0.flat_times,track['times'],seed=seed)
        if train[sl].sum()<8 or held[sl].sum()<4:
            write(out/f'seed-{seed}.json',dict(status='insufficient_group_support',split=split));continue
        keep=d['keep']&train;keep[sl]=False
        base={a:fit_training(d,d['node'],keep,a,orbital_policy=args.orbital_policy) for a in ARMS}
        offers,receipt=nominate(d,base,target['track_index'],train[sl],args.candidates)
        original=p0.rows[k]['candidate_index']
        if original not in {q['candidate_index'] for q in offers}:
            offers.append(dict(candidate_index=original,phase_s=0.,position=[0.,0.],arm='original',cost=None))
        write(out/f'nominations-{seed}.json',dict(split=split,nomination=receipt,selected=offers,
            baseline_training={a:r for a,(_,_,r) in base.items()}))
        proposals=[]
        for offer in offers:
            node=copy.deepcopy(d['node']);j=offer['candidate_index'];norad=int(d['scan'].norads[j])
            # Alias is inferred from training target points and the training-only
            # receiver fit, then held fixed and matched across c arms.
            bank={field:d['scan'].sky[field][[j]] for field in ('position_km','velocity_km_s')};bank['time_s']=d['scan'].sky['time_s']
            tt=track['times'][train[sl]];f,_=paired_phase_frequency(bank,tt,np.zeros(len(tt),int),np.array([offer['phase_s']]),*latlon(offer['position']))
            p,x,_=base['c0'];y=corrected(p,x,target['track_index'])[train[sl]]
            alias=int(profile_rate(y,track['rf_hz']/11.5e9*f,tt)['alias'][0])
            node['seed']['rows'][k].update(candidate_index=j,candidate_norad=norad);node['aliases'][k]=alias
            use=keep.copy();use[sl]=train[sl];arms={}
            for arm in ARMS:
                p,x,meta=fit_training(d,node,use,arm,orbital_policy=args.orbital_policy,target_family=j)
                scores=held_scores(p,x,held,sl,d['keep'])
                minimum_elevation=float(p.conditional_frequency(x)[1][sl].min())
                arms[arm]=dict(**meta,scores=scores,minimum_target_elevation_deg=minimum_elevation)
            proposal=dict(candidate_index=j,norad=norad,alias=alias,arms=arms)
            proposals.append(proposal);write(out/f'{seed}-{norad}.json',proposal)
            print(inv['job']['label'],seed,norad,[(a,round(v['scores']['joint']['negative_twice_log_density'],1),round(v['scores']['target']['rms_hz'],1)) for a,v in arms.items()],flush=True)
        result=dict(seed=seed,split=split,proposals=proposals);all_results.append(result);write(out/f'seed-{seed}.json',result)
    write(out/'result.json',dict(job=inv['job'],component=track['key'],track_id=target['track_id'],folds=all_results,
        seconds=time.monotonic()-started,annotation_prototype=True,no_accepted_associations=True,
        geometry_only_early_exit=bool(partition_plan and partition_plan.get('geometry_only_early_exit'))))


def full(args):
    from leo.analysis.research.grouped_prediction import identity_consensus
    from investigate_ds23_0268_remaining_tracks import family_frequency
    from probe_ds23_frequency_events import summary
    from debug_fast_graph_unassociated import memberships
    from algo02_scan import pair_passes
    inv=read(args.inventory);validation=read(args.validation/'result.json');annotation=identity_consensus(validation['folds'])
    args.output.mkdir(parents=True,exist_ok=False);write(args.output/'annotation.json',annotation)
    if annotation['status']!='conditionally_supported_identity':return
    d=context(inv);p0,x0=d['problems']['c0'];node=copy.deepcopy(d['node']);keep=d['keep'].copy()
    k=next(k for k,r in enumerate(p0.rows) if r['component']==validation['component']);i=p0.members[k];t=d['scan'].tracks[i]
    j=int(np.flatnonzero(d['scan'].norads==annotation['norad'])[0]);f,_=family_frequency(p0,x0,j,times=t['times'])
    alias=int(profile_rate(corrected(p0,x0,i),t['rf_hz']/11.5e9*f,t['times'])['alias'][0])
    node['seed']['rows'][k].update(candidate_index=j,candidate_norad=annotation['norad']);node['aliases'][k]=alias;keep[p0.slices[k]]=True
    for predictive in (False,True):
        pair={}
        for arm in ARMS:
            p,x,meta=fit_training(d,node,keep,arm,predictive=predictive,orbital_policy=args.orbital_policy,target_family=j)
            entries=d['entries'] if predictive else [];r=summary(p,x,entries);_,_,ids,_=memberships(p,x,entries)
            old=set(inv['policy'][arm]['proposed_associated_ids'])
            r.update(meta,proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids),
                     targets=[g for g in r['gates']['tracks'] if g['component']==validation['component']],
                     failed_existing=[g['component'] for g in r['gates']['tracks'] if not g['compatible'] and g['component']!=validation['component']])
            pair[arm]=r
        qualified=pair_passes(pair,include_linear=True) and all(r['lost_points']==0 for r in pair.values())
        name='with_predictive' if predictive else 'curved_only'
        write(args.output/(name+'.json'),dict(job=inv['job'],annotation=annotation,arms=pair,baseline=inv['policy'],
            paired_valid=qualified,predictive_rows_in_fit=predictive,no_production_change=True,alias=alias,orbital_policy=args.orbital_policy))
        print(inv['job']['label'],name,qualified,[(a,r['added_points'],r['lost_points'],r['RMS_hz']) for a,r in pair.items()],flush=True)


def controls(args):
    from probe_ds23_frequency_events import summary
    from debug_fast_graph_unassociated import memberships
    from algo02_scan import pair_passes
    inv=read(args.inventory);d=context(inv);args.output.mkdir(parents=True,exist_ok=False)
    for predictive in (False,True):
        pair={}
        for arm in ARMS:
            p,x,meta=fit_training(d,d['node'],d['keep'],arm,predictive=predictive,orbital_policy=args.orbital_policy)
            entries=d['entries'] if predictive else [];r=summary(p,x,entries);_,_,ids,_=memberships(p,x,entries)
            old=set(inv['policy'][arm]['proposed_associated_ids'])
            r.update(meta,proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids))
            pair[arm]=r
        name='with_predictive' if predictive else 'curved_only'
        write(args.output/(name+'.json'),dict(job=inv['job'],arms=pair,baseline=inv['policy'],
            paired_valid=pair_passes(pair,include_linear=True) and all(r['lost_points']==0 for r in pair.values()),
            matched_no_target_control=True,predictive_rows_in_fit=predictive,orbital_policy=args.orbital_policy))
        print(inv['job']['label'],'control',name,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--track');p.add_argument('--candidates',type=int,default=3);p.add_argument('--folds',type=int,default=3)
    p.add_argument('--validation',type=Path)
    p.add_argument('--partition-audit',type=Path)
    p.add_argument('--distinct-partitions',action='store_true',help='Select three distinct target holdouts by timestamps; skip RF fits if unavailable')
    p.add_argument('--control',action='store_true')
    p.add_argument('--orbital-policy',choices=['active_uncertainty','target_uncertainty'])
    a=p.parse_args();controls(a) if a.control else full(a) if a.validation else run(a)
