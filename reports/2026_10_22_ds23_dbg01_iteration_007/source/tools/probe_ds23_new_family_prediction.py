"""Cold paired positions from grouped new-family prediction; RF choices frozen."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.linalg import block_diag

import run_ds23_dbg01_iteration_007 as runner
from ds23_new_family_prediction import attach_new_families,new_gates,wrapped_curve_score
from ds23_frequency_events import make_event_problem
from ds23_family_cavity import predictive_density_reference
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'new_family_prediction_v2'


def select(d,groups):
    known={r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    known.update(e['candidate_index'] for e in d['entries']);selected=[];seen=set();controls=[]
    for group in sorted(groups,key=lambda g:-g['points']):
        if not group['proposal_qualified']:continue
        best={a:r[0] for a,r in group['arms'].items()};j=best['c0']['candidate_index'];nulls={}
        for arm,r in best.items():
            score=0.
            for member,alias in zip(group['members'],r['aliases'],strict=True):
                t=d['scan'].tracks[member['track_index']];metadata=d['scan'].fixed_window_noise
                sigma=np.array([metadata['per_observation_noise_sigma_hz'][oid] if metadata['extra_parameter_BIC_gain']>0 else d['scan'].radio_sigma_hz for oid in t['observation_ids']])*np.sqrt(2)
                score+=wrapped_curve_score(t['times'],t['values']+alias/4.4e-6,sigma)
            nulls[arm]=dict(wrapped_unresolved_score=score,gain=score-r['score'])
        ids={o for m in group['members'] for o in m['observation_ids']}
        eligible=bool(j not in known and not seen&ids and all(v['gain']>group['multiplicity_penalty'] for v in nulls.values())
            and np.array_equal(best['c0']['aliases'],best['fitted_c']['aliases']))
        controls.append(dict(components=[m['component'] for m in group['members']],norad=best['c0']['norad'],eligible=eligible,wrapped_controls=nulls))
        if eligible and len(selected)<2:
            selected.append(group);seen.update(ids)
    entries=[]
    for group in selected:
        best=group['arms']['c0'][0]
        for member,alias in zip(group['members'],best['aliases'],strict=True):
            entries.append(dict(member,candidate_index=best['candidate_index'],norad=best['norad'],alias=int(alias),
                association_source='new_family_group_prediction'))
    return entries,controls


def build(d,arm,reference,new_reference,entries,physical):
    p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],[])
    attach_new_families(p,d,d['entries'],entries,new_reference,physical_modes=physical)
    return cached(p)


def refit(d,arm,entries,physical):
    families=sorted({e['candidate_index'] for e in entries});reference=np.zeros(len(d['means']));new_reference=np.zeros(len(families));x=np.zeros(2);history=[]
    for _ in range(5):
        p=build(d,arm,reference,new_reference,entries,physical);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15);new_phase=np.clip(p.calculate(x)['new_family_phases_s'],-15,15)
        history.append(dict(fit=result,curved_phase_change_s=float(np.max(abs(phase-reference))),
            new_phase_change_s=float(np.max(abs(new_phase-new_reference)))))
        reference,new_reference=phase,new_phase
    r=summary(p,x,d['entries']);c=p.calculate(x)
    r['linear_gates']+=new_gates(p,x);r['predictive_points']+=sum(e['points'] for e in entries)
    r.update(new_reference=p.new_references,new_family_indices=families,new_family_phases_s=c['new_family_phases_s'],
        new_family_coefficient=c['new_family_coefficient'],new_physical_mode_metadata=p.new_mode_metadata,
        history=history,final_phase_change_s=max(history[-1]['curved_phase_change_s'],history[-1]['new_phase_change_s']))
    # Replay the joint density independently with native covariance/SVD algebra.
    a=c['new_prediction_audit'];groups=np.asarray(a['groups']);bias=np.eye(int(groups.max())+1)[groups]*300.
    design=np.column_stack((a['design'],bias));covariance=block_diag(np.linalg.inv(a['gram']),np.eye(bias.shape[1]))
    direct,method=predictive_density_reference(a['raw'],design,covariance,a['sigma'])
    if abs(direct-c['linear_predictive_objective'])>2e-5:raise ValueError('new-family joint density does not replay')
    original=p.curved_calculate(x)
    if np.max(abs(original['coefficient']-c['coefficient']))>1e-12:raise ValueError('linear data updated calibration coefficients')
    r['audit']=dict(direct_predictive_density_difference=direct-c['linear_predictive_objective'],density_method=method,
        original_curved_calibration_coefficient_difference=float(np.max(abs(original['coefficient']-c['coefficient']))))
    return r


def one(case):
    output=OUT/(case+'.json')
    if output.exists():raise FileExistsError('preserve new-family position experiment')
    d=runner.engine.current_setup(case);nominees=read(runner.RAW/'linear_family_groups'/(case+'.json'))
    if nominees['status']!='complete':raise ValueError('grouped nominations incomplete')
    entries,controls=select(d,nominees['groups'])
    previous=read(runner.RAW/'new_family_prediction'/(case+'_selection.json'))
    if entries!=previous['entries']:raise ValueError('geometry correction must preserve frozen RF entries')
    write(OUT/(case+'_selection.json'),dict(entries=entries,controls=controls,frozen_before_position_fits=True,no_GPS_used=True))
    trials={}
    if entries:
        for method,physical in [('phase_only',False),('physical_prior',True)]:
            arms={arm:refit(d,arm,entries,physical) for arm in ['c0','fitted_c']}
            passed=bool(valid(arms) and all(np.max(abs(np.asarray(r['new_family_phases_s'])))<=15.000001 for r in arms.values()))
            trials[method]=dict(arms=arms,paired_valid=passed,entries=entries,
                physical_modes=physical,original_calibration_observations_unchanged=True)
            print(case,method,'points',sum(e['points'] for e in entries),'valid',passed,flush=True)
    write(output,dict(case=case,trials=trials,primary='physical_prior',selection='new physical-prior model only if all paired gates pass, otherwise incumbent',
        no_geographic_scoring_yet=True))
    return dict(case=case,status='complete',points=sum(e['points'] for e in entries))


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    record=dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        helper_sha256=sha(Path(__file__).with_name('ds23_new_family_prediction.py')),
        new_family_phase_prior='declared Gaussian approximation at causal forecast mean/width; original curved Student priors unchanged',
        geometry_fix='one paired frequency, derivative and elevation per native timestamp; v1 first-frequency broadcast invalid and preserved',
        original_selection_entries_must_match_v1_exactly=True,
        preserved_v1_protocol_sha256=sha(runner.RAW/'new_family_prediction/protocol.json'),
        new_orbit_modes='three existing physical Gaussian causal TLE directions; zero-mode control',
        old_and_new_prediction_in_one_joint_shared_covariance=True,receiver_calibration_outputs_curved_only=True,
        aliases_and_disjoint_groups_frozen_from_same_c0_nomination_in_both_arms=True,maximum_groups=2,
        null_control='wrapped common-fragment alias sum of broad normalized polynomial prior; no in-sample score compared across masks',
        no_GPS_following_TLE_new_RF_or_point_trim=True,phase_rounds=5,position_steps=48,regional_start=[0,0],regional_width_km=25,
        primary='physical_prior',ablation='phase_only',no_new_ALGO_release_without_full_DS23=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve paired position protocol')
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,record['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,RF_selection_complete_before_geographic_scoring=True))


if __name__=='__main__':main()
