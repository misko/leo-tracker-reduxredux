"""Record completed measurement-model diagnostics without promoting a policy."""

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_algo03_iteration_audit'


def main():
    paths = {
        'observation_noise': 'reports/2026_10_21_ds23_observation_noise/independent_replay_audit.json',
        'sparse_glitches': 'reports/2026_10_21_ds23_sparse_glitches/independent_replay_audit.json',
        'new_phase_curves': 'reports/2026_10_21_ds23_new_family_anchor_only/independent_replay_audit.json',
        'independent_secondary': 'reports/2026_10_21_ds23_independent_secondary/independent_replay_audit.json',
        'added_information': 'reports/2026_10_21_ds23_added_curve_information/evaluation.json',
        'precision_counterfactual': 'reports/2026_10_21_ds23_precision_sensitivity/evaluation.json',
        'differential_phase': 'reports/2026_10_21_ds23_differential_frame_phase_v2/evaluation.json',
        'fractional_phase': 'reports/2026_10_21_ds23_fractional_differential_phase/frequency_consistency_audit.json',
        'phase_RF_consistency': 'reports/2026_10_21_ds23_phase_RF_consistency/evaluation.json',
        'joint_RF_pilot': 'reports/2026_10_21_ds23_joint_component_refinement/evaluation.json',
        'joint_RF_full_curves': 'reports/2026_10_21_ds23_joint_component_full_curves/evaluation.json',
        'joint_RF_position': 'reports/2026_10_21_ds23_joint_RF_position/independent_replay_audit.json',
    }
    evidence = {name: dict(path=path, sha256=sha(ROOT/path)) for name, path in paths.items()}
    data = {name: read(ROOT/path) for name, path in paths.items()}
    if not data['joint_RF_full_curves']['all_terminal'] or data['joint_RF_full_curves']['complete'] != 312:
        raise ValueError('full RF work is not complete')
    execution = read(ROOT/'reports/2026_10_21_ds23_joint_RF_position/execution.json')
    if not execution['all_terminal'] or execution['failures']:
        raise ValueError('position trials are not complete')
    info = []
    for row in data['precision_counterfactual']['rows']:
        if row['arm'] != 'fitted_c': continue
        result = row['results']['phase_uncertain']
        info.append(dict(case=row['case'], before_local_major_scale_km=result['before_scales']['major_local_sigma_km'],
            conditional_CFO_sigma_factors=[v['sigma_factor'] for v in result['rows']],
            after_local_major_scales_km=[v['scales']['major_local_sigma_km'] for v in result['rows']]))
    consistency = data['phase_RF_consistency']
    statistics = data['joint_RF_position']['statistics']
    gains = {arm: {name: dict(
        mean_improvement_m=1000*(statistics['incumbent'][arm]['mean_km']-statistics[name][arm]['mean_km']),
        median_improvement_m=1000*(statistics['incumbent'][arm]['median_km']-statistics[name][arm]['median_km']))
        for name in statistics if name != 'incumbent'} for arm in ['c0','fitted_c']}
    receipt = dict(recorded_UTC=datetime.now(timezone.utc).isoformat(), previous_goal_turn_classification='no progress: status inspection/restatement only',
        this_turn_classification='progress', goal_achieved=False, evidence=evidence,
        completed_this_iteration=['local precision counterfactual with fixed nuisance priors and Gamma precision',
            '282 held-frame differential phase screens across23 archived scans',
            '282 matched fractional-template and within-frame-information controls',
            '46 joint two-component CFO/epoch/rate fits with disjoint raw-symbol prediction',
            '312 full-curve joint RF fits on7 RF-qualified development scans',
            'matched c0/fitted-c regional position refits and exact replay of3 RF variants on all7 scans'],
        earlier_unrecorded_completed_experiments={name: evidence[name] for name in ['observation_noise','sparse_glitches','new_phase_curves','independent_secondary','added_information']},
        precision_information_counterfactual=info,
        local_information_is_not_position_accuracy_or_calibrated_confidence=True,
        phase_RF_comparison={key:consistency[key] for key in ['matched_probes','strong_phase_screen','strong_phase_within_three_local_RF_scales',
            'strict_RF_and_strong_phase','strict_RF_and_strong_phase_within_three_local_RF_scales']},
        large_interframe_phase_slopes_not_validated_as_carrier_Doppler=True,
        no_phase_frequency_correction_applied=True,
        joint_RF_pilot_summary=data['joint_RF_pilot']['summary'],
        full_curve_RF_summary={key:data['joint_RF_full_curves'][key] for key in ['complete','strict_RF_qualified']},
        matched_seven_scan_position_statistics=statistics, engineering_position_gains_m=gains,
        local_RF_fit_improvement_not_a_claim_of_better_dataset_wide_localization=True,
        preserved=['all original observations and frozen satellite labels/aliases', 'original orbital/radio/noise priors and residual gates',
            'same RF-qualified observations in separate, joint-frequency and joint-six-parameter controls',
            'linear observations never update curved calibration at fixed position',
            'same five-phase-round 48-iteration cold regional budget in c0/fitted-c',
            'causal TLEs and report-only geographic truth'],
        source_freeze_verified_this_turn=True, new_focused_tests_passed=16,
        first_differential_phase_attempt_failed_complex_JSON_serialization_without_persisted_fit_results=True,
        original_failed_attempt_preserved='reports/2026_10_21_ds23_differential_frame_phase/protocol.json',
        all_experiments_terminal=True, active_experiment=None,
        new_positive_generalization_established=False, new_MD_report_or_remote_push=False,
        current_full_DS23_benchmark_unchanged=dict(population=413,available=410,
            fitted_c_mean_km=1.4980020457420653,fitted_c_median_km=1.1854524915944755,
            c0_mean_km=1.5085072173344016,c0_median_km=1.2499845679166115),
        next_hypothesis='Test a fixed reliability variance inflation for linear prediction using the frozen active-curved family support. Current curved likelihood powers can be.2/.6/1 while linear prediction uses unit strength. Keep full shared covariance, all observations and original gates; no GPS-dependent rule or score comparison across different powers. This is unimplemented and unvalidated.',
        no_new_RF_collection=True)
    target = OUT/'precision_phase_joint_RF_iteration_receipt.json'; write(target, receipt)
    state = read(OUT/'state.json')
    state.update(latest_goal_iteration_receipt=str(target.relative_to(ROOT)),
        previous_goal_turn_classification=receipt['previous_goal_turn_classification'],this_turn_classification='progress',
        goal_achieved=False,active_experiment=None,latest_completed_experiment=paths['joint_RF_position'],
        latest_completed_RF_panel=paths['joint_RF_full_curves'],new_focused_tests_this_iteration=16,
        next_experiment_hypothesis=receipt['next_hypothesis'],
        no_new_positive_generalization_report_published=True,
        joint_component_RF_refinement_has_only_metre_scale_engineering_position_effect=True,
        interframe_phase_coherence_is_not_validated_carrier_Doppler=True,
        new_curved_family_phase_coordinates_implemented_but_no_generalization_gain=True)
    state['experiments']['measurement_models_phase_and_joint_RF_20261021'] = dict(path=str(target.relative_to(ROOT)),sha256=sha(target),
        full_DS23_benchmark_unchanged=True, matched_seven_scan_position_statistics=statistics,
        new_positive_generalization_established=False)
    write(OUT/'state.json', state); write(OUT/'current_iteration_receipt.json', receipt)
    print('RECORDED',target,'fitted-c mean gain metres',gains['fitted_c']['joint_all_six']['mean_improvement_m'],flush=True)


if __name__=='__main__':main()
