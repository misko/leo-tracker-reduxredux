"""Record raw-IQ uncertainty, independent controls, and matched position trials."""

from datetime import datetime,timezone
from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_algo03_iteration_audit'


def main():
    raw=ROOT/'reports/2026_10_21_ds23_joint_receiver_iq'
    boot=ROOT/'reports/2026_10_21_ds23_joint_iq_frame_bootstrap'
    independent=ROOT/'reports/2026_10_21_ds23_joint_iq_independent_control'
    phase=ROOT/'reports/2026_10_21_ds23_shared_receiver_phase'
    original=ROOT/'reports/2026_10_21_ds23_joint_clock_position'
    screened=ROOT/'reports/2026_10_21_ds23_screened_joint_clock_position_v2'
    directories=[raw,boot,independent,phase,original,screened]
    for directory in directories:
        protocol=read(directory/'protocol.json')
        for name,digest in protocol['source_tools'].items():
            assert sha(ROOT/'tools'/name)==digest
    r,ra=read(raw/'evaluation.json'),read(raw/'independent_replay_audit.json')
    b,ba=read(boot/'evaluation.json'),read(boot/'independent_replay_audit.json')
    i=read(independent/'evaluation.json');p,pa=read(phase/'evaluation.json'),read(phase/'independent_replay_audit.json')
    s=read(screened/'independent_replay_evaluation.json')
    assert len(r['rows'])==len(b['rows'])==9 and all(q['status']=='complete' for q in r['rows']+b['rows'])
    assert all(q['all_terminal'] for q in [r,b,i,p,read(original/'execution.json'),read(screened/'execution.json')])
    assert ra['completed']==ba['completed']==pa['completed']==9
    testlog=Path('/srv/bulk/leo/research/ds23-joint-receiver-phase-full-tests-20261021.log')
    assert '54 passed' in testlog.read_text()
    benchmark=ROOT/'reports/2026_10_20_ds23_combined_recovery_full/evaluation.json'
    dataset=read(benchmark);metrics={}
    for arm in ['c0','fitted_c']:
        rows=[q for q in dataset['all_rows'] if q['method']=='signed_prior' and q['arm']==arm and q['status']=='accepted']
        assert len(rows)==410
        errors=[q['position_error_km_report_only'] for q in rows]
        metrics[arm]=dict(count=len(rows),mean_km=float(np.mean(errors)),median_km=float(np.median(errors)))
    evidence=dict(raw=raw/'evaluation.json',raw_audit=raw/'independent_replay_audit.json',
        bootstrap=boot/'evaluation.json',bootstrap_audit=boot/'independent_replay_audit.json',
        independent_target=independent/'evaluation.json',shared_phase=phase/'evaluation.json',
        shared_phase_audit=phase/'independent_replay_audit.json',
        first_position=original/'independent_replay_evaluation.json',
        screened_position=screened/'independent_replay_evaluation.json',
        benchmark=benchmark,DBG01=ROOT/'reports/DBG01/README.md')
    previous=OUT/'common_clock_ambiguity_and_carrier_branch_iteration_receipt.json'
    ratios=[q['bootstrap_frequency_sigma_hz'][2]/q['Gaussian_frequency_sigma_hz'][2] for q in b['rows']]
    receipt=dict(recorded_UTC=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress',this_turn_classification='progress',goal_achieved=False,
        objective='Develop ALGO03 to reach full-DS23 mean AND median position error<=0.5km; causal TLE, regional initialization, no GPS inference; DBG01; publish only positive generalizing MD reports with figures to remote main',
        previous_receipt=dict(path=str(previous.relative_to(ROOT)),sha256=sha(previous)),
        evidence={k:dict(path=str(v.relative_to(ROOT)),sha256=sha(v)) for k,v in evidence.items()},
        raw_joint_IQ=dict(windows=9,scans=['DS23-0154','DS23-0216'],
            model='joint source carriers, one or two physical RX clocks,4fractional epochs,4code rates,2complex channel ratios; free shared TX gain pair and independent RX DC each frame',
            original_RF_acquisition_and_carrier_branch_conditioned=True,
            held_target_signal_coefficients_never_fit=True,
            RF_optimization_replays=ra['raw_RF_optimizations_replayed'],
            independent_dense_predictive_checks=ra['independent_dense_predictive_covariance_checks'],
            primary_common_vs_separate_candidates=r['conditional_candidates'],
            wrong_plus_minus750Hz_branches_have_large_within_frame_loss_penalties=True),
        uncertainty=dict(replicates_per_window=63,all_parameter_bootstrap=True,
            weighted_objective_replays=ba['weighted_bootstrap_objective_replays'],
            selected_bootstrap_optimization_refits=ba['selected_bootstrap_refits'],
            source_clock_sigma_hz=[dict(index=q['index'],Gaussian=q['Gaussian_frequency_sigma_hz'][2],
                paired_frame=q['bootstrap_frequency_sigma_hz'][2],bounds=q['bounded_replicates']) for q in b['rows']],
            bootstrap_over_Gaussian_clock_sigma_range=[min(ratios),max(ratios)],
            fixed_carrier_branch_and_some_limited_iteration_bootstrap_refits_are_not_absolute_covariance_coverage=True),
        independent_target_control=dict(surviving_common_clock_candidates=i['common_clock_candidates_also_beating_independent'],
            those_windows_both_in0154=True,
            common_vs_separate_clock_alone_was_insufficient_qualification=True),
        disjoint_position=dict(initial_exploratory_endpoints=24,screened_endpoints=len(s['rows']),
            screened_RF_indices=s['screened_RF_indices'],
            same_reused_IQ_GLRT_points_removed_in_both_matched_arms=True,
            fixed_original_satellite_nominations_and_masks_except_probe_exclusions=True,
            causal_priors_and_full25km_box_cold_center_c0_fitted_c_5round48step_budgets=True,
            screened_rows=[{k:q[k] for k in ['case','noise','arm','candidate_error_km',
                'matched_control_error_km','policy_error_km','candidate_augmented_paired_pass',
                'frequency_RMS_hz','matched_control_RMS_hz','RF_points','excluded_curved_points','excluded_predictive_points']} for q in s['rows']],
            only0154_has_RF_factors_after_current_screen=True,
            engineering_sigma_floor_and_unresolved_per_probe_LO_noise_sensitivity_are_not_calibrated_uncertainties=True,
            no_new_scan_or_location_generalization_proven=True),
        shared_phase_control=dict(model='one wrapped Gaussian relative receiver phase per frame shared by both components; one variance learned on training data only; normalized marginal raw-IQ predictions',
            all9windows_have_positive_held_predictive_gain_vs_independent_target=True,
            that_does_not_establish9_correct_correspondences_or9_clock_constraints=True,
            mean_RF_clock_carrier_and_covariance_not_refit_with_shared_phase=True,
            quadrature4096vs8192_replayed=True,
            two_signal_phase_closure_results=[dict(index=q['index'],window=q['window_key'],closure=q['phase_closure']) for q in pa['rows']],
            closure_is_descriptive_and_conditioned_not_a_full_RF_randomization_test=True),
        retained_full_DS23_benchmark=metrics,full_goal_achieved=False,
        focused_tests_passed=54,test_log=dict(path=str(testlog),sha256=sha(testlog)),
        all_jobs_this_iteration_terminal=True,new_RF_collection=False,subagents_spawned=False,
        new_MD_report_published=False,remote_push_this_iteration=False,
        reason_no_publication='one inspected scan has a modest improvement; RF correspondence/phase-noise covariance and disjoint position generalization remain unproven',
        next_actions=[
            'Use two-signal phase closure to distinguish a true shared receiver phase from inconsistent RX component correspondences;0154often has a poorly modeled second component,0216window2506has strong closure in both folds.',
            'Refit the raw carrier/clock means jointly with a normalized shared receiver phase-noise model and an unassociated-component option; current phase study changes predictive covariance only.',
            'Retain full RF carrier/clock/code covariance and frame-level uncertainty; do not convert all9positive aggregate predictive gains into9precise independent clock factors.',
            'Review previous shared-probe/differential-CFO negative confirmation controls before expanding. Test materially new branch-corrected, phase-aware RF evidence on more existing saved scan windows, not a new collection.',
            'Only then evaluate RF-conditioned satellite-family refresh with unchanged gates and matched c0/fitted-c cold regional searches on development and scan-disjoint confirmation; full-DS23 mean AND median<=0.5km remains the success criterion.' ])
    target=OUT/'joint_raw_IQ_uncertainty_and_disjoint_position_iteration_receipt.json'
    write(target,receipt);write(OUT/'current_iteration_receipt.json',receipt)
    state=read(OUT/'state.json')
    state.update(latest_goal_iteration_receipt=str(target.relative_to(ROOT)),
        latest_joint_raw_receiver_IQ_audit=str((raw/'independent_replay_audit.json').relative_to(ROOT)),
        latest_paired_frame_RF_uncertainty_audit=str((boot/'independent_replay_audit.json').relative_to(ROOT)),
        latest_independent_target_raw_IQ_control=str((independent/'evaluation.json').relative_to(ROOT)),
        latest_shared_receiver_phase_predictive_control=str((phase/'independent_replay_audit.json').relative_to(ROOT)),
        latest_disjoint_screened_RF_clock_position=str((screened/'independent_replay_evaluation.json').relative_to(ROOT)),
        RF_position_improvement_only_one_inspected_scan_no_generalization=True,
        phase_predictive_gains_do_not_qualify_all9_RF_correspondences=True,
        previous_goal_turn_classification='progress',this_turn_classification='progress',goal_achieved=False,
        focused_tests_passed=54,next_work=receipt['next_actions'],
        no_new_positive_generalization_report_published=True)
    write(OUT/'state.json',state)
    print(dict(receipt=str(target),benchmark=metrics,RF_screen=i['common_clock_candidates_also_beating_independent'],
        tests=54,screened_position_rows=len(s['rows'])),flush=True)


if __name__=='__main__':main()
