"""Apply the existing jackknife10s curvature rule to whole unused sources."""

from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path
import signal
import numpy as np

import probe_ds23_iteration010_paths as binding
from ds23_short_whole_curve_view import promote
from ds23_supported_curvature import curvature_evidence
from probe_ds23_linear_family_groups import group_data,residual_checks
from probe_ds23_family_cavity_nominations import candidate_prediction
from ds23_family_cavity import coarse_phase_scores
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from audit_ds23_algo01_coverage import retained_metrics
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=binding.runner.RAW/'short_whole_curves'


def choose_targets(d,cov):
    occupied=set().union(*(set(v['accepted_observation_ids']) for v in cov.values()));rows=[]
    for i,t in enumerate(d['scan'].tracks):
        if i in d['scan'].curved or set(t['observation_ids'])&occupied or np.ptp(t['times'])>=20:continue
        evidence=curvature_evidence(t)
        if evidence['qualified']:rows.append(dict(track_index=i,component=t['key'],points=len(t['times']),span_s=float(np.ptp(t['times'])),curvature=evidence))
    return sorted(rows,key=lambda r:(-r['points'],-r['span_s'],r['component']))[:2]


def nominate(d,kind,target):
    saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km']);p=binding.paths.build(d,kind,'c0',saved['phase_reference']);datum=group_data(d,p,x,[target['track_index']])
    f,e=phase_frequency_grid(d['scan'].sky,datum['times'],*latlon(x),phase_seconds=d['all_means'])
    plus=phase_frequency_grid(d['scan'].sky,datum['times'],*latlon(x),phase_seconds=d['all_means']+.01)[0]
    minus=phase_frequency_grid(d['scan'].sky,datum['times'],*latlon(x),phase_seconds=d['all_means']-.01)[0]
    coarse=coarse_phase_scores(datum['values'],datum['radio']@datum['coefficient'][:datum['radio_width']],datum['q']*f,datum['q']*(plus-minus)/.02,d['widths'],datum['base_covariance'],datum['groups'])
    scores=np.where(e.min(axis=1)>=0,coarse['score'],np.inf);pool=[int(j) for j in np.argsort(scores) if np.isfinite(scores[j])][:7];arms={}
    for arm,s in d['arms'].items():
        xx=np.asarray(s['endpoint_east_north_km']);pp=binding.paths.build(d,kind,arm,s['phase_reference']);data=group_data(d,pp,xx,[target['track_index']]);rows=[]
        for j in pool:
            c=candidate_prediction(dict(d,x=xx),data,j,coarse['aliases'][j]);c['fixed_radio_checks']=residual_checks(data,c);rows.append(c)
        arms[arm]=sorted(rows,key=lambda c:c['score'])
    best=arms['c0'][0] if arms['c0'] else None;other=next((c for c in arms['fitted_c'] if best and c['candidate_index']==best['candidate_index']),None)
    qualified=bool(best and other and all(c['qualified'] and all(g['compatible'] for g in c['fixed_radio_checks']) for c in [best,other]) and np.array_equal(best['aliases'],other['aliases']))
    offer=dict(target,candidate_index=best['candidate_index'],norad=best['norad'],alias=int(best['aliases'][0])) if qualified else None
    return dict(target=target,arms=arms,offer=offer,all_new_points_excluded_from_nomination_calibration=True)


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('480s short-curve prototype cap')));signal.alarm(480)
    binding.configure();d,cov,kind,_=binding.paths.parent(case);targets=choose_targets(d,cov);nominations=[nominate(d,kind,t) for t in targets]
    write(OUT/(case+'_nominations.json'),dict(case=case,targets=nominations,RF_choices_sealed_before_position_fits=True))
    original=binding.paths.build(d,kind,'c0',d['arms']['c0']['phase_reference'])
    active={r['candidate_index'] for r,sl in zip(original.rows,original.slices,strict=True) if original.keep[sl].any()}|{e['candidate_index'] for e in d['entries']}
    d=dict(d,original_protected=active&set(original.supported));nulls=[]
    for a,s in d['arms'].items():
        x=np.asarray(s['endpoint_east_north_km']);p=binding.paths.build(d,'support',a,s['phase_reference']);delta=p.calculate(x)['negative_twice_elbo']-s['negative_twice_elbo']
        if abs(delta)>1e-5:raise ValueError('support adapter changed the graph parent before adding data')
        nulls.append(dict(arm=a,objective_difference=delta))
    offers=[n['offer'] for n in nominations if n['offer']];trials=[]
    for size in range(1,len(offers)+1):
        for subset in combinations(offers,size):
            changed,added=promote(d,original,subset);arms={a:binding.paths.refit(changed,'support',a) for a in ['c0','fitted_c']};coverage={};audits=[]
            for a,saved in arms.items():
                p=binding.paths.build(changed,'support',a,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km']);delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
                if abs(delta)>1e-5:raise ValueError('short-curve endpoint objective changed')
                assert_curved_gate_replay(saved['gates'],retained_metrics(p,x));coverage[a]=binding.paths.coverage(changed,'support',a,saved);audits.append(dict(arm=a,objective_replay_difference=delta))
            retained={a:set(cov[a]['accepted_observation_ids'])<=set(coverage[a]['accepted_observation_ids']) for a in arms}
            passing=bool(valid(arms) and all(s['final_phase_change_s']<=.01 for s in arms.values()) and all(retained.values()))
            trials.append(dict(arms=arms,coverage=coverage,paired_valid=bool(valid(arms)),accepted=passing,additions=added,offers=list(subset),
                added_curved_points=sum(t['points'] for t in added),node=changed['node'],mask=changed['keep'],powers=changed['powers'],means=changed['means'],
                new_curved_indices=changed['scan'].curved,all_parent_accepted_IDs_preserved=retained,audits=audits))
            write(OUT/(case+'_checkpoint.json'),dict(case=case,trials=trials));print(case,'short curves',trials[-1]['added_curved_points'],'accepted',passing,flush=True)
    passing=[t for t in trials if t['accepted']];chosen=sorted(passing,key=lambda t:(-t['added_curved_points'],tuple(a['component'] for a in t['additions'])))[0] if passing else None
    write(OUT/(case+'.json'),dict(case=case,trials=trials,selected=chosen,parent_kind=kind,parent_nulls=nulls,original_protected=sorted(d['original_protected']),
        independent_short_curvature_required=True,no_GPS_or_following_TLE_or_original_point_deletion=True))
    signal.alarm(0);return dict(case=case,status='complete',targets=len(targets),offers=len(offers),accepted=chosen is not None)


def main():
    binding.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve short whole-curve prototype')
    cases=read(binding.runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),adapter_sha256=sha(Path(promote.__code__.co_filename)),
        curvature_helper_sha256=sha(Path(curvature_evidence.__code__.co_filename)),
        rule='existing10s/min12points/250Hz linear RMS/>10 quadratic BIC under every single-point deletion',
        whole_original_unused_sources_only_no_trimming_or_new_fragments=True,maximum_targets=2,ranking='points,span,component',
        full_causal_catalogue_coarse_then_best7_each_refined_in_both_c_arms=True,
        same_c0_nominee_aliases_and_fixed_radio_checks_in_both_arms=True,
        at_most_three_nonempty_whole_curve_subsets=True,original_cross_RX_power_rule_for_new_families_old_powers_frozen=True,
        old_active_orbit_support_preserved_and_new_one_owner_shape_modes_simplified=True,
        paired_original_gates_phase_convergence_and_all_parent_accepted_IDs_required=True,
        cold_start=[0,0],phase_rounds=5,steps_per_round=48,both_c_arms_matched=True,
        no_GPS_future_TLE_new_RF_or_parameter_threshold_tuning=True,experimental_no_ALGO_release=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
