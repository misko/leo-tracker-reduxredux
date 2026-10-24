"""Recover unused native GLRT after RF-qualified curved-family graph recovery.

New temporal paths remain predictive-only. The selected graph parent is frozen
by existing paired gates and added-point ordering, never geographic accuracy.
"""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.linalg import block_diag

import run_ds23_dbg01_iteration_008 as runner
import report_ds23_dbg01_iteration_004 as graph
import ds23_temporal_predictive_recovery as temporal
import ds23_graph_seeded_path_recovery as native
from ds23_active_mode_support import make_problem
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_family_cavity import predictive_density_reference
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from dbg01_unassociated import ownership
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import summary,cached
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'graph_seeded_paths'
METHODS={'independent':0.,'persistent5s':5.}


def parent(case):
    original=runner.engine.current_setup(case);graph.RAW=runner.RAW
    initial=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))
    support=read(runner.RAW/'support_aware_reentry'/(case+'_audited.json'))
    selected,kind=graph.graph_policy(original,initial,support)
    data,arms,cov=graph.residual_and_coverage(original,selected,kind)
    protected={r['candidate_index'] for r,sl in zip(original['base'].rows,original['base'].slices,strict=True) if original['keep'][sl].any()}
    protected.update(e['candidate_index'] for e in original['entries'])
    data=dict(data,arms=arms,original_protected=protected)
    return data,cov,kind,selected


def build(d,kind,arm,reference):
    if kind=='support':
        p=make_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],d['original_protected'])
    else:p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],[])
    attach_event_predictive(p,d['entries'],d['powers'])
    return cached(p)


def discover(d,cov,kind,basis):
    occupied=set().union(*(set(c['accepted_observation_ids']) for c in cov.values()))
    observations=sorted([o for o in d['observations'] if o['observation_id'] not in occupied],
        key=lambda o:(o['receiver'],o['channel'],o['actual_rf_hz'],o['time_s'],o['observation_id']))
    if not observations:return dict(methods={m:dict(lanes=[],paths=[],selected=[]) for m in METHODS},unused_points=0)
    predictions={a:native.predictions(build(d,kind,a,s['phase_reference']),np.asarray(s['endpoint_east_north_km']),d['powers'],observations,basis)
        for a,s in d['arms'].items()}
    lanes=sorted({(o['receiver'],o['channel'],o['actual_rf_hz']) for o in observations});families=len(predictions['c0']['active'])
    values=np.array([o['measured_cfo_hz'] for o in observations]);rng=np.random.default_rng(2026102208)
    penalty=float(2*np.log(len(METHODS)*len(lanes)*families));results={m:dict(lanes=[],paths=[],selected=[]) for m in METHODS}
    for lane in lanes:
        ix=np.array([i for i,o in enumerate(observations) if (o['receiver'],o['channel'],o['actual_rf_hz'])==lane])
        if len(ix)<8:continue
        local=[observations[i] for i in ix];times=np.array([o['time_s'] for o in local]);y=values[ix]
        pred={a:{k:(v[ix] if k in ['mean','variance','native_sigma','visible','features'] else v) for k,v in pr.items()} for a,pr in predictions.items()}
        density=temporal.density_predictions(pred['c0'],y);permutations=[rng.permutation(len(y)) for _ in range(19)]
        for method,tau in METHODS.items():
            h=temporal.hmm(times,density,pred['c0']['visible'],tau)
            controls=[temporal.hmm(times,temporal.density_predictions(pred['c0'],y[order],order),pred['c0']['visible'],tau)['log_ratio_vs_clutter'] for order in permutations]
            threshold=max(controls)+2*np.log(20);lane_pass=h['log_ratio_vs_clutter']>threshold
            results[method]['lanes'].append(dict(lane=lane,points=len(y),native_log_ratio=h['log_ratio_vs_clutter'],
                permutation_log_ratios=controls,threshold=threshold,passed=bool(lane_pass)))
            for state,indices in temporal.path_indices(times,h['states']):
                checks={a:temporal.path_identity(pr,y,indices) for a,pr in pred.items()};j=state-1
                passed=bool(lane_pass and all(c['best_local_index']==j and c['probabilities'][j+1]>=.99 and c['gain_vs_clutter']>penalty
                    and c['maximum_marginal_SD_hz']<temporal.PERIOD/20 for c in checks.values())
                    and np.array_equal(checks['c0']['aliases'],checks['fitted_c']['aliases']))
                candidate=pred['c0']['active'][j];key=f"GRAPH_PATH_{method}_{len(results[method]['paths']):03d}"
                fragment=dict(key=key,receiver=lane[0],channel=lane[1],rf_hz=lane[2],candidate_index=candidate,norad=int(d['scan'].norads[candidate]),
                    times=times[indices],values=y[indices]+checks['c0']['aliases']*temporal.PERIOD,observation_ids=[local[i]['observation_id'] for i in indices])
                results[method]['paths'].append(dict(fragment=fragment,checks=checks,passed=passed,points=len(indices),
                    span_s=float(np.ptp(times[indices])),lane_coherence_passed=bool(lane_pass)))
    for method,result in results.items():
        eligible=sorted([p for p in result['paths'] if p['passed']],key=lambda p:-p['checks']['c0']['gain_vs_clutter'])[:24]
        result['selected']=[p['fragment'] for p in eligible]
    return dict(methods=results,unused_points=len(observations),active_families=families,multiplicity_penalty=penalty)


def refit(d,kind,arm):
    reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
    for _ in range(5):
        p=build(d,kind,arm,reference);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
    saved=summary(p,x,d['entries']);saved.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
    c=p.calculate(x);curved=p.curved_calculate(x);g=p.noise_groups[p.keep];u=curved['features'][p.keep]
    w=np.asarray(d['powers'])[g]*curved['noise_precision'][g]/p.point_noise[p.keep]**2
    gram=np.diag(curved['coefficient_prior_precision'])+u.T@(u*w[:,None]);view,values,sigma,groups,_=linear_geometry(p,d['entries'])
    geometry=geometry_features(view,x,0.);features=geometry['features'];bias=np.eye(int(groups.max())+1)[groups]*300.
    direct,_=predictive_density_reference(values-view.q*geometry['intercept']-features@curved['coefficient'],
        np.column_stack((features,bias)),block_diag(np.linalg.inv(gram),np.eye(bias.shape[1])),sigma*np.sqrt(2))
    delta=direct-c['linear_predictive_objective'];change=float(np.max(abs(c['coefficient']-curved['coefficient'])))
    if abs(delta)>2e-5 or change>1e-12:raise ValueError('native path predictive density or calibration does not replay')
    saved['audit']=dict(direct_predictive_density_difference=delta,original_curved_calibration_coefficient_difference=change)
    return saved


def coverage(d,kind,arm,saved):
    p=build(d,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    extended=extend_associations(p,x,retained_metrics(p,x));lookup={t['key']:t for t in d['scan'].tracks}
    explicit=[dict(e,compatible=g['compatible'],association_source='graph_seeded_predictive_path') for e,g in zip(d['entries'],saved['linear_gates'],strict=True)]
    new_keys={e['component'] for e in explicit};new_ids=ownership(explicit);rows=[];collisions=[]
    for r in extended['tracks']:
        if not r['compatible'] or r['component'] in new_keys:continue
        row=dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids']))
        if set(row['observation_ids'])&new_ids:collisions.append(row['component']);continue
        rows.append(row)
    ids=ownership(rows+explicit);allids={o['observation_id'] for o in d['observations']}
    if not ids<=allids:raise ValueError('nonphysical native GLRT ID')
    return dict(associated=len(ids),total_GLRT=len(allids),percent=100*len(ids)/len(allids),associated_tracks=len(rows)+len(explicit),
        accepted_observation_ids=sorted(ids),associations=dict(tracks=rows+explicit),colliding_postfit_extensions_omitted=collisions,
        active_curved_points=int(d['keep'].sum()),predictive_points=sum(e['points'] for e in d['entries']))


def one(case):
    runner.configure();d,cov,kind,selected=parent(case);basis=native.receiver_basis(d['scan'])
    write(OUT/(case+'_parent.json'),dict(case=case,selected=selected,kind=kind,arms=d['arms'],coverage=cov,
        original_protected=sorted(d['original_protected']),receiver_basis=basis.__name__,RF_parent_frozen_before_new_paths=True))
    discovery=discover(d,cov,kind,basis);write(OUT/(case+'_discovery.json'),discovery);methods={}
    for method,proposal in discovery['methods'].items():
        offered=proposal['selected']
        if not offered:methods[method]=dict(accepted=False,reason='no correlated temporal proposal');continue
        scan,entries=native.append_native_paths(d['scan'],d['entries'],offered,basis);dd=dict(d,scan=scan,entries=entries);checks={}
        for arm,saved in d['arms'].items():
            p=build(dd,kind,arm,saved['phase_reference']);checks[arm]=summary(p,np.asarray(saved['endpoint_east_north_km']),entries)['linear_gates'][len(d['entries']):]
        keys=set.intersection(*({g['component'] for g in rows if g['compatible']} for rows in checks.values()))
        chosen=[f for f in offered if f['key'] in keys]
        write(OUT/(case+'_'+method+'_selection.json'),dict(offered=offered,checks=checks,selected=chosen,
            complete_paths_only_no_residual_point_trimming=True,RF_selection_complete_before_cold_fit=True))
        if not chosen:methods[method]=dict(accepted=False,reason='no whole path passes fixed-parent residual gates');continue
        scan,entries=native.append_native_paths(d['scan'],d['entries'],chosen,basis);dd=dict(d,scan=scan,entries=entries)
        arms={a:refit(dd,kind,a) for a in ['c0','fitted_c']};newcov={a:coverage(dd,kind,a,s) for a,s in arms.items()}
        preserved={a:set(cov[a]['accepted_observation_ids'])<=set(newcov[a]['accepted_observation_ids']) for a in arms}
        passed=bool(valid(arms) and all(preserved.values()))
        methods[method]=dict(accepted=passed,paired_valid=bool(valid(arms)),all_parent_IDs_preserved=preserved,
            arms=arms,coverage=newcov,entries=entries,new_points=sum(len(f['times']) for f in chosen),new_paths=len(chosen))
        print(case,method,methods[method]['new_points'],'points, accepted',passed,flush=True)
    write(OUT/(case+'.json'),dict(case=case,methods=methods,parent_kind=kind,primary='persistent5s',
        no_geographic_scoring_or_following_TLE_used=True,original_curved_calibration_membership_equals_graph_parent=True))
    return dict(case=case,status='complete',accepted={k:v['accepted'] for k,v in methods.items()})


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve graph-seeded path experiment')
    write(OUT/'protocol.json',dict(cases=read(runner.RAW/'protocol.json')['cases'],
        source_sha256=sha(Path(__file__)),native_helper_sha256=sha(Path(native.__file__)),temporal_helper_sha256=sha(Path(temporal.__file__)),
        hypothesis='new RF-qualified curved family can explain orphan GLRT that an incumbent-family-only temporal search cannot',
        primary='persistent5s',control='independent',minimum_points=8,minimum_span_s=6,maximum_gap_s=10,maximum_paths=24,
        seed=2026102208,permutation_controls=19,permutation_lane_gate='native ratio > maximum permutation +2log20',
        permutation_is_diagnostic_not_calibrated_p_value=True,Gaussian_identity_probability_is_not_ground_truth=True,
        full_shared_calibration_covariance_in_path_validation_and_final_likelihood=True,
        native_basis_must_numerically_match_original_all_track_basis=True,
        graph_parent_support_modes_and_protected_incumbents_frozen=True,
        all_parent_likelihood_and_association_IDs_must_survive=True,whole_paths_screened_once_no_iterative_pruning=True,
        phase_rounds=5,position_steps=48,regional_center=[37.906,-122.545],box_width_km=25,cold_start_km=[0,0],
        both_c_arms_same_paths_aliases_priors_and_budgets=True,no_GPS_or_following_TLE_or_new_RF=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
