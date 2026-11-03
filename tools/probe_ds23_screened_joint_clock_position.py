"""Repeat the matched position test after the independent-target RF control."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

import probe_ds23_joint_clock_position as engine
import audit_ds23_joint_iq_uncertainty_position as audit
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_screened_joint_clock_position_v2'
ORIGINAL_RF = ROOT/'reports/2026_10_21_ds23_joint_receiver_iq/evaluation.json'
INDEPENDENT = ROOT/'reports/2026_10_21_ds23_joint_iq_independent_control/evaluation.json'


def configure():
    engine.OUT = OUT
    engine.RAW = OUT/'screened_RF'


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    OUT.mkdir(exist_ok=True)
    original, independent = read(ORIGINAL_RF), read(INDEPENDENT)
    allowed = set(independent['common_clock_candidates_also_beating_independent'])
    filtered = dict(rows=[dict(index=r['index'], case=r['case'],
        conditional_raw_IQ_common_clock_candidate=r['index'] in allowed) for r in original['rows']],
        original_RF_sha256=sha(ORIGINAL_RF), independent_target_control_sha256=sha(INDEPENDENT),
        screen='original common-clock tests AND both RX/frame folds beat independent target raw-IQ prediction',
        absolute_frequency_covariance_and_cross_location_generalization_not_established=True)
    source = OUT/'screened_RF/evaluation.json'
    source.parent.mkdir(exist_ok=True)
    if source.exists() and read(source) != filtered:
        raise ValueError('frozen independent-target RF screen changed')
    if not source.exists():
        write(source, filtered)
    configure()
    protocol = dict(cases=engine.CASES, jobs=[(case, 'strict', noise) for case in engine.CASES
        for noise in ['control','bootstrap','plus_radio']],
        screened_RF_sha256=sha(source), bootstrap_RF_sha256=sha(engine.RF/'evaluation.json'),
        source_tools={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_screened_joint_clock_position.py',
            'probe_ds23_joint_clock_position.py', 'ds23_disjoint_rf_calibration.py', 'ds23_radio_calibration_factor.py']},
        regional_box_km=25, cold_start=[0,0], matched_c0_fitted_c=True,
        phase_rounds=5, steps_per_round=48, workers=6, per_pair_seconds=180,
        same_disjoint_GLRT_mask_for_control_and_calibration=True,
        no_GPS_future_TLE_or_satellite_selection_used=True,
        no_position_variant_promoted=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen screened RF position sensitivity changed')
    if not target.exists():
        write(target, protocol)
    for case in engine.CASES:
        engine.prepare(case)
    with ProcessPoolExecutor(max_workers=6, initializer=configure) as pool:
        results = [f.result() for f in as_completed([pool.submit(engine.one, tuple(job)) for job in protocol['jobs']])]
    assert all(r['status'] == 'complete' for r in results)
    audit.PNT = OUT
    audited = [audit.position_case(case, selections=['strict']) for case in engine.CASES]
    rows = [r for result in audited for r in result['rows']]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    methods = ['control','bootstrap','plus_radio']
    for ax, case in zip(axes, engine.CASES, strict=True):
        for offset, arm, color in [(-.1,'c0','tab:blue'),(.1,'fitted_c','tab:orange')]:
            selected = [next(r for r in rows if r['case']==case and r['arm']==arm and r['noise']==n) for n in methods]
            x = np.arange(3)+offset
            ax.scatter(x, [r['candidate_error_km'] for r in selected], color=color, label=arm)
            bad = [k for k,r in enumerate(selected) if not r['candidate_augmented_paired_pass']]
            ax.scatter(x[bad], [selected[k]['candidate_error_km'] for k in bad], marker='x', color='crimson', s=80)
        ax.set_xticks(np.arange(3), ['Matched control','RF bootstrap floor','RF + radio noise'], rotation=25, ha='right')
        ax.set(title=case, ylabel='Position error(km)')
        ax.legend(fontsize=8)
    fig.suptitle('Independent-target-screened RF clocks:2windows in0154;0216falls back\n'
        'Engineering uncertainty; no new-scan or full-DS23 accuracy improvement established', fontsize=11)
    fig.savefig(OUT/'screened_position_sensitivity.png', dpi=160)
    plt.close(fig)
    write(OUT/'independent_replay_evaluation.json', dict(rows=rows, case_audits=audited,
        screened_RF_indices=sorted(allowed), all_RF_and_GLRT_IQ_disjoint=True,
        no_cross_scan_position_generalization_or_method_promotion=True))
    write(OUT/'execution.json', dict(rows=results, all_terminal=True))
    print([(r['case'],r['noise'],r['arm'],round(r['candidate_error_km'],6),r['candidate_augmented_paired_pass']) for r in rows], flush=True)


if __name__ == '__main__':
    main()
