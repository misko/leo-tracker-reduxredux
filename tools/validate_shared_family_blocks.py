"""Matched random-block sensitivity of an existing-family predictive update.

Frozen graph/identities are conditioning assumptions. This is not independent
identity validation and does not propose accepted associations.
"""
import argparse
import hashlib
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context
from annotate_track_predictively import training_factory
from grouped_predictive_scan import predictive_training_views
from ds23_frequency_events import make_event_problem, attach_event_predictive
from conditional_satellite_refresh import attach_conditional_satellite_refresh
from probe_ds23_frequency_events import cached
from investigate_dsx01_localization_failures import fit
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.retained_track_likelihood import PERIOD
from phase_reference_checks import phase_refresh, reference_domain
from prototype_dsx01_continuous_position import latlon
from stress_joint_attachment import supervise


def held_prediction(raw, train, held, sigma=150*np.sqrt(2), bias_sigma=300.):
    """Only training values estimate the new fragment's regularized constant."""
    raw=np.asarray(raw,float);train=np.asarray(train,bool);held=np.asarray(held,bool)
    if raw.shape!=train.shape or raw.shape!=held.shape or (train&held).any():
        raise ValueError('matching disjoint masks required')
    if train.sum()<4 or not held.any():raise ValueError('training and held support required')
    bias=float(raw[train].sum()/(train.sum()+(sigma/bias_sigma)**2))
    residual=raw[held]-bias
    return dict(training_bias_hz=bias,held_residual_hz=residual,
                held_RMS_hz=float(np.sqrt(np.mean(residual**2))))


def one(args):
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0']
    target=read(args.trial/'target_0.json')['target_entries'][0]
    if d['keep'][base.slices[base.members.index(target['track_index'])]].any():
        raise ValueError('target must be wholly inactive in calibration')
    annotation=read(args.annotation/'result.json')
    fold=next(f for f in annotation['folds'] if f['seed']==args.seed);split=fold['split']
    train,held=replay_split(base.flat_times,split);keep=d['keep']&train
    target_track=d['scan'].tracks[target['track_index']]
    tt,th=replay_split(target_track['times'],split)
    if tt.sum()<8 or th.sum()<4:raise ValueError('insufficient target partition')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(seed=args.seed,split=split,target=target,
        noise_hz=150,unit_powers=True,start=[0,0],box_width_km=25,phase_rounds=5,iterations=48,
        graph_and_ids_frozen=True,GPS_used=False,future_TLE=False,
        target_training_indices=np.flatnonzero(tt),target_held_indices=np.flatnonzero(th),
        target_in_calibration=False,existing_predictive_entries_training_only=True,
        held_target_constant_sigma_hz=300,held_target_noise_sigma_hz=150*np.sqrt(2),
        retained_policy_changed=False,held_values_excluded_from_fitting=True))
    results=[]
    for mode in ('default','conditional'):
        for role in ('control','addition'):
            full_entries=d['entries']+([target] if role=='addition' else [])
            scan,entries,receipts=predictive_training_views(d['scan'],full_entries,split)
            powers=np.ones(len(d['powers']));factory=training_factory(d)
            for arm in ('c0','fitted_c'):
                x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
                for _ in range(5):
                    p=make_event_problem(scan,d['node'],keep,arm,reference,powers,d['means'],d['model'],[],base_problem_factory=factory)
                    attach_event_predictive(p,entries,powers)
                    if mode=='conditional':attach_conditional_satellite_refresh(p,entries,powers,[target['candidate_index']])
                    cached(p);fr=fit(p,x,iterations=48);x=np.asarray(fr['parameters'])
                    reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                    history.append(dict(endpoint_east_north_km=x,**check))
                c=p.calculate(x);state=p.state(x);approx,_=p.conditional_frequency(x)
                predictions=[];domains=[]
                for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                    take=d['keep'][sl]&held[sl]
                    if not take.any():continue
                    t=p.scan.tracks[i];j=row['candidate_index'];times=t['times'][take]
                    domain=reference_domain(p.sky['time_s'],times,np.zeros(len(times),int),[state['phases'][j]],padding_s=0)
                    domains.append(domain)
                    if not domain['in_domain']:continue
                    f,_=family_frequency(p,x,j,times=times)
                    r=c['conditional_residual_hz'][sl][take]-p.q[sl][take]*(f-approx[sl][take])
                    predictions.append(dict(component=t['key'],kind='incumbent_curved',norad=row['candidate_norad'],
                        held_times_s=times,held_residual_hz=r,held_RMS_hz=float(np.sqrt(np.mean(r*r)))))
                # Evaluate all original predictive curves, plus target, using
                # full views only after the fitted posterior has been frozen.
                for entry in d['entries']+[target]:
                    t=p.scan.tracks[entry['track_index']];tr,he=replay_split(t['times'],split)
                    if tr.sum()<4 or not he.any():continue
                    j=entry['candidate_index']
                    domain=reference_domain(p.sky['time_s'],t['times'],np.zeros(len(tr),int),[state['phases'][j]],padding_s=0)
                    domains.append(domain)
                    if not domain['in_domain']:continue
                    f,e=family_frequency(p,x,j,times=t['times']);q=t['rf_hz']/11.5e9
                    raw=t['values']+entry['alias']*PERIOD-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[entry['track_index']]@state['smooth'][t['receiver']-1]-q*f
                    predictions.append(dict(component=t['key'],kind='target' if entry==target else 'incumbent_predictive',
                        norad=entry['norad'],held_times_s=t['times'][he],minimum_elevation_deg=float(e.min()),
                        **held_prediction(raw,tr,he)))
                result=dict(mode=mode,role=role,arm=arm,seed=args.seed,history=history,
                    final_phase_change_s=check['phase_change_s'],domains_valid=all(v['in_domain'] for v in domains),
                    objective=c['negative_twice_elbo'],endpoint_latlon=latlon(x),
                    receiver_delta_at_update=c.get('shared_satellite_receiver_change',0.),
                    predictive_training_views=receipts,predictions=predictions)
                results.append(result);write(args.output/f'{mode}-{role}-{arm}.json',result)
                target_result=next(r for r in predictions if r['kind']=='target')
                print(args.seed,mode,role,arm,round(target_result['held_RMS_hz'],2),flush=True)
    write(args.output/'result.json',dict(job=inv['job'],target=target,rows=results,
        conditional_validation_only=True,no_accepted_associations=True,
        predictive_point_RMS_not_calibrated_probability=True))


def run(args):
    seeds=[f['seed'] for f in read(args.annotation/'result.json')['folds']]
    if len(seeds)!=3:raise ValueError('exactly three saved partitions required')
    args.output.mkdir(parents=True,exist_ok=False)
    paths=[args.inventory,args.trial/'target_0.json',args.annotation/'result.json']
    write(args.output/'protocol.json',dict(seeds=seeds,inventory=str(args.inventory),trial=str(args.trial),
        annotation=str(args.annotation),source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        workers=3,seconds_per_fold=360,selection='Previously recovered 63381 candidate, fixed before these tests',
        no_GPS_selection=True,no_accepted_associations=True))
    def work(seed):
        cmd=[sys.executable,__file__,'one','--inventory',str(args.inventory),'--trial',str(args.trial),
            '--annotation',str(args.annotation),'--seed',str(seed),'--output',str(args.output/str(seed))]
        result=dict(seed=seed,command=cmd,**supervise(cmd,args.output/(str(seed)+'.log'),360))
        write(args.output/(str(seed)+'-terminal.json'),result);return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(work,s) for s in seeds]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['run','one'])
    for name in ('inventory','trial','annotation','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seed',type=int);a=p.parse_args();run(a) if a.mode=='run' else one(a)
