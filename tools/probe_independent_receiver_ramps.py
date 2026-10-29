"""Target-family-excluded validation and paired position fits for receiver ramps."""
import argparse
import hashlib
from pathlib import Path
import time
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training,prior_means
from annotate_predictive_only import prediction_models,calibration_covariance
from leo.analysis.research.grouped_prediction import replay_split,predictive_score
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD
from include_curved_family_annotations import configuration
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from algo02_scan import pair_passes


def receiver_ramps(receiver,maximum_time,kind):
    if kind not in ('receiver','receiver_RF'):raise ValueError('radio correction required')
    return [dict(kind=kind,receiver=int(receiver),time_s=float(t),transition_s=10.,sigma_hz=50.)
            for t in np.arange(0.,maximum_time,10.)]


def exclude_family(rows,slices,mask,norad,target_row):
    keep=np.array(mask,bool,copy=True)
    for k,(row,sl) in enumerate(zip(rows,slices,strict=True)):
        if k==target_row or row['candidate_norad']==norad:keep[sl]=False
    return keep


def run(args):
    began=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    original=read(args.inclusion/'protocol.json');target=original['targets'][0];inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0']
    annotation=read(args.validation/'result.json');i=target['track_index'];track=d['scan'].tracks[i];k=target['row'];j=target['candidate_index']
    independent=exclude_family(base.rows,base.slices,d['keep'],target['norad'],k)
    if independent[base.slices[k]].any():raise ValueError('target used for receiver calibration')
    maximum=float(max(base.flat_times.max(),track['times'].max()))
    models={'original':[],'receiver_hz':receiver_ramps(target['receiver'],maximum,'receiver'),
            'receiver_fractional':receiver_ramps(target['receiver'],maximum,'receiver_RF')}
    write(out/'protocol.json',dict(job=inv['job'],target=target,models=models,validation=str(args.validation),inclusion=str(args.inclusion),
          event_grid_selection='fixed ten-second ramps over scan timestamps; no residual or GPS selection',
          sigma_increment_hz=50.,randomized_partitions=[f['split'] for f in annotation['folds']],
          entire_target_family_excluded_from_validation_calibration=True,conditional_on_existing_identity_nomination=True,
          validation_fixed_noise_hz=150,validation_family_powers_all_one=True,phase_step_s=.025,
          original_full_fit_noise_and_other_priors=True,phase_rounds=5,iterations=48,start=[0,0],box_width_km=25,
          GPS_used=False,future_TLE=False,no_production_change=True,exploratory_prior=True))
    prior=args.resume_from
    if prior:
        old_protocol=read(prior/'protocol.json');new_protocol=read(out/'protocol.json')
        if old_protocol!=new_protocol:raise ValueError('resume protocol differs; no reuse permitted')
        folds=read(prior/'validation.json')['folds']
        sources=[prior/'protocol.json',prior/'validation.json']+list(prior.glob('*_control.json'))+list(prior.glob('*_target.json'))
        write(out/'continuation.json',dict(source=str(prior),reason='Resume missing full fits after verified terminal cap',
              source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},unchanged_numerical_protocol=True))
    else:folds=[]
    for fold in ([] if prior else annotation['folds']):
        train,held=replay_split(base.flat_times,fold['split']);tt,th=replay_split(track['times'],fold['split']);fold_result={}
        for name,events in models.items():
            pair={}
            for arm in ('c0','fitted_c'):
                p,x,meta=fit_training(d,d['node'],independent&train,arm,events=events)
                means,cov,lp,phases,elev,prior=prediction_models(d,p,x,i,j,phase_step=.025,uncalibrated_phase_mixture=True)
                if not np.isfinite(lp).any():raise ValueError('nominee not visible in predictive phase box')
                score=mixture_prediction(track['values']+target['alias']*PERIOD,means,cov,lp,tt,th)
                c,coefcov=calibration_covariance(p,x);mask=independent&held
                if not mask.any():raise ValueError('no independent held calibration observations')
                precision=np.where(c['noise_precision']>1e-12,c['noise_precision'],1.)
                sigma=p.point_noise[mask]/np.sqrt(precision[p.noise_groups[mask]])
                features=c['features'][p.keep]
                weight=c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
                gram=np.diag(c['coefficient_prior_precision'])+features.T@(features*weight[:,None])
                existing=predictive_score(c['conditional_residual_hz'][mask],c['features'][mask],gram,sigma)
                weights=score['training_mixture_weights']
                pair[arm]=dict(**meta,target_score=score,existing_score=existing,target_prior=prior,
                    target_phase_mean_s=float(weights@phases),target_phase_boundary_mass=float(weights[abs(phases)>=14.9].sum()),
                    minimum_elevation_deg=float(elev[weights>1e-6].min()),target_held_times_s=track['times'][th],
                    calibration_points=int(p.keep.sum()),held_existing_points=int(mask.sum()),
                    target_enters_receiver_calibration=False,event_amplitudes_hz=c.get('event_amplitudes_hz',[]))
            fold_result[name]=pair;write(out/f"validation-{fold['seed']}-{name}.json",pair)
            print(inv['job']['label'],fold['seed'],name,'held target RMS',[(a,round(v['target_score']['rms_hz'],1)) for a,v in pair.items()],flush=True)
        folds.append(dict(seed=fold['seed'],split=fold['split'],models=fold_result))
    write(out/'validation.json',dict(job=inv['job'],folds=folds))
    # Full fits use their original noise/prior rules. Validation above is separate.
    outcomes={}
    for name,events in models.items():
        for add in (False,True):
            tag=name+('_target' if add else '_control');extras=[target] if add else []
            if prior and (prior/(tag+'.json')).exists():
                result=read(prior/(tag+'.json'))
                if result['model']!=name or result['events']!=events or result['target_entries']!=extras or result['job']!=inv['job']:
                    raise ValueError('completed fit differs from continuation protocol')
                outcomes[tag]=result;write(out/(tag+'.json'),result)
                print(inv['job']['label'],tag,'reused unchanged',flush=True);continue
            node,keep=configuration(d['node'],d['keep'],base.slices,extras);means,_=prior_means(d,node);pair={}
            for arm in ('c0','fitted_c'):
                reference=np.zeros(len(means));x=np.zeros(2);history=[]
                for _ in range(5):
                    kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                    p=make_event_problem(d['scan'],node,keep,arm,reference,d['powers'],means,d['model'],events,**kw)
                    attach_event_predictive(p,d['entries'],d['powers']);cached(p);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
                    phase=np.clip(p.state(x)['phases'][p.labels],-15,15);delta=float(np.max(abs(phase-reference)));reference=phase
                    history.append(dict(fit=result,phase_change_s=delta))
                row=summary(p,x,d['entries']);_,_,ids,_=memberships(p,x,d['entries']);old=set(inv['policy'][arm]['proposed_associated_ids'])
                calc=p.calculate(x);diagnostics=[]
                for target_entry in extras:
                    sl=p.slices[target_entry['row']];raw=calc['conditional_residual_hz'][sl]
                    diagnostics.append(dict(component=target_entry['component'],norad=target_entry['norad'],times_s=track['times'],
                        CFO_hz=track['values'],residual_hz=raw,predicted_CFO_hz=track['values']-raw,
                        gate=next(g for g in row['gates']['tracks'] if g['component']==target_entry['component'])))
                row.update(history=history,final_phase_change_s=delta,proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids),
                           targets=diagnostics,event_amplitudes_hz=calc.get('event_amplitudes_hz',[]))
                pair[arm]=row
            valid=pair_passes(pair,include_linear=True) and all(v['lost_points']==0 for v in pair.values())
            result=dict(job=inv['job'],model=name,events=events,arms=pair,paired_valid=valid,target_entries=extras,no_production_change=True)
            outcomes[tag]=result;write(out/(tag+'.json'),result)
            print(inv['job']['label'],tag,'passes',valid,flush=True)
    write(out/'result.json',dict(job=inv['job'],validation=folds,full_fits=outcomes,seconds=time.monotonic()-began,no_production_change=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('inventory','inclusion','validation','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--resume-from',type=Path,help='Reuse exact-protocol completed validation and full-fit checkpoints')
    run(p.parse_args())
