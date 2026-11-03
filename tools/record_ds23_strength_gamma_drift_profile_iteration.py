"""Record completed controls and a replicated conditional RF-model issue."""

from datetime import datetime,timezone
from pathlib import Path
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_algo03_iteration_audit'


def main():
    paths=dict(linear_strength='reports/2026_10_21_ds23_linear_family_strength/development_independent_replay.json',
        Gamma_gradient='reports/2026_10_21_ds23_exact_gamma_gradient/independent_replay_audit.json',
        drift_development='reports/2026_10_21_ds23_band_drift_correlation/development_independent_replay.json',
        drift_confirmation='reports/2026_10_21_ds23_band_drift_correlation/confirmation_independent_replay.json',
        fixed_drift_followup='reports/2026_10_21_ds23_band_drift_correlation/fixed_prior_confirmation_workflow.json',
        within_probe_profiles='reports/2026_10_21_ds23_frequency_profile/evaluation.json',
        profile_validation='reports/2026_10_21_ds23_frequency_profile_validation/evaluation.json',
        profile_confirmation='reports/2026_10_21_ds23_frequency_profile_confirmation/evaluation.json',
        profile_RF_audit='reports/2026_10_21_ds23_frequency_profile_confirmation/independent_replay_audit.json')
    evidence={k:dict(path=p,sha256=sha(ROOT/p)) for k,p in paths.items()};data={k:read(ROOT/p) for k,p in paths.items()}
    for folder,stage in [('2026_10_21_ds23_linear_family_strength','development'),
        ('2026_10_21_ds23_band_drift_correlation','development'),('2026_10_21_ds23_band_drift_correlation','confirmation')]:
        execution=read(ROOT/'reports'/folder/(stage+'_execution.json'))
        if not execution['all_terminal'] or execution['failures']:raise ValueError('position control not complete')
    for name in ['within_probe_profiles','profile_validation','profile_confirmation']:
        if not data[name]['all_terminal']:raise ValueError('RF control not complete')
    gamma=data['Gamma_gradient'];profile=data['within_probe_profiles'];rf=data['profile_RF_audit']
    receipt=dict(recorded_UTC=datetime.now(timezone.utc).isoformat(),previous_goal_turn_classification='progress',this_turn_classification='progress',
        goal_achieved=False,evidence=evidence,
        linear_strength_seven_scan_statistics=data['linear_strength']['statistics'],
        linear_strength_fails_joint_mean_and_median_development=True,no_linear_strength_confirmation_run=True,
        Gamma_integration_diagnostic=dict(cases=7,arms=['c0','fitted_c'],grid='3x3 at.25km spacing per RF mode',
            integration_draws_per_node=[512,2048,2048],independent_seed_controls=True,
            maximum_predicted_local_shift_km=gamma['maximum_predicted_local_shift_km'],
            maximum_independent_seed_disagreement_km=gamma['maximum_independent_seed_shift_disagreement_km'],
            all_importance_diagnostics_qualified=gamma['all_importance_diagnostics_qualified'],
            same_generalized_model_Gaussian_modes_integrated_exactly_Gamma_integrals_estimated=True,
            curved_calibration_moments_exclude_linear_data=True,
            phase_reference_fixed=True,no_position_refit_or_accuracy_claim=True,
            local_diagnostic_does_not_prove_global_or_full_dataset_equivalence=True),
        band_drift_prior_control=dict(original_mean_sigma_hz_s=10.,original_contrast_sigma_hz_s=.5,
            original_cross_band_correlation=99.75/100.25,alternative_correlation=0.,
            each_band_marginal_variance_hz2_s2=100.25,nuisance_count_unchanged=True,
            development=data['drift_development']['statistics'],confirmation=data['drift_confirmation']['statistics'],
            curved_RF_selector_did_not_qualify_fixed_alternative=True,
            fixed_alternative_confirmation_followup_disclosed_separately_from_failed_original_selector=True,
            fixed_alternative_fails_both_mean_and_median_in_confirmation=True,
            no_prior_promoted=True),
        within_probe_RF=dict(development_probes=profile['complete'],same_scans=23,
            median_absolute_common_non_affine_contrast_hz=profile['median_absolute_common_non_affine_contrast_hz'],
            preliminary_probes_over_three_local_scales=profile['common_contrast_over_three_local_sigmas'],
            conditional_local_scales_not_calibrated_confidence=True,
            RF_prediction_summary=rf['summary'],one_native_raw_probe_per_cohort_independently_replayed=True,
            confirmation_probe_disjoint_not_scan_or_location_disjoint=True,
            code_and_timing_conditioned_on_whole_probe_fit_in_all_models=True,
            constant_and_piecewise_frequencies_and_channel_updates_training_symbols_only=True,
            hardware_origin_and_absolute_frequency_correction_not_established=True,
            no_CFO_measurement_or_localization_policy_modified=True),
        preserved=['original observation values/masks/labels/aliases and residual gates in position trials',
            'causal TLEs; report-only geographic truth; cold25x25km regional initialization',
            'paired c0/fitted-c observations, priors other than explicit intervention, and5x48 search budgets',
            'curved-only calibration; linear posterior prediction with full covariance',
            'exact incumbent fallback on either arm failing original gates'],
        component_owned_tests_passed=27,original_ALGO02_source_freeze_verified=True,
        all_experiments_terminal=True,active_experiment=None,no_new_RF_collection=True,
        current_full_DS23_benchmark_unchanged=dict(available=410,population=413,
            fitted_c_mean_km=1.4980020457420653,fitted_c_median_km=1.1854524915944755,
            c0_mean_km=1.5085072173344016,c0_median_km=1.2499845679166115),
        new_position_generalization_gain=False,no_new_MD_report_or_remote_push=True,
        next_hypothesis='Prototype a common within-probe receiver frequency perturbation fitted jointly to two simultaneous pilot components. First test the gauge-invariant component frequency difference and held-symbol/point-disjoint RF prediction. Do not assume the late frequency is settled, a zero-mean perturbation equals the physical LO, or inter-frame phase continuity measures Doppler. Establish the joint covariance with any reused original measurement before adding differential evidence to localization. This is unimplemented and unvalidated.',
        rejected_or_exhausted=['fixed support inflation of independent predictive linear noise fails mean on development',
            'more exact Gaussian/Gamma integration predicts only1-17m local shifts in these7 scans',
            'independent band linear drifts at fixed marginal variance fail median confirmation',
            'per-band nonlinear covariance, converter-dependent smooth loading, spatial-score means and old fixed-position importance audits already exist; do not rebrand as new'])
    target=OUT/'strength_Gamma_drift_profile_iteration_receipt.json';write(target,receipt)
    state=read(OUT/'state.json')
    state.update(latest_goal_iteration_receipt=str(target.relative_to(ROOT)),previous_goal_turn_classification='progress',
        this_turn_classification='progress',goal_achieved=False,active_experiment=None,
        latest_completed_experiment=paths['drift_confirmation'],latest_completed_RF_panel=paths['profile_RF_audit'],
        latest_Gamma_position_gradient_diagnostic=paths['Gamma_gradient'],latest_linear_strength_trial=paths['linear_strength'],
        next_experiment_hypothesis=receipt['next_hypothesis'],new_focused_tests_this_iteration=27,
        no_new_positive_generalization_report_published=True,
        band_linear_drift_independence_not_a_confirmed_position_fix=True,
        within_probe_temporal_RF_model_has_conditional_held_symbol_and_point_disjoint_support=True,
        within_probe_temporal_RF_model_has_no_validated_absolute_CFO_or_position_correction=True)
    state['experiments']['strength_Gamma_drift_profile_20261021']=dict(path=str(target.relative_to(ROOT)),sha256=sha(target),
        full_DS23_benchmark_unchanged=True,no_new_position_generalization_gain=True,
        within_probe_RF_prediction=rf['summary'])
    write(OUT/'state.json',state);write(OUT/'current_iteration_receipt.json',receipt)
    print('RECORDED',target,'goal remains unmet',flush=True)


if __name__=='__main__':main()
