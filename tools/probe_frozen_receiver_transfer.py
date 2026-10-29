"""Bounded replay of five ramp cases with receiver feedback explicitly cut."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path
import sys
import time
import numpy as np
from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training
from annotate_predictive_only import prediction_models
from probe_independent_receiver_ramps import exclude_family
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.cut_receiver_prediction import cut_receiver_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD
from stress_joint_attachment import supervise


def worker(args):
    start=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    cohort=read(args.previous/'protocol.json');job=next(j for j in cohort['jobs'] if j['track_id']==args.track)
    source=args.previous/args.track;protocol=read(source/'protocol.json');prior=read(source/'validation.json')
    inv=read(Path(job['inventory']));d=context(inv);base,_=d['problems']['c0'];target=protocol['target']
    i,j=target['track_index'],target['candidate_index'];track=d['scan'].tracks[i]
    independent=exclude_family(base.rows,base.slices,d['keep'],target['norad'],target['row'])
    write(out/'protocol.json',dict(source=str(source),source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (source/'protocol.json',source/'validation.json',Path(job['inventory']))},
        previous_protocol=protocol,job=job,prediction_modes=['ordinary','frozen_receiver','no_target_training'],
        phase_receiver_factorization=True,fixed_phase_receiver_marginal_unchanged=True,
        conditional_on_incumbent_nominee=True,new_position_fits=False,no_production_change=True))
    folds=[]
    for fold in prior['folds']:
        train,_=replay_split(base.flat_times,fold['split']);tt,th=replay_split(track['times'],fold['split'])
        models={}
        for name,events in protocol['models'].items():
            pair={}
            for arm in ('c0','fitted_c'):
                p,x,meta=fit_training(d,d['node'],independent&train,arm,events=events)
                old=fold['models'][name][arm]
                if abs(meta['training_objective']-old['training_objective'])>1e-5:
                    raise ValueError('training objective failed exact replay')
                write(out/f"calibration-{fold['seed']}-{name}-{arm}.json",dict(meta=meta,reference=p.reference,
                      keep_indices=np.flatnonzero(p.keep),events=events,arm=arm,source_protocol=str(out/'protocol.json')))
                means,cov,lp,phases,elev,receipt,frozen=prediction_models(d,p,x,i,j,phase_step=.025,
                    uncalibrated_phase_mixture=True,return_frozen_covariance=True)
                observed=track['values']+target['alias']*PERIOD
                ordinary=mixture_prediction(observed,means,cov,lp,tt,th)
                delta=abs(ordinary['negative_twice_log_density']-old['target_score']['negative_twice_log_density'])
                if delta>1e-5:raise ValueError('previous conditional score failed exact replay')
                cut=cut_receiver_prediction(observed,means,cov,frozen,lp,tt,th)
                prior_only=mixture_prediction(observed,means,cov,lp,np.zeros(len(tt),bool),th)
                scores={}
                for mode,score in [('ordinary',ordinary),('frozen_receiver',cut),('no_target_training',prior_only)]:
                    weights=score['training_mixture_weights']
                    scores[mode]=dict(score=score,phase_mean_s=float(weights@phases),
                        phase_boundary_mass=float(weights[abs(phases)>=14.9].sum()),
                        minimum_elevation_deg=float(elev[weights>1e-6].min()))
                pair[arm]=dict(**meta,scores=scores,existing_score=old['existing_score'],prior=receipt,
                    held_times_s=track['times'][th],held_CFO_hz=track['values'][th],
                    objective_replay_delta=abs(meta['training_objective']-old['training_objective']),
                    conditional_score_replay_delta=delta,frozen_point_sigma_hz=np.sqrt(np.diag(frozen)),
                    training_points=int(tt.sum()),held_points=int(th.sum()))
            models[name]=pair;write(out/f"fold-{fold['seed']}-{name}.json",pair)
            print(job['label'],fold['seed'],name,'frozen RMS',
                  [round(v['scores']['frozen_receiver']['score']['rms_hz'],2) for v in pair.values()],flush=True)
        folds.append(dict(seed=fold['seed'],split=fold['split'],models=models))
    write(out/'result.json',dict(job=job,folds=folds,seconds=time.monotonic()-start,no_production_change=True))


def run(args):
    if args.track:return worker(args)
    protocol=read(args.previous/'protocol.json');jobs=protocol['jobs']
    if len(jobs)!=5:raise ValueError('requires original five-case cohort')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(source=str(args.previous),jobs=jobs,workers=5,seconds_per_case=600,
        selection='All five previously tested ramp cases; no outcome selection',GPS_used=False,no_production_change=True))
    def work(job):
        tid=job['track_id'];cmd=[sys.executable,__file__,'--previous',str(args.previous),'--output',str(args.output/tid),'--track',tid]
        result=dict(job=job,command=cmd,**supervise(cmd,args.output/(tid+'.log'),600))
        write(args.output/(tid+'-terminal.json'),result);return result
    with ThreadPoolExecutor(max_workers=5) as pool:
        for future in as_completed([pool.submit(work,j) for j in jobs]):print(future.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--track')
    run(p.parse_args())
