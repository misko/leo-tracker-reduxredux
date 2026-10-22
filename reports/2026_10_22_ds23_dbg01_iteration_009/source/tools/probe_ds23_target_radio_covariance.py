"""Other-track RF covariance on the unchanged restored-mask position problem."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.linalg import block_diag

import repair_ds23_iteration009_targets as repair
from ds23_target_radio_covariance import make_target_problem,retained_covariance_metrics
from ds23_other_track_noise import blocks,validation
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from ds23_family_cavity import predictive_density_reference
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from run_ds23_combined_recovery_full import valid
from evaluate_ds23_phase_refreshed import extend_associations
from dbg01_unassociated import ownership
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'target_radio_covariance'


def fit_one(case,source,method,noise_scale):
    repair.configure();d=repair.engine.current_setup(case);old=d['arms'];component=source['component'];model=source['model']
    keep=d['keep'].copy();k=next(k for k,r in enumerate(d['base'].rows) if r['component']==component);keep[d['base'].slices[k]]=True;d=dict(d,keep=keep)
    nulls=[]
    for arm,saved in old.items():
        for mask_name,mask in [('incumbent',repair.engine.current_setup(case)['keep']),('restored',keep)]:
            dd=dict(d,keep=mask);a=repair.engine.baseline.build(dd,arm,saved['phase_reference']);b=make_target_problem(dd,arm,saved['phase_reference'],component,0.,model['tau_s'])
            x=np.asarray(saved['endpoint_east_north_km']);ca,cb=a.calculate(x),b.calculate(x);delta=ca['negative_twice_elbo']-cb['negative_twice_elbo']
            coefficient=float(np.max(abs(ca['coefficient']-cb['coefficient'])))
            if abs(delta)>1e-5 or coefficient>1e-5:raise ValueError('white covariance implementation null failed')
            nulls.append(dict(arm=arm,mask=mask_name,objective_difference=delta,coefficient_difference=coefficient))
    arms={};coverage={}
    for arm in ['c0','fitted_c']:
        reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
        for _ in range(5):
            p=cached(make_target_problem(d,arm,reference,component,model['alpha'],model['tau_s'],noise_scale))
            result=fit(p,x,iterations=48);x=np.asarray(result['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
        saved=summary(p,x,d['entries']);saved['original_raw_gates']=saved['gates'];saved['gates']=retained_covariance_metrics(p,x)
        saved.update(history=history,final_phase_change_s=history[-1]['phase_change_s']);c=p.calculate(x)
        view,values,sigma,groups,_=linear_geometry(p,d['entries']);g=geometry_features(view,x,0.)
        biases=np.eye(int(groups.max())+1)[groups]*300.;design=np.column_stack((g['features'],biases))
        raw=values-view.q*g['intercept']-g['features']@c['coefficient'];cov=block_diag(np.linalg.inv(c['curved_posterior_gram']),np.eye(biases.shape[1]))
        direct,_=predictive_density_reference(raw,design,cov,sigma*np.sqrt(2));delta=direct-c['linear_predictive_objective']
        if abs(delta)>2e-5:raise ValueError('target-covariance predictive density does not replay')
        saved['audit']=dict(predictive_density_difference=delta,curved_calibration_coefficient_difference=float(np.max(abs(c['coefficient']-p.curved_calculate(x)['coefficient']))))
        arms[arm]=saved;extended=extend_associations(p,x,saved['gates']);lookup={t['key']:t for t in d['scan'].tracks}
        rows=[dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extended['tracks']];ids=ownership(rows)
        coverage[arm]=dict(associated=len(ids),total_GLRT=len(d['observations']),percent=100*len(ids)/len(d['observations']),
            associated_tracks=sum(r['compatible'] for r in rows),accepted_observation_ids=sorted(ids),associations=extended,
            active_curved_points=int(keep.sum()),predictive_points=sum(e['points'] for e in d['entries']))
    result=dict(case=case,method=method,arms=arms,coverage=coverage,paired_valid=bool(valid(arms)),mask=keep,
        component=component,covariance=model,noise_scale=noise_scale,nulls=nulls,all_original_likelihood_points_preserved=True,
        target_raw_deterministic_checks_retained_whitened_stochastic_checks=True)
    write(OUT/(case+'_'+method+'.json'),result);print(case,method,'paired',result['paired_valid'],flush=True)
    return dict(case=case,method=method,status='complete',paired_valid=result['paired_valid'])


def main():
    repair.configure();OUT.mkdir(exist_ok=True);tasks=[];selections=[]
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve target-covariance experiment')
    for case in read(repair.runner.RAW/'protocol.json')['cases']:
        d=repair.engine.current_setup(case);meta=d['scan'].fixed_window_noise;lookup=meta['per_observation_noise_sigma_hz'] if meta['extra_parameter_BIC_gain']>0 else {}
        for source in read(repair.runner.RAW/'other_track_radio_noise'/(case+'.json'))['rows']:
            if not source['covariance_qualified']:continue
            target=d['scan'].tracks[source['track_index']];excluded=set(source['target_observation_ids'])
            tracks=[t for t in d['scan'].tracks if t['receiver']==target['receiver'] and not excluded&set(t['observation_ids'])]
            training=validation(blocks(tracks,lookup,d['scan'].radio_sigma_hz),source['model']);scale=float(np.sqrt(training['profiled_variance_ratio']))
            selections.append(dict(case=case,component=source['component'],training_amplitude=training,noise_scale=scale))
            tasks.extend([(case,source,'shape_only',1.),(case,source,'training_scaled',scale)])
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),helper_sha256=sha(Path(make_target_problem.__code__.co_filename)),
        selections=selections,model_frozen_from_other_same_RX_tracks_before_position_fits=True,
        target_RF_contrasts_validate_shape_but_do_not_supply_variance_scale=True,
        models=['shape_only','training_scaled'],each_uses_same_restored_original_points_labels_aliases_and_other_priors=True,
        target_only_covariance_block_all_other_noise_blocks_unchanged=True,
        raw_RMS_bias_alias_horizon_mean_slope_quadratic_and_step_checks_retained=True,
        fixed_noise_screen_thresholds_also_applied_to_whitened_profile_and_conditional_innovations=True,
        original_checks_for_every_other_curved_and_predictive_track_unchanged=True,
        both_c_arms_same_kernel_scale_observations_and5x48cold_budget=True,
        no_following_TLE_GPS_new_RF_or_new_nuisance_coordinates=True,
        prior_radio_temporal_experiment_changed_all_track_covariance_and_kept_raw_ACF_gates=True,
        primary='training_scaled',control='shape_only'))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run_task,tasks))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


def run_task(task):return fit_one(*task)


if __name__=='__main__':main()
