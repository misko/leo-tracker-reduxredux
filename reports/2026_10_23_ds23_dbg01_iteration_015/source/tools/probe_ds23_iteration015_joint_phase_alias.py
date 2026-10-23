"""Exact nonlinear phase/alias nomination for the longest remaining curved source."""

import copy
from pathlib import Path
import signal
import numpy as np

import probe_ds23_iteration015_recovery as binding
from ds23_joint_phase_alias_nomination import integrate
from probe_ds23_single_curved_reentry import predictive_track_data
from probe_ds23_family_cavity_nominations import candidate_prediction
from probe_ds23_family_cavity_position import fit_configuration
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha

runner=binding.runner;paths=binding.paths.paths
OUT=runner.RAW/'joint_phase_alias_nomination'


def one(case):
    runner.configure();d,cov,kind,_=paths.parent(case)
    if kind!='default':raise ValueError('preserve support parent with an explicit adapter before using this ablation')
    occupied=set().union(*(set(c['accepted_observation_ids']) for c in cov.values()))
    eligible=[i for i in d['scan'].curved if len(d['scan'].tracks[i]['times'])>=12 and not occupied&set(d['scan'].tracks[i]['observation_ids'])]
    eligible=sorted(eligible,key=lambda i:(-np.ptp(d['scan'].tracks[i]['times']),-len(d['scan'].tracks[i]['times']),d['scan'].tracks[i]['key']))[:1]
    result=dict(case=case,targets=[],trials=[],selected=None)
    for index in eligible:
        saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km']);p=paths.build(d,kind,'c0',saved['phase_reference']);row=next(k for k,i in enumerate(p.members) if i==index);data=predictive_track_data(d,p,x,row)
        def geometry(phase):
            f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=phase)
            return f*data['q'],np.min(e,axis=1)>=0
        quadrature=integrate(data['values'],data['radio']@data['coefficient'][:data['radio_width']],data['base_covariance'],np.linspace(-15,15,121),d['all_means'],d['widths'],d['model']['nu'],geometry)
        pool=[int(j) for j in np.argsort(quadrature['score']) if np.isfinite(quadrature['score'][j])][:7]
        old=read(runner.RAW/'single_curve_reentry'/(case+'_nominations.json'));target=next(r for r in old['targets'] if r['target']['component']==d['scan'].tracks[index]['key'])
        for old_offer in [target['best'],target['original']]:
            if old_offer is not None and old_offer['candidate_index'] not in pool:pool.append(old_offer['candidate_index'])
        nominees=[]
        for j in pool:
            alias=[int(quadrature['aliases'][j])];c=candidate_prediction(dict(d,x=x),data,j,alias)
            c.update(joint_phase_score=float(quadrature['score'][j]),joint_grid_phase_s=float(quadrature['peak_phase_s'][j]));nominees.append(c)
        nominees.sort(key=lambda r:r['score']);qualified=[r for r in nominees if r['qualified']]
        record=dict(track_index=index,component=d['scan'].tracks[index]['key'],points=len(data['times']),candidates=nominees,
            original_nomination_best=target['best'],nominal_original=target['original'],grid_ranking=[dict(norad=int(d['scan'].norads[j]),score=float(quadrature['score'][j]),phase_s=float(quadrature['peak_phase_s'][j]),alias=int(quadrature['aliases'][j])) for j in pool])
        result['targets'].append(record);write(OUT/(case+'_RF_nominations.json'),dict(result,RF_nomination_frozen_before_new_position_fits=True))
        for offer in qualified[:1]:
            node=copy.deepcopy(d['node']);keep=d['keep'].copy();node['seed']['rows'][row].update(candidate_index=offer['candidate_index'],candidate_norad=offer['norad']);node['aliases'][row]=int(offer['aliases'][0]);keep[p.slices[row]]=True
            labels=sorted({r['candidate_index'] for r in node['seed']['rows']});means=d['all_means'][labels]
            trial=fit_configuration(dict(d,keep=keep),node,d['entries'],means);trial.update(mask=keep,added_curved_points=int(keep.sum()-d['keep'].sum()),additions=[dict(component=record['component'],candidate_index=offer['candidate_index'],norad=offer['norad'],alias=int(offer['aliases'][0]))])
            if trial['paired_valid']:
                dd=dict(d,node=node,keep=keep,means=means,arms=trial['arms']);coverage={a:runner.engine.baseline.inventory(dd,a) for a in trial['arms']}
                trial['coverage']=coverage;trial['accepted']=all(set(cov[a]['accepted_observation_ids'])<=set(c['accepted_observation_ids']) for a,c in coverage.items())
            else:trial['accepted']=False
            result['trials'].append(trial)
            if trial['accepted']:result['selected']=trial
            print(case,'phase/alias nominee',offer['norad'],offer['aliases'],'paired',trial['paired_valid'],'accepted',trial['accepted'],flush=True)
    write(OUT/(case+'.json'),result)


def main():
    binding.configure('paths');OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve joint phase/alias experiment')
    cases=read(runner.RAW/'protocol.json')['cases'];write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),numerical_helper_sha256=sha(Path(integrate.__code__.co_filename)),
        hypothesis='an alias chosen only at the prior mean or a linearized phase score may omit a clean curved source identity',
        maximum_wholly_unused_curved_sources_per_case=1,ranking='longest span, then points, after qualified graph recovery',
        every_causal_candidate_and121nonlinear_phase_values_from_minus15to15_used=True,
        source_calibration_excluded_and_parent_radio_posterior_frozen_for_nomination=True,
        proper_original_phase_prior_and_trapezoidal_phase_quadrature_with_nearest_alias_per_phase=True,
        nomination_is_not_a_calibrated_identity_posterior_or_full_wrapped_probability=True,
        best7_plus_old_best_and_original_are_refined_with_original_physical_modes=True,
        only_best_phase_qualified_refined_nominee_gets_original5x48_and_near_feasible_budget=True,
        all_original_point_IDs_and_residual_physical_visibility_and_phase_gates_retained=True,
        no_GPS_following_TLE_new_RF_IQ_or_phase_limit_increase=True))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s joint phase/alias cap')));signal.alarm(600)
    for case in cases:one(case)
    signal.alarm(0);write(OUT/'execution.json',dict(all_terminal=True,all_passed=True))


if __name__=='__main__':main()
