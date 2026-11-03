"""One long unused source may nominate a new predictive family without a mate."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

import probe_ds23_iteration012_existing_recovery as binding
import probe_ds23_linear_family_groups as groups
import probe_ds23_new_family_prediction as prediction
from ds23_new_family_prediction import wrapped_curve_score
from ds23_family_cavity import coarse_phase_scores
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=binding.runner.RAW/'single_source_new_family'


def eligible(d,cov):
    occupied=set().union(*(set(v['accepted_observation_ids']) for v in cov.values()))
    rows=[i for i,t in enumerate(d['scan'].tracks) if i not in d['scan'].curved and len(t['times'])>=8
        and np.ptp(t['times'])>=20 and not occupied&set(t['observation_ids'])]
    return sorted(rows,key=lambda i:(-np.ptp(d['scan'].tracks[i]['times']),-len(d['scan'].tracks[i]['times']),d['scan'].tracks[i]['key']))[:1]


def offer(pair,penalty):
    if not all(pair.values()):return False
    best={a:rows[0] for a,rows in pair.items()}
    return bool(len({r['candidate_index'] for r in best.values()})==1 and
        np.array_equal(best['c0']['aliases'],best['fitted_c']['aliases']) and
        all(r['qualified'] and r['all_fixed_radio_checks_pass'] and r['wrapped_null_gain']>penalty and
            len(pair[a])>=2 and pair[a][1]['score']-r['score']>2*np.log(100) for a,r in best.items()))


def one(case):
    binding.configure('paths');d,cov,kind,_=binding.paths.paths.parent(case);targets=eligible(d,cov);nominations=[];trials={}
    for index in targets:
        saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km']);p=binding.paths.paths.build(d,kind,'c0',saved['phase_reference']);data=groups.group_data(d,p,x,[index])
        f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
        plus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)[0]
        minus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)[0]
        coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],data['q']*f,data['q']*(plus-minus)/.02,d['widths'],data['base_covariance'],data['groups'])
        ranking=np.where(e.min(axis=1)>=0,coarse['score'],np.inf);pool=[int(j) for j in np.argsort(ranking) if np.isfinite(ranking[j])][:7];pair={}
        penalty=float(2*np.log(max(1,len(targets))*len(d['scan'].norads)*27))
        active={r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}|{e['candidate_index'] for e in d['entries']}
        for arm,s in d['arms'].items():
            xx=np.asarray(s['endpoint_east_north_km']);pp=binding.paths.paths.build(d,kind,arm,s['phase_reference']);datum=groups.group_data(d,pp,xx,[index]);rows=[]
            for j in pool:
                c=groups.candidate_prediction(dict(d,x=xx),datum,j,coarse['aliases'][j]);checks=groups.residual_checks(datum,c)
                lifted=datum['values']+np.asarray(c['aliases'])[datum['groups']]/4.4e-6
                null=wrapped_curve_score(datum['times'],lifted,datum['noise'])
                c.update(fixed_radio_checks=checks,all_fixed_radio_checks_pass=all(g['compatible'] for g in checks),wrapped_null_score=null,wrapped_null_gain=null-c['score'])
                rows.append(c)
            pair[arm]=sorted(rows,key=lambda r:r['score'])
        passes=offer(pair,penalty) and pair['c0'][0]['candidate_index'] not in active
        record=dict(track_index=index,component=d['scan'].tracks[index]['key'],points=len(data['times']),arms=pair,multiplicity_penalty=penalty,offered=passes)
        nominations.append(record);write(OUT/(case+'_nominations.json'),dict(rows=nominations,RF_choices_frozen_before_position_fit=True))
        if passes:
            best=pair['c0'][0];entry=dict(data['members'][0],candidate_index=best['candidate_index'],norad=best['norad'],alias=int(best['aliases'][0]),association_source='single_source_new_family_prediction')
            # The original new-family build matches only the ordinary parent.
            # These targets currently occur on the default parent; do not silently
            # change an existing support-aware graph model through this adapter.
            if kind!='default':raise ValueError('single-family adapter requires unchanged default graph parent')
            for method,physical in [('phase_only',False),('physical_control',True)]:
                arms={a:prediction.refit(d,a,[entry],physical) for a in ['c0','fitted_c']}
                accepted=bool(valid(arms) and all(r['final_phase_change_s']<=.01 and np.max(abs(np.asarray(r['new_family_phases_s'])))<=15.000001 for r in arms.values()))
                trials[method]=dict(arms=arms,entries=[entry],paired_valid=bool(valid(arms)),accepted=accepted,physical_modes=physical)
                print(case,method,len(data['times']),'points, accepted',accepted,flush=True)
    write(OUT/(case+'.json'),dict(case=case,nominations=nominations,trials=trials,primary='phase_only',parent_kind=kind,
        all_new_points_predictive_only_no_radio_calibration_update=True))
    return dict(case=case,targets=len(targets),trials=len(trials))


def main():
    binding.configure('paths');OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve single-source experiment')
    cases=read(binding.runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),grouped_nomination_sha256=sha(Path(groups.__file__)),
        original_prediction_sha256=sha(Path(prediction.__file__)),
        hypothesis='a long isolated source should not require an incompatible second source to propose a new predictive family',
        maximum_targets_per_case=1,whole_unused_noncalibration_source_min8points_min20s=True,
        full_causal_catalogue_coarse_then_best7_refined_in_both_arms=True,
        original_fixed_radio_residual_gates_and_gap2log100_retained=True,
        proper_wrapped_unresolved_curve_null_gain_must_exceed2log_targets_catalogue_27=True,
        same_candidate_and_alias_in_both_arms=True,primary='phase_only',physical_modes_only_named_control=True,
        original_radio_calibration_and_every_parent_likelihood_ID_unchanged=True,
        c0_fitted_c_same_IDs_candidates_priors_and_cold5x48budget=True,
        no_GPS_following_TLE_new_RF_or_postfit_trimming=True,
        inspected_case_development_only_not_full_DS23_confirmation=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
