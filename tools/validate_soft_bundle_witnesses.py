"""Conditional held-block challenge of target-excluded receiver corrections."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from predictive_graph_bundle import bundle_context
from annotate_track_predictively import fit_training
from annotate_predictive_only import prediction_models
from diagnose_soft_bundle_witnesses import collect,disjoint_witnesses
from residual_witness_prediction import predict
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD


def assert_training_only(witnesses,split):
    for witness in witnesses:
        training,_=replay_split(np.asarray(witness['times_s']),split)
        if not training.all():raise ValueError('held or guard observations leaked into receiver correction')


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.trial/'protocol.json');inv=read(args.inventory);d=context(inv)
    d,target=bundle_context(d,inv,Path(pr['target']['bundle_source']),pr['target']['track_id'])
    annotation=read(args.annotation/'result.json');fold=next(f for f in annotation['folds'] if f['seed']==args.seed)
    base,_=d['problems']['c0'];training,_=replay_split(base.flat_times,fold['split']);i=target['track_index'];track=d['scan'].tracks[i]
    train,held=replay_split(track['times'],fold['split']);keep=d['keep']&training
    write(args.output/'protocol.json',dict(seed=args.seed,job=inv['job'],target=target,split=fold['split'],candidates=pr['candidates'],
        widths_s=[0,3,6],primary_width_s=6,discovery_selected_width_s=3,relation='same_receiver',scaling='hz',minimum_families=2,
        fixed_noise_hz=150,unit_family_powers=True,phase_step_s=.025,phase_limit_s=15,
        target_and_witness_training_only=True,incumbent_predictive_entries_excluded=True,
        candidate_set_selected_in_previous_RF_development=True,reused_partitions_not_fresh_validation=True,
        correction_uncertainty_not_integrated=True,no_position_inclusion_authorized=True,GPS_used=False,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.trial/'protocol.json',args.annotation/'result.json')}))
    results=[]
    for arm in ('c0','fitted_c'):
        p,x,meta=fit_training(d,d['node'],keep,arm);witnesses,unavailable=collect(p,x,[])
        witnesses,excluded=disjoint_witnesses(witnesses,target['observation_ids']);assert_training_only(witnesses,fold['split'])
        if excluded:raise ValueError('target entered calibration')
        proposals=[]
        for candidate in pr['candidates']:
            j=int(np.flatnonzero(d['scan'].norads==candidate['norad'])[0]);means,cov,lp,phases,elevations,prior=prediction_models(d,p,x,i,j,phase_step=.025,uncalibrated_phase_mixture=True)
            tt=dict(component=track['key'],norad=candidate['norad'],receiver=track['receiver'],channel=track['channel'],rf_hz=track['rf_hz'],times_s=track['times'])
            predictions={width:predict(tt,witnesses,width_s=width,relation='same_receiver',scaling='hz',minimum_families=2) for width in (3.,6.)}
            for alias in candidate['aliases']:
                observed=track['values']+alias*PERIOD
                for width in (0.,3.,6.):
                    correction=predictions[width]['prediction_hz'] if width else np.zeros(len(observed))
                    score=mixture_prediction(observed,means+correction,cov,lp,train,held)
                    weight=score['training_mixture_weights'];score.pop('held_covariance_hz2')
                    proposals.append(dict(norad=candidate['norad'],alias=alias,width_s=width,score=score,prior=prior,
                        phase_mean_s=float(weight@phases),phase_boundary_mass=float(weight[abs(phases)>=14.9].sum()),
                        held_supported_points=int(predictions[width]['qualified'][held].sum()) if width else 0,
                        held_prediction_hz=correction[held],witness_families=predictions[width]['witness_families'] if width else [],
                        minimum_elevation_deg=float(elevations[weight>1e-6].min())))
        row=dict(arm=arm,training=meta,held_times_s=track['times'][held],held_points=int(held.sum()),proposals=proposals,
            witnesses=witnesses,unavailable=unavailable)
        results.append(row);write(args.output/(arm+'.json'),row)
        print(inv['job']['label'],args.seed,arm,'complete',flush=True)
    write(args.output/'result.json',dict(seed=args.seed,results=results,no_position_refit_with_correction=True,no_associations_authorized=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','trial','annotation','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);run(p.parse_args())
