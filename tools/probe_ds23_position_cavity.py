"""Cold family-excluded position fits and local position-mixture nominations.

Only other curved families estimate position/calibration during nomination.
Fixed original labels, aliases, likelihood powers and priors remain conditional
inputs; this is not an untouched validation of those data-derived choices.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

import probe_ds23_family_cavity_nominations as old
import probe_ds23_family_cavity_position as position
from ds23_position_cavity import normal_grid,reweight_nodes,mixture_score
from ds23_position_information import marginal_position_information
from ds23_height_problem import geometry_features
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import refit
from run_algo01_ds23_sample import ROOT,read,write,sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid

OUT=ROOT/'reports/2026_10_22_ds23_position_cavity'
CASES=['DS23-0268','DS23-0080','DS23-0405','DS23-0240']
VARIANTS=['point_cavity','quadrature_cavity']


def position_covariance(p,x,powers):
    c=p.calculate(x);coefficient=c['coefficient'];columns=[]
    for k in range(2):
        delta=np.zeros(2);delta[k]=.01;values=[]
        for z in [x+delta,x-delta]:
            g=geometry_features(p,z,0.);values.append(p.q*g['intercept']+g['features']@coefficient)
        columns.append((values[0]-values[1])/.02)
    j=np.column_stack(columns);u=c['features'];keep=p.keep
    w=powers[p.noise_groups[keep]]*c['noise_precision'][p.noise_groups[keep]]/p.point_noise[keep]**2
    information=marginal_position_information(j[keep],u[keep],w,c['coefficient_prior_precision'])
    covariance=np.linalg.inv(information);np.linalg.cholesky(covariance)
    return covariance


def prove_exclusion(p,x):
    """Check the actual, uncached numerical objective after perturbing held CFOs."""
    if not np.any(~p.keep):raise ValueError('a cavity must exclude observations')
    original=p.values.copy();checks=[]
    for delta in [np.zeros(2),np.array([.01,-.01]),np.array([-.01,.01])]:
        z=np.clip(x+delta,p.lower,p.upper);before=p.calculate(z)
        p.values[~p.keep]+=12345.
        try:after=p.calculate(z)
        finally:p.values[:]=original
        loss=abs(after['negative_twice_elbo']-before['negative_twice_elbo'])
        coef=float(np.max(abs(after['coefficient']-before['coefficient'])))
        if loss>1e-9 or coef>1e-10:raise ValueError('held CFO entered position/calibration objective')
        checks.append(dict(position=z,loss_difference=loss,coefficient_difference=coef))
    return checks


def coarse(d,data,x):
    f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
    plus,_=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)
    minus,_=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)
    result=old.coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],
        f*data['q'],(plus-minus)/.02*data['q'],d['widths'],data['base_covariance'],data['groups'])
    result['score']=np.where(e.min(axis=1)>=0,result['score'],np.inf)
    return result


def compact(row):
    return {k:v for k,v in row.items() if k not in ['prior_covariance','prior_mean','calibration_slots']}


def one(case):
    paths={v:OUT/v/(case+'_nominations.json') for v in VARIANTS}
    if all(p.exists() for p in paths.values()):return dict(case=case,status='already_terminal')
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s position-cavity nomination cap')));signal.alarm(600)
    try:
        d=old.setup(case);base=d['base'];families=sorted({r['candidate_index'] for r,s in zip(base.rows,base.slices,strict=True) if d['keep'][s].any()})
        rows={v:[] for v in VARIANTS};cavities=[]
        for target in families:
            keep=d['keep'].copy()
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row['candidate_index']==target:keep[sl]=False
            if not keep.any():raise ValueError('no other curved calibration family')
            cavity=refit(d['scan'],d['node'],keep,'c0',d['powers'],d['means'],d['model'],[],[])
            if cavity['final_phase_change_s']>.01:
                skipped=dict(original_index=target,original_norad=int(d['scan'].norads[target]),
                    candidates=[],original=None,best=None,predictive_gain=None,
                    skipped_reason='other_family_position_phase_not_converged',
                    final_phase_change_s=cavity['final_phase_change_s'])
                for variant in VARIANTS:rows[variant].append(skipped.copy())
                cavities.append(dict(original_index=target,original_norad=int(d['scan'].norads[target]),fit=cavity,
                    calibration_mask=keep,skipped_reason=skipped['skipped_reason']))
                print(case,int(d['scan'].norads[target]),'left unresolved: other-family phase change',cavity['final_phase_change_s'],flush=True)
                continue
            x=np.asarray(cavity['endpoint_east_north_km']);reference=np.asarray(cavity['phase_reference'])
            center_d=dict(d,x=x,reference=reference);center=old.family_data(center_d,target);center['target']=target
            covariance=position_covariance(center['p'],x,d['powers']);grid=normal_grid(x,covariance,center['p'].lower,center['p'].upper)
            exclusion=prove_exclusion(center['p'],x)
            nodes=[];coarse_rows=[];loss=[];center_index=None
            for node in grid['positions']:
                nd=dict(center_d,x=node);data=center if np.max(abs(node-x))<1e-10 else old.family_data(nd,target);data['target']=target
                if data is center:center_index=len(nodes)
                nodes.append((nd,data));coarse_rows.append(coarse(nd,data,node));loss.append(data['p'].calculate(node)['negative_twice_elbo'])
            if center_index is None:raise ValueError('central quadrature node missing')
            logw=reweight_nodes(grid['positions'],x,covariance,grid['log_weights'],loss)
            mixtures=mixture_score(np.array([c['score'] for c in coarse_rows]),logw)
            metadata=dict(original_index=target,original_norad=int(d['scan'].norads[target]),members=center['members'],
                held_observation_ids=center['held_ids'],held_points=len(center['values']),coarse_candidate_count=len(d['scan'].norads),
                all_held_points_disjoint_from_calibration=True,cavity_phase_change_s=center['cavity_phase_change_s'],
                cavity_position=x,cavity_position_covariance_km2=covariance)
            cache={}
            def predict(k,j,aliases):
                key=(k,j,tuple(aliases))
                if key not in cache:cache[key]=compact(old.candidate_prediction(*nodes[k],j,aliases))
                return cache[key]
            for variant in VARIANTS:
                scores=coarse_rows[center_index]['score'] if variant=='point_cavity' else mixtures
                pool=[target]+[int(j) for j in np.argsort(scores) if np.isfinite(scores[j]) and j!=target][:7];candidates=[]
                for j in pool:
                    anchor=center_index if variant=='point_cavity' else int(np.argmin(np.array([c['score'][j] for c in coarse_rows])-2*logw))
                    aliases=coarse_rows[anchor]['aliases'][j].tolist()
                    if variant=='point_cavity':record=dict(predict(center_index,j,aliases))
                    else:
                        components=[predict(k,j,aliases) for k in range(len(nodes))]
                        record=dict(candidate_index=j,norad=int(d['scan'].norads[j]),aliases=aliases,
                            score=float(mixture_score([r['score'] for r in components],logw)),
                            qualified=all(r['qualified'] for r in components),components=components,
                            all_components_share_aliases=True)
                    candidates.append(record)
                original=next(r for r in candidates if r['candidate_index']==target)
                eligible=sorted([r for r in candidates if r['qualified'] and r['candidate_index']!=target],key=lambda r:r['score'])
                best=eligible[0] if eligible else None
                rows[variant].append(dict(metadata,candidates=candidates,original=original,best=best,
                    predictive_gain=original['score']-best['score'] if best else None,
                    search_penalty=float(2*np.log(len(d['scan'].norads)))))
            cavities.append(dict(original_index=target,original_norad=int(d['scan'].norads[target]),fit=cavity,
                position_covariance_km2=covariance,positions=grid['positions'],Gaussian_log_weights=grid['log_weights'],
                log_weights=logw,other_family_losses=loss,retained_Gaussian_mass=grid['retained_Gaussian_mass'],
                held_CFO_perturbation_checks=exclusion,calibration_mask=keep,
                conditional_on_fixed_original_other_labels_aliases_powers_and_Gamma_covariance=True))
            print(case,int(d['scan'].norads[target]),'cavity',x.tolist(),'gains',[rows[v][-1]['predictive_gain'] for v in VARIANTS],flush=True)
        for variant,path in paths.items():
            write(path,dict(case=case,status='complete',variant=variant,families=rows[variant],cavities=cavities,
                reference_position_used=False,no_RF_GPS_future_TLE_or_point_deletion=True,
                source_incumbent_sha256=sha(d['binding']),seconds=time.monotonic()-began))
        result=dict(case=case,status='complete',seconds=time.monotonic()-began)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc),seconds=time.monotonic()-began)
        for path in paths.values():
            if not path.exists():write(path,result)
    finally:signal.alarm(0)
    return result


def positions(case):
    result={}
    for variant in VARIANTS:
        directory=OUT/variant
        result[variant]=position.one(case,nominations_dir=directory,output_dir=directory/'position')['status']
    return dict(case=case,status=result)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['nominations','positions'],required=True)
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(cases=CASES,primary='quadrature_cavity',control='point_cavity',workers=4,
        family_position_fit_cold_start=[0,0],regional_width_km=25,other_curved_families_only=True,
        cavity_phase_rounds=5,cavity_position_steps=48,quadrature_order=3,quadrature_nodes_at_most=9,
        covariance_conditional_on_Gamma_precisions=True,quadrature_reweighted_by_other_family_RF_density=True,
        all_component_geometry_phase_and_convergence_required_for_alternative=True,
        nonconverged_cavity_leaves_only_that_family_unresolved_other_offers_preserved=True,
        original_data_derived_other_labels_aliases_and_powers_are_conditional_inputs=True,
        full_causal_catalogue_coarse_screen_then_original_plus7_refined_candidates=True,
        final_fit_and_adoption_unchanged_from_conditional_family_replacement=True,
        primary_adoption='equal identity priors; paired original gates; positive normalized c0 gain',
        matched_c0_fitted_c_observations_priors_and_search_budgets=True,
        no_GPS_RF_future_TLE_or_point_deletion=True,per_case_nomination_seconds=600,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_position_cavity.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('position cavity protocol changed')
    if not path.exists():write(path,protocol)
    for variant in VARIANTS:(OUT/variant/'position').mkdir(parents=True,exist_ok=True)
    function=one if args.stage=='nominations' else positions
    if args.stage=='positions' and not read(OUT/'nomination_execution.json')['all_terminal']:raise ValueError('nominations not terminal')
    with ProcessPoolExecutor(max_workers=4) as pool:results=[f.result() for f in as_completed([pool.submit(function,c) for c in CASES])]
    write(OUT/('nomination_execution.json' if args.stage=='nominations' else 'position_execution.json'),dict(rows=results,all_terminal=True,no_geographic_evaluation_yet=True))
    if args.stage=='positions':
        for variant in VARIANTS:
            write(OUT/variant/'position/execution.json',dict(rows=[read(OUT/variant/'position'/(c+'.json')) for c in CASES],all_terminal=True))


if __name__=='__main__':main()
