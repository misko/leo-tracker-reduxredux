"""Random block test of target-excluded receiver residual prediction."""
import argparse,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training
from annotate_predictive_only import check_predictive_role
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.grouped_prediction import replay_split,identity_consensus
from leo.analysis.research.retained_track_likelihood import PERIOD
from residual_witness_prediction import predict
from stress_joint_attachment import supervise


def bias_from_training(raw,training):
    values=np.asarray(raw)[training]
    if not len(values):raise ValueError('target training points required for the constant')
    return float(values.sum()/(len(values)+(150./300.)**2))


def one(args):
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0']
    source=read(args.source/'result.json');pr=read(args.source/'protocol.json')
    annotation=identity_consensus(source['folds'],score_name='conditional_target')
    if annotation['status']!='conditionally_supported_identity':raise ValueError('supported identity required')
    i=pr['target']['track_index'];track=d['scan'].tracks[i];check_predictive_role(base,i,True)
    j=int(np.flatnonzero(d['scan'].norads==annotation['norad'])[0])
    aliases={q['alias'] for f in source['folds'] for q in f['proposals'] if q['norad']==annotation['norad']}
    if len(aliases)!=1:raise ValueError('stable alias required')
    alias=next(iter(aliases));fold=next(f for f in source['folds'] if f['seed']==args.seed)
    train,_=replay_split(base.flat_times,fold['split']);tt,held=replay_split(track['times'],fold['split'])
    keep=d['keep']&train;args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(job=inv['job'],seed=args.seed,split=fold['split'],target_norad=annotation['norad'],
        target_component=track['key'],target_training_indices=np.flatnonzero(tt),target_held_indices=np.flatnonzero(held),
        all_witness_values_training_only=True,fixed_noise_hz=150,unit_family_powers=True,
        target_fits_only_one_constant_on_training=True,no_target_calibration=True,
        incumbent_predictive_observations_excluded=True,curved_only_conditioning=True,GPS_used=False))
    results=[]
    for arm in ('c0','fitted_c'):
        p,x,meta=fit_training(d,d['node'],keep,arm);c=p.calculate(x);state=p.state(x)
        approximate,_=p.conditional_frequency(x);witnesses=[]
        for row,k,sl in zip(p.rows,p.members,p.slices,strict=True):
            active=p.keep[sl]
            if active.sum()<4:continue
            w=p.scan.tracks[k];times=w['times'][active];f,_=family_frequency(p,x,row['candidate_index'],times=times)
            residual=c['conditional_residual_hz'][sl][active]-p.q[sl][active]*(f-approximate[sl][active])
            witnesses.append(dict(component=w['key'],norad=row['candidate_norad'],receiver=w['receiver'],channel=w['channel'],
                rf_hz=w['rf_hz'],times_s=times,residual_hz=residual))
        f,e=family_frequency(p,x,j,times=track['times']);q=track['rf_hz']/11.5e9
        raw=track['values']+alias*PERIOD-p.scan.hardware(track,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][track['receiver']-1]-q*f
        target=dict(component=track['key'],norad=annotation['norad'],receiver=track['receiver'],channel=track['channel'],rf_hz=track['rf_hz'],times_s=track['times'])
        baseline=raw-bias_from_training(raw,tt);rows=[]
        for relation in ('same_receiver','same_receiver_band','other_receiver','same_satellite'):
            for width in (3.,6.,12.):
                for scaling in ('hz','fractional'):
                    pred=predict(target,witnesses,width_s=width,relation=relation,scaling=scaling,minimum_families=1 if relation=='same_satellite' else 2)
                    corrected=raw-pred['prediction_hz'];bias=bias_from_training(corrected,tt);residual=corrected-bias
                    rows.append(dict(relation=relation,width_s=width,scaling=scaling,
                        training_bias_hz=bias,held_points=int(held.sum()),held_supported_points=int(pred['qualified'][held].sum()),
                        held_RMS_hz=float(np.sqrt(np.mean(residual[held]**2))),baseline_held_RMS_hz=float(np.sqrt(np.mean(baseline[held]**2))),
                        held_residual_hz=residual[held],held_prediction_hz=pred['prediction_hz'][held],
                        held_distinct_families=pred['distinct_families'][held],witness_families=pred['witness_families']))
        results.append(dict(arm=arm,training=meta,minimum_target_elevation_deg=float(e.min()),
            held_times_s=track['times'][held],baseline_held_residual_hz=baseline[held],rows=rows))
    write(args.output/'result.json',dict(job=inv['job'],seed=args.seed,results=results,
        conditional_on_frozen_graph_and_incumbent_ids=True,position_not_refitted_with_correction=True,
        no_accepted_associations=True,independent_partitions_not_independent_replications=True))
    print(inv['job']['label'],args.seed,'held receiver prediction complete',flush=True)


def run(args):
    r=read(args.source/'result.json');seeds=[f['seed'] for f in r['folds']]
    if len(seeds)!=3:raise ValueError('three original randomized partitions required')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(job=r['job'],seeds=seeds,source=str(args.source),inventory=str(args.inventory),
        source_sha256=hashlib.sha256((args.source/'result.json').read_bytes()).hexdigest(),workers=3,seconds_per_fold=300,
        primary=dict(relation='same_receiver',width_s=6.,scaling='hz',minimum_families=2),
        other_variants='predeclared sensitivity checks, not selected using target or GPS',
        all_scan_held_blocks_removed_before_fitting=True,no_production_change=True))
    def work(seed):
        cmd=[sys.executable,__file__,'one','--inventory',str(args.inventory),'--source',str(args.source),
             '--seed',str(seed),'--output',str(args.output/str(seed))]
        terminal=dict(seed=seed,command=cmd,**supervise(cmd,args.output/(str(seed)+'.log'),300))
        write(args.output/(str(seed)+'-terminal.json'),terminal);return terminal
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(work,seed) for seed in seeds]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['run','one'])
    for key in ('source','inventory','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--seed',type=int);args=p.parse_args();run(args) if args.mode=='run' else one(args)
