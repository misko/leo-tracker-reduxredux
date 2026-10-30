"""Random-block validation of a step discovered without the target family."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from inactive_graph_fragment import validated_inactive_context
from annotate_track_predictively import fit_training
from annotate_predictive_only import prediction_models,calibration_covariance
from probe_independent_receiver_ramps import exclude_family
from independent_step_witness import search
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.grouped_prediction import replay_split,predictive_score
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD


def training_curves(p,x):
    c=p.calculate(x);approx,_=p.conditional_frequency(x);curves=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        mask=p.keep[sl]
        if mask.sum()<8:continue
        t=p.scan.tracks[i];times=t['times'][mask];f,_=family_frequency(p,x,row['candidate_index'],times=times)
        raw=c['conditional_residual_hz'][sl][mask]-p.q[sl][mask]*(f-approx[sl][mask])
        curves.append(dict(component=t['key'],norad=row['candidate_norad'],receiver=t['receiver'],channel=t['channel'],rf_hz=t['rf_hz'],times_s=times,residual_hz=raw))
    return curves


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);d=context(inv)
    d,target=validated_inactive_context(d,inv,args.validation);ann=read(args.validation/'result.json');norad=ann['annotation']['norad']
    if ann['annotation']['status']!='conditionally_supported_identity':raise ValueError('supported fragment identity required')
    base,_=d['problems']['c0'];track=d['scan'].tracks[target['track_index']];j=int(np.flatnonzero(d['scan'].norads==norad)[0])
    k=base.members.index(target['parent_track_index']);independent=exclude_family(base.rows,base.slices,d['keep'],norad,k)
    if any(independent[sl].any() for row,sl in zip(base.rows,base.slices,strict=True) if row['candidate_norad']==norad):raise ValueError('target family entered calibration')
    metadata=dict(component=track['key'],norad=norad,receiver=track['receiver'],channel=track['channel'],rf_hz=track['rf_hz'],times_s=track['times'])
    paths=[args.inventory,args.validation/'result.json',args.validation/'protocol.json']
    write(out/'protocol.json',dict(job=inv['job'],target=target,norad=norad,folds=[f['split'] for f in ann['folds']],
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        target_family_excluded_from_calibration=True,predictive_incumbents_excluded_from_training=True,
        step_discovery='training-only c0 residuals; same receiver additive Hz; apply identical selected event to both arms',
        fixed_noise_hz=150,amplitude_prior_hz=150,full_scan_step_time_not_reused=True,GPS_used=False,future_TLE=False,
        position_inclusion_authorized=False,phase_step_s=.1,phase_rounds=5,position_steps=48))
    folds=[]
    for fold in ann['folds']:
        train,held=replay_split(base.flat_times,fold['split']);tt,th=replay_split(track['times'],fold['split'])
        controls={a:fit_training(d,d['node'],independent&train,a) for a in ('c0','fitted_c')}
        p,x,_=controls['c0'];proposal=search(training_curves(p,x),metadata,scope='same_receiver',scaling='hz')
        events=([dict(kind='receiver',receiver=track['receiver'],time_s=proposal['best']['time_s'],sigma_hz=150.)]
                if proposal['supported_exploratory_proposal'] else [])
        aliases={q['alias'] for q in fold['proposals'] if q['norad']==norad}
        if len(aliases)!=1:raise ValueError('validated family alias is not unique')
        observed=track['values']+next(iter(aliases))*PERIOD;models={}
        for name in ('original','training_selected_step'):
            pair={}
            for arm in ('c0','fitted_c'):
                p,x,meta=(fit_training(d,d['node'],independent&train,arm,events=events)
                    if name=='training_selected_step' and events else controls[arm])
                means,cov,lp,phases,elev,prior=prediction_models(d,p,x,target['track_index'],j,uncalibrated_phase_mixture=True)
                score=mixture_prediction(observed,means,cov,lp,tt,th)
                c,coefcov=calibration_covariance(p,x);mask=independent&held
                u=c['features'][p.keep];w=c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
                gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
                sigma=p.point_noise[mask]/np.sqrt(np.maximum(c['noise_precision'][p.noise_groups[mask]],1e-12))
                existing=predictive_score(c['conditional_residual_hz'][mask],c['features'][mask],gram,sigma)
                pair[arm]=dict(**meta,target_score=score,existing_score=existing,target_prior=prior,
                    target_held_times_s=track['times'][th],event_amplitudes_hz=c.get('event_amplitudes_hz',[]),
                    event_selected=bool(events),target_enters_calibration=False)
            models[name]=pair
        result=dict(seed=fold['seed'],split=fold['split'],proposal=proposal,events=events,models=models)
        write(out/(str(fold['seed'])+'.json'),result);folds.append(result)
        print(inv['job']['label'],fold['seed'],'event',events,'target delta',[(a,round(models['training_selected_step'][a]['target_score']['negative_twice_log_density']-models['original'][a]['target_score']['negative_twice_log_density'],3)) for a in ('c0','fitted_c')],flush=True)
    write(out/'result.json',dict(job=inv['job'],folds=folds,independent_family_excluded_validation=True,
        conditional_on_existing_identity=True,event_time_uncertainty_not_integrated=True,no_position_inclusion=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','validation','output'):parser.add_argument('--'+name,type=Path,required=True)
    run(parser.parse_args())
