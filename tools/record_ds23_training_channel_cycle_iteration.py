"""Record bounded RF qualification results without promoting a position method."""

from datetime import datetime, timezone
from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_algo03_iteration_audit'


def main():
    tone = ROOT/'reports/2026_10_21_ds23_training_channel_rf_v2'
    cycles = ROOT/'reports/2026_10_21_ds23_paired_component_cycles_v2'
    t, ta = read(tone/'evaluation.json'), read(tone/'independent_replay_audit.json')
    c, ca = read(cycles/'evaluation.json'), read(cycles/'independent_replay_audit.json')
    assert t['all_terminal'] and c['all_terminal'] and ta['completed'] == 19 and len(ca['rows']) == 2
    assert not t['failures'] and all(r['status'] == 'complete' for r in c['rows'])
    for directory in [tone, cycles]:
        protocol = read(directory/'protocol.json')
        assert all(sha(ROOT/'tools'/name) == digest for name, digest in protocol['source_sha256'].items())
    benchmark = ROOT/'reports/2026_10_20_ds23_combined_recovery_full/evaluation.json'
    values = read(benchmark)
    summary = {}
    for arm in ['c0', 'fitted_c']:
        rows = [r for r in values['all_rows'] if r['method'] == 'signed_prior' and r['arm'] == arm
            and r['status'] == 'accepted']
        assert len(rows) == 410
        errors = [r['position_error_km_report_only'] for r in rows]
        summary[arm] = dict(count=410, mean_km=float(np.mean(errors)), median_km=float(np.median(errors)))
    freezes = {}
    for case in ['DS23-0268', 'DS23-0405']:
        protocol = read(Path('/srv/bulk/leo/research/dbg01-two-worst-fast-20261021')/case/'protocol.json')
        assert all(sha(ROOT/'reports/2026_10_19_algo02_ds23_full'/case/name) == digest
            for name, digest in protocol['input_sha256'].items())
        freezes[case] = True
    old = ROOT/'reports/2026_10_20_algo03_iteration_audit/reentry_and_training_RF_iteration_receipt.json'
    files = dict(tone=tone/'evaluation.json', tone_audit=tone/'independent_replay_audit.json',
        cycles=cycles/'evaluation.json', cycles_audit=cycles/'independent_replay_audit.json',
        inventory=ROOT/'reports/2026_10_21_ds23_paired_component_cycles/inventory.json',
        benchmark=benchmark, DBG01=ROOT/'reports/DBG01/README.md')
    cycle_summary = {}
    for r in c['rows']:
        cycle_summary[r['case']] = dict(native_disagreement_hz=r['original_native_component_disagreement_hz'],
            modes={mode:dict(both_conditional_candidates=d['both_components_conditional_candidates'],
                all_RF_fits_interior=d['all_native_joint_fits_interior'],
                component_disagreement_hz=[f['principal_component_disagreement_hz'] for f in d['folds']],
                conditional_scores=[z['minimum_held_gain'] for z in d['components']])
                for mode, d in r['modes'].items()})
    receipt = dict(recorded_UTC=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress', this_turn_classification='progress', goal_achieved=False,
        objective='Full DS23 mean AND median error <=0.5km; causal TLE, regional initialization, no GPS in inference',
        previous_receipt=dict(path=str(old.relative_to(ROOT)), sha256=sha(old)),
        evidence={k:dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for k, p in files.items()},
        training_only_per_tone=dict(completed=ta['completed'],
            all_RX_fold_held_RF_score_improvements=ta['all_RX_fold_held_RF_score_improvements'],
            conditional_candidates=t['conditional_candidates'], supported_candidates=t['supported_candidates'],
            actual_native_RF_refits=ta['actual_native_RF_refits'],
            actual_gain_model_refits=ta['actual_gain_model_refits'],
            first_control_refits=ta['control_gain_model_refits'],
            no_new_qualified_absolute_CFO_or_position_measurement=True),
        complex_projection_correction=dict(variance='for gain=c(row)@w, use w.T@Cov(c(column))@w.conj()',
            v1_results_superseded=True, v1_raw_outputs_preserved=True,
            v1_source_archive='/srv/bulk/leo/research/ds23-training-channel-rf-v1-source-20261021',
            historical_flat_one_column_variances_unchanged=True,
            historical_per_tone_prototypes_need_corrected_replay_before_any_reuse=True,
            no_ALGO02_position_measurement_used_this_new_projection=True,
            validated_by_correlated_complex_Gaussian_sampling=True),
        simultaneous_component_cycles=cycle_summary,
        scope='23 already-saved dual-IQ panels; only2scans/9windows have qualifying two-component cycles; not full-DS23 RF coverage',
        training_native_acquisition_seeds_and_conditional_held_extraction_variances_remain_conditioned=True,
        ambiguity_750Hz_and_primary_GLRT_joint_covariance_not_qualified=True,
        retained_full_DS23_benchmark=summary, original_ALGO02_source_freeze_verified=freezes,
        focused_tests_passed=26, all_jobs_this_iteration_terminal=True,
        no_new_RF_collection_or_subagents=True, no_position_variant_promoted=True,
        no_new_positive_generalization_MD_report_or_remote_push=True,
        DBG01_extended_with_training_RF_support_complex_covariance_and_clock_cycles=True,
        next_actions=[
            'Fit one common physical RX clock contrast to both simultaneous component gain vectors, retaining full complex cross-component covariance.',
            'Compare that constrained model with separate component clocks on held frames and disjoint native-qualified windows; allow fallback and keep weak0154component explicit.',
            'Test750Hz branches using within-frame RF likelihood and calibrate uncertainty with independent components; do not adopt the repeatable23Hz discrepancy as a known bias.',
            'Only validated RF constraints may enter a joint physical per-probe LO model with primary-GLRT covariance, matched c0/fitted-c and regional cold starts.',
            'Use DBG01 and scan-disjoint position confirmation; increased GLRT coverage or held RF fit alone cannot qualify ALGO03.' ])
    target = OUT/'training_channel_and_component_cycles_iteration_receipt.json'
    write(target, receipt)
    write(OUT/'current_iteration_receipt.json', receipt)
    state = read(OUT/'state.json')
    state.update(latest_goal_iteration_receipt=str(target.relative_to(ROOT)),
        latest_training_only_frequency_selective_RF_audit=str((tone/'independent_replay_audit.json').relative_to(ROOT)),
        latest_simultaneous_component_clock_cycle_audit=str((cycles/'independent_replay_audit.json').relative_to(ROOT)),
        complex_RF_projection_variance_orientation_corrected_in_new_v2_prototypes=True,
        previous_goal_turn_classification='progress', this_turn_classification='progress', goal_achieved=False,
        focused_tests_passed=26, no_new_positive_generalization_report_published=True,
        next_work=receipt['next_actions'])
    write(OUT/'state.json', state)
    print(dict(receipt=str(target), benchmark=summary, candidates=t['supported_candidates'], cycles=cycle_summary), flush=True)


if __name__ == '__main__':
    main()
