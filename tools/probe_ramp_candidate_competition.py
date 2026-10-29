"""Renew causal satellite competition with candidate families excluded equally."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
import hashlib
from pathlib import Path
import sys
import time
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training,training_factory,prior_means,nominate,corrected
from annotate_predictive_only import prediction_models
from probe_independent_receiver_ramps import exclude_family
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import cached
from leo.analysis.research.grouped_prediction import replay_split,identity_consensus
from leo.analysis.research.cut_receiver_prediction import cut_receiver_prediction
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon
from stress_joint_attachment import supervise


def exclude_candidates(rows,slices,mask,norads,target_row):
    keep=np.array(mask,bool,copy=True)
    for norad in norads:keep=exclude_family(rows,slices,keep,norad,target_row)
    return keep


def restore_training(d,path,expected_keep):
    r=read(path);keep=np.zeros(len(expected_keep),bool);keep[r['keep_indices']]=True
    if not np.array_equal(keep,expected_keep):raise ValueError('calibration keep mask mismatch')
    means,_=prior_means(d,d['node']);p=make_event_problem(d['scan'],d['node'],keep,r['arm'],np.asarray(r['reference']),
        np.ones(len(d['powers'])),means,d['model'],r['events'],base_problem_factory=training_factory(d))
    cached(p);x=np.asarray(r['meta']['endpoint_east_north_km'])
    if abs(p.calculate(x)['negative_twice_elbo']-r['meta']['training_objective'])>1e-5:
        raise ValueError('calibration checkpoint objective mismatch')
    return p,x,r['meta']


def worker(args):
    start=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    source=args.transfer/args.track;pr=read(source/'protocol.json');old=pr['previous_protocol'];job=pr['job']
    r=read(source/'result.json');inv=read(Path(job['inventory']));d=context(inv);base,_=d['problems']['c0']
    target=old['target'];i=target['track_index'];track=d['scan'].tracks[i]
    independent=exclude_family(base.rows,base.slices,d['keep'],target['norad'],target['row'])
    write(out/'protocol.json',dict(job=job,source=str(source),source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [source/'protocol.json',source/'result.json']},
        nomination='top three from full causal bank per receiver model; union plus original nominee',
        calibration_exclusion='entire union of nominated satellite families, including target row',
        aliases='target training only under original model; shared across models and c arms',
        phase_step_s=.025,models=old['models'],phase_receiver_factorization=True,
        GPS_used=False,future_TLE=False,position_uncertainty_integrated=False,no_production_change=True,
        joint_train_held_evidence_diagnostic=True,acceptance_rule_unchanged=True,
        previous_result=str(args.previous/args.track/'result.json') if args.previous else None))
    all_models={name:[] for name in old['models']}
    for fold in r['folds']:
        seed=fold['seed'];train,_=replay_split(base.flat_times,fold['split']);tt,th=replay_split(track['times'],fold['split'])
        union={};receipts={};baseline=None
        for name in old['models']:
            training={arm:restore_training(d,source/f'calibration-{seed}-{name}-{arm}.json',independent&train)
                      for arm in ('c0','fitted_c')}
            offers,receipt=nominate(d,training,i,tt,3);receipts[name]=receipt
            if name=='original':baseline=training
            for offer in offers:
                j=offer['candidate_index']
                if j not in union or offer['cost']<union[j]['cost']:union[j]=offer
        union.setdefault(target['candidate_index'],dict(candidate_index=target['candidate_index'],phase_s=0.,position=[0.,0.],cost=None))
        for j,offer in union.items():
            bank={key:d['scan'].sky[key][[j]] for key in ('position_km','velocity_km_s')};bank['time_s']=d['scan'].sky['time_s']
            f,_=paired_phase_frequency(bank,track['times'][tt],np.zeros(tt.sum(),int),np.array([offer['phase_s']]),*latlon(offer['position']))
            p,x,_=baseline['c0'];alias=int(profile_rate(corrected(p,x,i)[tt],track['rf_hz']/11.5e9*f,track['times'][tt])['alias'][0])
            offer.update(alias=alias,norad=int(d['scan'].norads[j]))
        excluded={q['norad'] for q in union.values()}
        keep=exclude_candidates(base.rows,base.slices,d['keep']&train,excluded,target['row'])
        write(out/f'nominations-{seed}.json',dict(seed=seed,split=fold['split'],selected=list(union.values()),receipts=receipts,
              excluded_norads=sorted(excluded),calibration_points=int(keep.sum())))
        print(job['label'],seed,'candidate union',sorted(excluded),'training points',int(keep.sum()),flush=True)
        for name,events in old['models'].items():
            training={arm:fit_training(d,d['node'],keep,arm,events=events) for arm in ('c0','fitted_c')};proposals=[]
            for j,offer in union.items():
                pair={}
                for arm,(p,x,meta) in training.items():
                    means,cov,lp,phases,elev,receipt,frozen=prediction_models(d,p,x,i,j,phase_step=.025,
                        uncalibrated_phase_mixture=True,return_frozen_covariance=True)
                    if np.isfinite(lp).any():
                        score=cut_receiver_prediction(track['values']+offer['alias']*PERIOD,means,cov,frozen,lp,tt,th)
                        ordinary=mixture_prediction(track['values']+offer['alias']*PERIOD,means,cov,lp,tt,th)
                        joint=mixture_prediction(track['values']+offer['alias']*PERIOD,means,cov,lp,np.zeros(len(tt),bool),tt|th)
                        if abs(joint['negative_twice_log_density']-ordinary['negative_twice_log_density']-
                               ordinary['training_negative_twice_log_density'])>1e-5:
                            raise ValueError('joint evidence decomposition failed')
                        w=score['training_mixture_weights'];minimum=float(elev[w>1e-6].min())
                        phase=float(w@phases);boundary=float(w[abs(phases)>=14.9].sum())
                    else:
                        score=dict(negative_twice_log_density=1e30,rms_hz=1e15,unobservable=True)
                        ordinary=joint=score
                        minimum=float(elev.max());phase=boundary=None
                    pair[arm]=dict(**meta,scores={'target':score,'conditional_target':score,'ordinary_conditional':ordinary,'joint_target':joint},prior=receipt,
                        minimum_target_elevation_deg=minimum,target_phase_mean_s=phase,target_phase_boundary_mass=boundary,
                        candidate_family_used_for_calibration=False)
                proposal=dict(candidate_index=j,norad=offer['norad'],alias=offer['alias'],arms=pair)
                proposals.append(proposal);write(out/f'{seed}-{name}-{offer["norad"]}.json',proposal)
            result=dict(seed=seed,split=fold['split'],proposals=proposals)
            all_models[name].append(result);write(out/f'fold-{seed}-{name}.json',result)
            print(job['label'],seed,name,'best',[(a,min(proposals,key=lambda q:q['arms'][a]['scores']['target']['negative_twice_log_density'])['norad'])
                  for a in ('c0','fitted_c')],flush=True)
    annotations={name:identity_consensus(folds,score_name='conditional_target') for name,folds in all_models.items()}
    replay=[]
    if args.previous:
        path=args.previous/args.track/'result.json';previous=read(path)
        for name,folds in all_models.items():
            for f,oldfold in zip(folds,previous['models'][name],strict=True):
                if f['seed']!=oldfold['seed']:raise ValueError('replayed partition mismatch')
                oldproposals={q['norad']:q for q in oldfold['proposals']}
                if set(oldproposals)!={q['norad'] for q in f['proposals']}:raise ValueError('replayed candidate set mismatch')
                for proposal in f['proposals']:
                    oldp=oldproposals[proposal['norad']]
                    if oldp['alias']!=proposal['alias']:raise ValueError('replayed alias mismatch')
                    for arm in ('c0','fitted_c'):
                        delta=abs(proposal['arms'][arm]['scores']['target']['negative_twice_log_density']-
                                  oldp['arms'][arm]['scores']['target']['negative_twice_log_density'])
                        if delta>1e-5:raise ValueError('replayed frozen score mismatch')
                        replay.append(delta)
        write(out/'replay.json',dict(source=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
              comparisons=len(replay),maximum_frozen_score_delta=max(replay)))
    write(out/'result.json',dict(job=job,models=all_models,annotations=annotations,seconds=time.monotonic()-start,
        original_norad=target['norad'],new_position_fits=False,no_production_change=True,
        maximum_frozen_score_replay_delta=max(replay) if replay else None))


def run(args):
    if args.track:return worker(args)
    with args.qualification.open() as f:qualified={r['scan'] for r in csv.DictReader(f) if r['joint_screen_pass']=='True'}
    jobs=[j for j in read(args.transfer/'protocol.json')['jobs'] if j['label'] in qualified]
    if len(jobs)!=2:raise ValueError('requires the two previously passing cases')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,qualification_source=str(args.qualification),
        qualification_sha256=hashlib.sha256(args.qualification.read_bytes()).hexdigest(),workers=2,seconds_per_case=600,
        selection='Both cases passing the preceding conditional predictive/full-fit checks; no GPS selection'))
    def work(job):
        tid=job['track_id'];cmd=[sys.executable,__file__,'--transfer',str(args.transfer),'--output',str(args.output/tid),'--track',tid]
        if args.previous:cmd+=['--previous',str(args.previous)]
        terminal=dict(job=job,command=cmd,**supervise(cmd,args.output/(tid+'.log'),600))
        write(args.output/(tid+'-terminal.json'),terminal);return terminal
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(work,j) for j in jobs]):print(future.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transfer',type=Path,required=True)
    p.add_argument('--qualification',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--track');p.add_argument('--previous',type=Path)
    run(p.parse_args())
