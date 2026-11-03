"""Matched position experiment after independently predicted joint RF fits.

Original observations, associations, priors, noise scales and residual gates
remain fixed. Identical RF-qualified probes are remeasured in three arms.
Different measurement values mean their in-sample position objectives must
not be used to choose which arm to report or deploy.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, summary
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_shared_probe_position import refine_original
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha
from probe_ds23_joint_component_full_curves import OUT as RF, BULK as RF_BULK

OUT = ROOT/'reports/2026_10_21_ds23_joint_RF_position'
BULK = Path('/srv/bulk/leo/research/ds23-joint-RF-position-20261021')
MODELS = ['separate_refinement', 'joint_frequency', 'joint_all_six']


def prepare(case):
    context = context_signed(case); scan = context[0]
    protocol = read(RF/'protocol.json'); evaluation = read(RF/'evaluation.json')
    if not evaluation['all_terminal'] or evaluation['complete'] != len(protocol['jobs']):
        raise ValueError('all raw joint refinements must finish before position evaluation')
    for name, digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != digest: raise ValueError('joint RF source changed')
    by_probe = {(r['case'], r['probe']): r for r in evaluation['rows']}
    selected = [(item, by_probe[case, item['job']['probe']]) for item in protocol['jobs']
                if item['job']['case'] == case and by_probe[case, item['job']['probe']]['qualified_for_full_curve_test']]
    scans, updates = {}, {}
    for model in MODELS:
        jobs, rows = [], []
        for item, result in selected:
            jobs.append(item['job']); row = dict(item['fit'])
            if model != 'separate_refinement':
                parameters = result['frequency_only' if model == 'joint_frequency' else 'full']['parameters']
                for offset, role in [(0, 'first'), (3, 'second')]:
                    row[role+'_fit'] = dict(row[role+'_fit'], CFO_hz=parameters[offset])
            rows.append(row)
        scans[model], updates[model] = refine_original(scan, jobs, rows)
    if len({tuple(sorted(v)) for v in updates.values()}) != 1:
        raise ValueError('RF variants changed different physical observations')
    return context, scans, updates


def problem(context, scan, arm, reference):
    _, node, mask, powers, means, hyper, entries, *_ = context
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
    attach_event_predictive(p, entries, powers)
    return p


def refit(context, scan, arm):
    reference = np.zeros(len(context[4])); x = np.zeros(2); history = []
    for _ in range(5):
        p = cached(problem(context, scan, arm, reference)); fitted = fit(p, x, iterations=48)
        x = np.asarray(fitted['parameters']); phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase-reference))); history.append(dict(fit=fitted, phase_change_s=change)); reference = phase
    record = summary(p, x, context[6]); record.update(history=history, final_phase_change_s=change)
    return record


def run(case):
    path = BULK/(case+'.json')
    if path.exists(): return read(path)
    started = time.monotonic()
    def timeout(*_): raise TimeoutError('600-second joint-RF position budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(600)
    try:
        context, scans, updates = prepare(case); signed, source = context[-2:]; incumbent = signed['policy_arms']; replay = {}
        for arm, old in incumbent.items():
            p = problem(context, context[0], arm, np.array(old['phase_reference']))
            r = summary(p, np.array(old['endpoint_east_north_km']), context[6]); delta = r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta) > 1e-6 or r['linear_calibration_max_difference'] != 0: raise ValueError('incumbent does not replay')
            replay[arm] = delta
        models = {}
        for model in MODELS:
            pair = {arm: refit(context, scans[model], arm) for arm in ARMS}
            accepted = valid(pair)
            models[model] = dict(arms=pair, paired_valid=accepted, policy_arms=pair if accepted else incumbent)
            print(case, model, 'original paired gates', accepted, 'updates', len(updates[model]), flush=True)
        record = dict(case=case, status='complete', models=models, updates=updates, incumbent_arms=incumbent,
            exact_incumbent_replay=replay, source_signed_sha256=sha(source), original_mask=context[2],
            powers=context[3], means_s=context[4], hyper=context[5], entries=context[6],
            RF_evaluation_sha256=sha(RF/'evaluation.json'), no_GPS_future_TLE_or_phase_continuity=True,
            original_observations_labels_aliases_noise_scales_and_gates_preserved=True,
            all_models_same_RF_qualified_observation_ids=True, frequency_fit_scores_not_used_for_arm_selection=True)
    except Exception as exc: record = dict(case=case, status='failed', error=repr(exc))
    finally: signal.alarm(0)
    record['seconds'] = time.monotonic()-started; write(path, record); return record


def audit_case(case):
    saved = read(BULK/(case+'.json'))
    if saved['status'] != 'complete': raise ValueError(f'{case}: position experiment incomplete')
    context, scans, updates = prepare(case); signed, source = context[-2:]
    if saved['source_signed_sha256'] != sha(source) or saved['incumbent_arms'] != signed['policy_arms']: raise ValueError('incumbent changed')
    for actual, expected in [(context[2], saved['original_mask']), (context[3], saved['powers']), (context[4], saved['means_s'])]:
        np.testing.assert_array_equal(actual, expected)
    if saved['hyper'] != context[5] or saved['entries'] != context[6] or updates != saved['updates']: raise ValueError('matched observations/priors changed')
    rows = [dict(case=case, method='incumbent', arm=a, policy_latlon=r['endpoint_latlon'], trial_latlon=r['endpoint_latlon'],
        paired_valid=True, frequency_RMS_hz=r['RMS_hz']) for a, r in signed['policy_arms'].items()]
    for model, record in saved['models'].items():
        pair = {}
        for arm, old in record['arms'].items():
            p = problem(context, scans[model], arm, np.array(old['phase_reference']))
            r = summary(p, np.array(old['endpoint_east_north_km']), context[6]); delta = r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta) > 1e-6 or r['linear_calibration_max_difference'] != 0: raise ValueError('RF objective or no-linear-calibration replay failed')
            for key in ['gates', 'linear_gates']:
                a, b = (r[key]['tracks'], old[key]['tracks']) if key == 'gates' else (r[key], old[key])
                if [(v['component'], v['compatible']) for v in a] != [(v['component'], v['compatible']) for v in b]: raise ValueError('original residual gates changed')
            r['final_phase_change_s'] = old['final_phase_change_s']; pair[arm] = r
            rows.append(dict(case=case, method=model, arm=arm, trial_latlon=r['endpoint_latlon'],
                policy_latlon=record['policy_arms'][arm]['endpoint_latlon'], paired_valid=record['paired_valid'],
                objective_replay_difference=delta, frequency_RMS_hz=r['RMS_hz'], updated_original_points=len(updates[model]),
                failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],
                failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
        if valid(pair) != record['paired_valid'] or record['policy_arms'] != (record['arms'] if record['paired_valid'] else signed['policy_arms']):
            raise ValueError('paired adoption or exact fallback changed')
    return rows


def audit():
    protocol = read(OUT/'protocol.json')
    for name, digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != digest: raise ValueError('position scientific source changed')
    with ProcessPoolExecutor(max_workers=7) as pool:
        rows = [row for future in as_completed([pool.submit(audit_case, case) for case in protocol['cases']]) for row in future.result()]
    from report_algo02_ds23 import position_error
    for row in rows:
        row['position_error_km'] = position_error(row['policy_latlon']); row['trial_position_error_km'] = position_error(row['trial_latlon'])
    statistics = {model: {arm: dict(mean_km=float(np.mean([r['position_error_km'] for r in rows if (r['method'],r['arm']) == (model,arm)])),
        median_km=float(np.median([r['position_error_km'] for r in rows if (r['method'],r['arm']) == (model,arm)])),
        accepted=sum(r['paired_valid'] for r in rows if (r['method'],r['arm']) == (model,arm))) for arm in ARMS}
        for model in ['incumbent']+MODELS}
    write(OUT/'independent_replay_audit.json', dict(rows=rows, statistics=statistics,
        same_original_physical_observations_in_all_arms=True, original_gates_and_exact_fallback_verified=True,
        no_GPS_in_inference_or_RF_case_selection=True, development_cases_not_untouched_generalization=True,
        RF_objectives_with_different_measurements_not_compared=True, full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True); cases = protocol['cases']; xx = np.arange(len(cases))
    for i, model in enumerate(['incumbent']+MODELS):
        values = [next(r['position_error_km'] for r in rows if (r['case'],r['method'],r['arm']) == (case,model,'fitted_c')) for case in cases]
        axes[0].bar(xx+(i-1.5)*.2, values, width=.19, label=model.replace('_', ' '))
    axes[0].set(xticks=xx, xticklabels=[c[-4:] for c in cases], xlabel='DS23 scan', ylabel='Policy position error (km)')
    axes[0].legend(fontsize=7); axes[0].grid(axis='y', alpha=.2)
    for model in ['incumbent']+MODELS:
        values = sorted(r['position_error_km'] for r in rows if r['method'] == model and r['arm'] == 'fitted_c')
        axes[1].step(values, np.arange(1,len(values)+1)/len(values), where='post', label=model.replace('_', ' '))
    axes[1].set(xlabel='Policy position error (km)', ylabel='Empirical cumulative fraction'); axes[1].grid(alpha=.2); axes[1].legend(fontsize=7)
    fig.suptitle('Does jointly refining simultaneous received components improve position?\nSame RF-qualified original points, labels and noise priors; original gates and exact fallback; fitted c shown')
    fig.savefig(OUT/'position_comparison.png', dpi=160); plt.close(fig)
    print(statistics, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--stage', choices=['run','audit'], required=True); args = parser.parse_args()
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    if args.stage == 'audit': audit(); return
    protocol = dict(cases=read(RF/'protocol.json')['cases'], models=MODELS, workers=7, per_case_seconds=600,
        paired_c0_fitted_c=True, cold_start=[0,0], regional_center=[37.906,-122.545], regional_width_km=25,
        phase_rounds=5, position_iterations=48, unchanged_observation_population_and_labels=True,
        unchanged_orbit_radio_noise_and_fragment_bias_priors_and_original_gates=True,
        adopt='all original paired residual gates and phase convergence; exact incumbent otherwise',
        no_GPS_future_TLE_RF_collection_or_in_sample_RF_arm_selection=True,
        RF_evaluation_sha256=sha(RF/'evaluation.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__), ROOT/'tools/probe_ds23_shared_probe_position.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol: raise ValueError('joint-RF position protocol changed')
    if not path.exists(): write(path, protocol)
    with ProcessPoolExecutor(max_workers=7) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run,case) for case in protocol['cases']])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True, failures=[r for r in rows if r['status'] != 'complete']))


if __name__ == '__main__': main()
