"""Persist RF ambiguity findings and the unchanged full positioning benchmark."""

from datetime import datetime, timezone
from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_algo03_iteration_audit'


def main():
    previous = OUT/'training_channel_and_component_cycles_iteration_receipt.json'
    clock = ROOT/'reports/2026_10_21_ds23_common_receiver_clock_v2'
    branch = ROOT/'reports/2026_10_21_ds23_common_clock_alias_refit'
    screen = ROOT/'reports/2026_10_21_ds23_common_clock_carrier_alias'
    c, ca = read(clock/'evaluation.json'), read(clock/'independent_replay_audit.json')
    b, ba = read(branch/'evaluation.json'), read(branch/'independent_replay_audit.json')
    for result in [c, b, read(screen/'evaluation.json')]:
        assert result['all_terminal'] and all(r.get('status', 'complete') == 'complete' for r in result['rows'])
    assert ca['completed'] == ba['completed'] == 9
    for directory in [clock, branch, screen]:
        protocol = read(directory/'protocol.json')
        bindings = protocol.get('source_sha256')
        if not isinstance(bindings, dict):
            bindings = protocol['source_tools']
        for name, digest in bindings.items():
            assert sha(ROOT/'tools'/name) == digest
    benchmark = ROOT/'reports/2026_10_20_ds23_combined_recovery_full/evaluation.json'
    dataset = read(benchmark)
    position = {}
    for arm in ['c0', 'fitted_c']:
        rows = [r for r in dataset['all_rows'] if r['method'] == 'signed_prior'
            and r['arm'] == arm and r['status'] == 'accepted']
        assert len(rows) == 410
        errors = [r['position_error_km_report_only'] for r in rows]
        position[arm] = dict(count=len(rows), mean_km=float(np.mean(errors)), median_km=float(np.median(errors)))
    tests = Path('/srv/bulk/leo/research/ds23-common-clock-qualification-tests-20261021.log')
    assert '39 passed' in tests.read_text()
    roots = dict(clock=clock/'evaluation.json', clock_audit=clock/'independent_replay_audit.json',
        alias_search=branch/'evaluation.json', alias_audit=branch/'independent_replay_audit.json',
        alias_screen=screen/'evaluation.json', benchmark=benchmark,
        inventory=ROOT/'reports/2026_10_21_ds23_common_receiver_clock/inventory.json',
        DBG01=ROOT/'reports/DBG01/README.md')
    clock_finding = next(r for r in ca['rows'] if r['index'] == 8)
    RF_ratios = {r['window_key']:[q['held_score_ratio'] for q in r['RF'] if q['receiver'] == 2]
        for r in ba['rows'] if r['case'] == 'DS23-0216'}
    receipt = dict(recorded_UTC=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress', this_turn_classification='progress', goal_achieved=False,
        objective='Full DS23 mean AND median position error<=0.5km; causal TLE, regional initialization, no GPS inference',
        previous_receipt=dict(path=str(previous.relative_to(ROOT)), sha256=sha(previous)),
        evidence={k:dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for k, p in roots.items()},
        scope=dict(saved_dual_IQ_panels=23, qualifying_windows=9, scans=['DS23-0154', 'DS23-0216'],
            engineering_windows=2, other_windows=7, not_new_scan_or_location_confirmation=True),
        implemented='one common physical receiver-clock contrast versus separate clocks and independent target gains, with full complex component covariance and training-only RF fits',
        ambiguity_finding=dict(pilot_CFO_alias_hz=1/4.4e-6, frame_phase_alias_hz=750.,
            one_pilot_alias_mod_frame_hz=(1/4.4e-6+375)%750-375,
            prior_apparent23Hz_disagreement_was_alias_bookkeeping_not_evidence_of_receiver_defect=True,
            corrected_0216_exact_and_periodic_comparisons=clock_finding['closure'],
            raw_carrier_differences_must_be_retained_before_frame_phase=True,
            exact_gain_and_full_covariance_rotation_required_when_removing750Hz_cycles=True,
            v1_common_clock_wrong_pilot_wrapping_outputs_preserved_not_promoted=True,
            v1_source_archive='/srv/bulk/leo/research/ds23-common-clock-v1-source-20261021'),
        carrier_branch_search=dict(joint_grid=[-1,0,1], jointly_refitted_two_component_branches=9,
            branch_selection_training_IQ_only=True, each_branch_iterations=24,
            independently_replayed_training_branch_profile_scores=ba['training_RF_branch_profile_replays'],
            RX2_0216_held_RF_energy_ratios=RF_ratios,
            other7windows_in0154_keep_original_branches=True,
            corrected_carrier_branches_do_not_by_themselves_qualify_a_clock_measurement=True),
        qualification=dict(v2_exact_primary_candidates=ca['primary_candidates'],
            v3_RF_branch_selected_primary_candidates=ba['primary_candidates'],
            v3_primary_with_all_component_prediction_support=ba['primary_candidates_with_all_component_prediction_support'],
            all_primary_failures_retained=True,
            clock_model_refits_each_audit=216, native_RF_selected_branch_refits_each_audit=36,
            branch_selected0216_still_fails_strict_common_vs_separate_minimum_gain=True,
            bottom_discrepancy_variance_boundary_can_be_legitimate_but_old_strict_screen_was_not_loosened=True,
            no_absolute_CFO_covariance_calibrated=True),
        retained_full_DS23_benchmark=position,
        all_new_RF_work_existing_local_IQ_only=True, new_RF_collection=False, subagents_spawned=False,
        focused_tests_passed=39, test_log=dict(path=str(tests), sha256=sha(tests)),
        all_jobs_this_iteration_terminal=True, no_position_variant_promoted=True,
        no_new_MD_progress_report_or_remote_push_without_position_generalization=True,
        next_actions=[
            'Build a direct joint raw-IQ two-receiver/two-component likelihood with shared transmitter gain per frame, one physical receiver-clock contrast, per-component complex channel ratio, native carrier and epoch/rate nuisance parameters.',
            'Use RF-selected physical carrier branches. Profile joint frame gains/DC, keep full carrier/clock/epoch/rate covariance, and test held-target IQ predicted from held-source IQ.',
            'Compare one versus two receiver-clock contrasts without adding independent per-track drift; do not force unsupported0154signal pairs to calibrate.',
            'Validate global750Hz branches using within-frame likelihood and total uncertainty using frame/symbol residual resampling; conditional gain noise alone is insufficient.',
            'Any localization use must replace or jointly model reused primary GLRT data and physical per-probe LO, not add an independent5Hz factor to the same IQ.',
            'Then run matched c0/fitted-c regional-cold positioning development and scan-disjoint confirmation with DBG01; publish only a positive generalizing position change.' ])
    target = OUT/'common_clock_ambiguity_and_carrier_branch_iteration_receipt.json'
    write(target, receipt)
    write(OUT/'current_iteration_receipt.json', receipt)
    state = read(OUT/'state.json')
    state.update(latest_goal_iteration_receipt=str(target.relative_to(ROOT)),
        latest_joint_common_clock_RF_audit=str((clock/'independent_replay_audit.json').relative_to(ROOT)),
        latest_training_only_RF_carrier_alias_audit=str((branch/'independent_replay_audit.json').relative_to(ROOT)),
        pilot_CFO_alias_and_frame_phase_alias_noncommutation_explains_apparent23Hz=True,
        apparent23Hz_is_not_established_receiver_or_TLE_error=True,
        RF_carrier_alias_search_has_held_frame_gains_but_no_qualified_position_correction=True,
        previous_goal_turn_classification='progress', this_turn_classification='progress', goal_achieved=False,
        focused_tests_passed=39, next_work=receipt['next_actions'],
        no_new_positive_generalization_report_published=True)
    write(OUT/'state.json', state)
    print(dict(receipt=str(target), unchanged_benchmark=position, RX2_RF_ratios=RF_ratios,
        primary_candidates=ba['primary_candidates'], tests=39), flush=True)


if __name__ == '__main__':
    main()
