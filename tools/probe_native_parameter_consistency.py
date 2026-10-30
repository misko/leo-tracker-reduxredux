"""Separate satellite, fragment-bias and receiver explanations of native failures.

Full-fit shifts are diagnostics only. Randomized scan-wide block refits exclude
held observations from calibration and target conditioning. Identities remain
the previously selected hypotheses, so this does not validate false-ID rates.
"""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context,validated_native_source
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_frequency_events import cached
from probe_native_residual_transfer import assess
from compare_dsx01_frame_joint import conditional_gate
from annotate_track_predictively import fit_training
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.fixed_coordinate_prediction import fixed_coordinate_prediction


def coordinate_sets(p,j):
    begin=p.hardware.shape[1]+p.smooth.shape[1];nf=len(p.labels);no=3*len(p.supported)
    satellite=[begin+p.labels.index(j)]
    if j in p.supported:
        start=begin+nf+3*p.supported.index(j);satellite+=list(range(start,start+3))
    biases=[begin+nf+no+k for k,r in enumerate(p.rows) if r['candidate_index']==j]
    return dict(bias_only=biases,phase_orbit_fixed_bias=satellite,
        phase_orbit_bias=satellite+biases,receiver_only=list(range(begin)),
        all_coordinates=list(range(p.event_start)))


def geometry(p,x,target,powers,sigma_override=None):
    c=p.calculate(x);g=p.noise_groups[p.keep]
    weight=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    u=c['features'][p.keep];gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weight[:,None])
    view,values,sigma,groups,slices=linear_geometry(p,[target]);geo=geometry_features(view,x,0.)
    mean=view.q*geo['intercept']+geo['features']@c['coefficient']
    if sigma_override is not None:sigma=np.full(len(values),sigma_override)
    noise=np.diag(2*sigma*sigma)+300.**2
    return c,gram,geo['features'],values,mean,noise,geo['elevation']


def witnesses(p,c,delta,target,held=None):
    answer=[];tt=p.scan.tracks[target['track_index']]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        t=p.scan.tracks[i];mask=p.keep[sl] if held is None else held[sl]
        if mask.sum()<4:continue
        same=row['candidate_index']==target['candidate_index'];same_rx=t['receiver']==tt['receiver']
        times=t['times'][mask];overlap=(times>=tt['times'].min())&(times<=tt['times'].max())
        if not same and not (same_rx and overlap.sum()>=4):continue
        before=c['conditional_residual_hz'][sl][mask]
        after=before-(c['features'][sl]@delta)[mask]
        answer.append(dict(component=t['key'],norad=row['candidate_norad'],same_family=same,same_receiver=same_rx,
            receiver=t['receiver'],channel=t['channel'],times_s=times,points=int(mask.sum()),overlap_points=int(overlap.sum()),
            before_residual_hz=before,after_residual_hz=after,before=conditional_gate(before,times),after=conditional_gate(after,times)))
    return answer


def run(args):
    out=args.output;out.mkdir(exist_ok=False,parents=True);inv=read(args.inventory);pr=read(args.inclusion/'protocol.json')
    saved=read(args.inclusion/'target_0.json');target=saved['target_entries'][0]
    validation=Path(pr['annotation_receipts'][0]['path']);annotation=read(validation/'result.json')
    source=validated_native_source(validation);d=context(inv)
    d,_=native_context(d,inv,source,annotation['track_id']);t=d['scan'].tracks[target['track_index']]
    write(out/'protocol.json',dict(inventory=str(args.inventory),inclusion=str(args.inclusion),validation=str(validation),
        native_source=str(source),target=target,matched_c=True,no_GPS=True,no_future_TLE=True,no_new_parameter_priors=True,
        full_fit_is_diagnostic=True,conditional_models_fix_excluded_parameters_at_posterior_means=True,
        held_blocks_excluded_scanwide=True,noise_policy='original full replay; fixed 150 Hz training and 2x predictive variance in block refits',
        identities_selected_previously_using_all_target_points=True,no_independent_identity_validation=True))
    full={};folds=[]
    for arm,row in saved['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(row['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,d['entries']+[target],d['powers']);cached(p);x=np.array(row['endpoint_east_north_km'])
        c,gram,h,y,mean,noise,elevation=geometry(p,x,target,d['powers'])
        difference=c['negative_twice_elbo']-row['negative_twice_elbo']
        if abs(difference)>1e-5:raise ValueError('original endpoint failed exact replay')
        variants={};begin=p.hardware.shape[1]+p.smooth.shape[1]
        for name,indices in coordinate_sets(p,target['candidate_index']).items():
            v=fixed_coordinate_prediction(c['coefficient'],gram,h,y-mean,noise,indices)
            delta=v['coefficient']-c['coefficient'];receiver=float(np.max(abs(delta[:begin])))
            if name in ('bias_only','phase_orbit_fixed_bias','phase_orbit_bias') and receiver!=0:raise ValueError('receiver changed')
            from shared_satellite_refresh import exact_shared_replay
            original=p.calculate;p.shared_satellite_families=[target['candidate_index']]
            p.calculate=lambda position:dict(c,coefficient=v['coefficient'])
            try:exact=exact_shared_replay(p,x,d['entries']+[target])
            finally:p.calculate=original
            variants[name]=dict(target=assess(y-mean-h@delta,t['times']),parameter_shift=delta,
                allowed_indices=indices,shift_mahalanobis=v['shift_mahalanobis'],receiver_coordinate_change=receiver,
                conditional_predictive_objective=v['negative_twice_log_density'],exact_phase=exact,
                witnesses=witnesses(p,c,delta,target))
        full[arm]=dict(times_s=t['times'],CFO_hz=y,original_prediction_hz=mean,original=assess(y-mean,t['times']),
            variants=variants,objective_replay_difference=difference,minimum_elevation_deg=float(elevation.min()))
        print(inv['job']['label'],arm,'full',[(k,round(v['target']['RMS_hz'],1),v['target']['noise']['noise_screen_pass']) for k,v in variants.items()],flush=True)
    write(out/'full.json',full)
    for fold in annotation['folds']:
        split=fold['split'];train_target,held_target=replay_split(t['times'],split)
        p0,_=d['problems']['c0'];train,held=replay_split(p0.flat_times,split)
        if train_target.sum()<8 or held_target.sum()<4:raise ValueError('insufficient original target partition')
        keep=d['keep']&train;held_old=d['keep']&held
        arm_results={}
        for arm in ('c0','fitted_c'):
            p,x,meta=fit_training(d,d['node'],keep,arm)
            c,gram,h,y,mean,noise,elevation=geometry(p,x,target,np.ones(len(d['powers'])),150.)
            variants={}
            for name,indices in coordinate_sets(p,target['candidate_index']).items():
                prior=fixed_coordinate_prediction(c['coefficient'],gram,h,np.zeros(len(y)),noise,indices)
                prediction=mixture_prediction(y,mean[None,:],prior['predictive_covariance'][None,:,:],np.zeros(1),train_target,held_target)
                conditioned=fixed_coordinate_prediction(c['coefficient'],gram,h[train_target],(y-mean)[train_target],
                    noise[np.ix_(train_target,train_target)],indices)
                delta=conditioned['coefficient']-c['coefficient']
                variants[name]=dict(prediction=prediction,parameter_shift=delta,shift_mahalanobis=conditioned['shift_mahalanobis'],
                    witnesses=witnesses(p,c,delta,target,held_old),receiver_coordinate_change=float(np.max(abs(delta[:p.hardware.shape[1]+p.smooth.shape[1]]))))
            arm_results[arm]=dict(training=meta,variants=variants,minimum_elevation_deg=float(elevation.min()))
        record=dict(seed=fold['seed'],split=split,training_target_indices=np.flatnonzero(train_target),held_target_indices=np.flatnonzero(held_target),arms=arm_results)
        folds.append(record);write(out/f"seed-{fold['seed']}.json",record)
        print(inv['job']['label'],fold['seed'],'held',[(a,[(k,round(v['prediction']['rms_hz'],1)) for k,v in r['variants'].items()]) for a,r in arm_results.items()],flush=True)
    write(out/'result.json',dict(job=inv['job'],branch_id=annotation['track_id'],full=full,folds=folds,
        diagnostic_only=True,no_accepted_associations=True,not_an_independent_identity_validation=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('inventory','inclusion','output'):p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
