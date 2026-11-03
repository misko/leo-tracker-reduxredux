"""Matched c0/fitted-c position controls on the additional saved-scan cohort."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np

import probe_ds23_joint_clock_position as engine
import audit_ds23_joint_iq_uncertainty_position as audit
from probe_ds23_phase_clock_confirmation import OUT as RF_SOURCE
from refine_ds23_phase_clock_uncertainty import OUT as UNCERTAINTY
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=RF_SOURCE/'position'


def configure():
    engine.OUT=OUT;engine.RF=UNCERTAINTY;engine.RAW=OUT/'RF_eligibility'
    engine.CASES=[r['case'] for r in read(RF_SOURCE/'evaluation.json')['rows']]


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    OUT.mkdir(exist_ok=True)
    source=read(RF_SOURCE/'evaluation.json');bootstrap=read(UNCERTAINTY/'evaluation.json')
    if not source['all_terminal'] or not bootstrap['all_terminal']:raise ValueError('RF jobs not terminal')
    by_index={r['index']:r for r in bootstrap['rows']}
    eligibility=[]
    for r in source['rows']:
        b=by_index.get(r['index']);good=bool(b and b['status']=='complete' and b['full_fit']['converged']
            and not b['full_fit']['boundary'] and not b['full_fit']['phase_variance_boundary']
            and all(not n['boundary'] for n in b['full_native_fits'])
            and b['bounded_replicates']<=1 and b['unconverged_replicates']<=3)
        eligibility.append(dict(index=r['index'],case=r['case'],
            conditional_raw_IQ_common_clock_candidate=bool(r.get('conditional_two_component_candidate') and good),
            source_RF_candidate=r.get('conditional_two_component_candidate'),bootstrap_optimization_quality=good))
    screen=dict(rows=eligibility,RF_source_sha256=sha(RF_SOURCE/'evaluation.json'),
        uncertainty_sha256=sha(UNCERTAINTY/'evaluation.json'),
        quality_rule='source RF checks plus full native/phase interiors and convergence; at most1bounded and3unconverged of31bootstrap refits',
        engineering_uncertainty_only=True,no_GPS_or_position_used_in_screen=True)
    screen_path=OUT/'RF_eligibility/evaluation.json';screen_path.parent.mkdir(exist_ok=True)
    if screen_path.exists() and read(screen_path)!=screen:raise ValueError('frozen RF position eligibility changed')
    if not screen_path.exists():write(screen_path,screen)
    configure()
    protocol=dict(cases=engine.CASES,RF_source_sha256=sha(RF_SOURCE/'evaluation.json'),
        bootstrap_sha256=sha(UNCERTAINTY/'evaluation.json'),eligibility_sha256=sha(screen_path),
        workers=6,per_pair_seconds=180,noises=['control','bootstrap','plus_radio'],
        phase_rounds=5,steps_per_round=48,regional_box_km=25,cold_start=[0,0],
        matched_c0_fitted_c_observations_candidates_priors_and_budgets=True,
        all_GLRT_from_reused_RF_probe_removed_in_both_matched_arms=True,
        original_satellite_nominations_remain_fixed=True,
        sigma='max(5Hz,whole-frame phase-aware bootstrap SD,fold clock difference/sqrt2); broad adds2*radio-noise variance',
        original_residual_gates_plus_phase_limit15s_and_RF_innovation_limit3sigma=True,
        policy_falls_back_to_original_full_GLRT_signed_incumbent_for_invalid_or_no_RF=True,
        no_GPS_following_TLE_or_location_specific_selection_used=True,
        four_previously_studied_saved_scans_not_new_geographic_locations=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [__file__.split('/')[-1],
            'probe_ds23_joint_clock_position.py','ds23_disjoint_rf_calibration.py','ds23_radio_calibration_factor.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen phase-aware position protocol changed')
    if not path.exists():write(path,protocol)
    for case in engine.CASES:engine.prepare(case)
    jobs=[(case,'strict',noise) for case in engine.CASES for noise in protocol['noises']]
    with ProcessPoolExecutor(max_workers=6,initializer=configure) as pool:
        results=[f.result() for f in as_completed([pool.submit(engine.one,j) for j in jobs])]
    write(OUT/'execution.json',dict(rows=results,all_terminal=True))
    if not all(r['status']=='complete' for r in results):raise ValueError('position trial failed; preserve terminal failure')
    audit.PNT=OUT;audited=[audit.position_case(case,selections=['strict']) for case in engine.CASES]
    rows=[r for case in audited for r in case['rows']]
    for r in rows:
        r['candidate_adopted']=bool(r['noise']!='control' and r['RF_points'] and r['candidate_augmented_paired_pass'])
        r['policy_error_km']=r['candidate_error_km'] if r['candidate_adopted'] else r['source_incumbent_error_km']
    aggregate=[]
    for arm in ['c0','fitted_c']:
        for noise in ['bootstrap','plus_radio']:
            selected=[r for r in rows if r['arm']==arm and r['noise']==noise]
            before=[r['source_incumbent_error_km'] for r in selected];after=[r['policy_error_km'] for r in selected]
            aggregate.append(dict(arm=arm,noise=noise,scans=len(selected),adopted=sum(r['candidate_adopted'] for r in selected),
                baseline_mean_km=float(np.mean(before)),baseline_median_km=float(np.median(before)),
                policy_mean_km=float(np.mean(after)),policy_median_km=float(np.median(after))))
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    x=np.arange(len(engine.CASES))
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        baseline=[next(r for r in rows if r['case']==case and r['arm']==arm)['source_incumbent_error_km'] for case in engine.CASES]
        ax.scatter(x-.18,baseline,color='black',label='Original signed incumbent')
        for offset,noise,color in [(0.,'bootstrap','tab:blue'),(.18,'plus_radio','tab:orange')]:
            selected=[next(r for r in rows if r['case']==case and r['arm']==arm and r['noise']==noise) for case in engine.CASES]
            ax.scatter(x+offset,[r['policy_error_km'] for r in selected],color=color,label=noise)
            for i,r in enumerate(selected):
                if r['candidate_adopted']:ax.plot([i-.18,i+offset],[baseline[i],r['policy_error_km']],color=color,alpha=.6)
        ax.axhline(.5,color='seagreen',ls='--',lw=1)
        ax.set_xticks(x,[case.split('-')[1] for case in engine.CASES]);ax.set(title=arm,ylabel='Position error (km)',xlabel='Additional saved scan')
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Phase-aware, partial-component-screened RF clocks · disjoint GLRT controls\n'
        'Engineering uncertainty; fallback uses original incumbent; no full-DS23 method promoted',fontsize=11)
    fig.savefig(OUT/'position_comparison.png',dpi=160);plt.close(fig)
    write(OUT/'independent_replay_evaluation.json',dict(rows=rows,aggregate=aggregate,case_audits=audited,
        all_RF_IQ_disjoint_from_GLRT=True,all_endpoints_and_calibration_designs_replayed=True,
        no_full_DS23_or_new_location_accuracy_improvement_established=True))
    print(aggregate,flush=True)
    print([(r['case'],r['noise'],r['arm'],round(r['candidate_error_km'],6),r['candidate_adopted']) for r in rows],flush=True)


if __name__=='__main__':main()
