"""Audit paired-frame uncertainty and disjoint RF-clock position sensitivity."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from audit_ds23_joint_receiver_iq import context, independent_Q
from ds23_joint_receiver_iq import JointReceiverIQ
from ds23_joint_iq_frame_bootstrap import FrameResampledJointIQ
from ds23_joint_component_rf import JointComponentWorkspace
from ds23_disjoint_rf_calibration import exclude_probes
from ds23_radio_calibration_factor import make_calibrated_problem, attach_calibrated_predictive
from probe_ds23_frequency_events import cached
from probe_ds23_sign_carrier_position import context_signed
from report_algo02_ds23 import position_error
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from run_algo01_ds23_sample import ROOT, read, write, sha

RF = ROOT/'reports/2026_10_21_ds23_joint_iq_frame_bootstrap'
PNT = ROOT/'reports/2026_10_21_ds23_joint_clock_position'
NATIVE = ROOT/'reports/2026_10_21_ds23_common_clock_alias_refit/evaluation.json'


def uncertainty_one(row):
    samples, fs, edge, epochs, segments = context(row)
    original = next(r for r in read(NATIVE)['rows'] if r['index'] == row['index'])
    noise = []
    for rx in [0, 1]:
        parameters = np.mean([np.asarray(f['native_training_fits'][rx]['parameters']) for f in original['folds']], axis=0)
        seeds = [dict(CFO_hz=p[0], offset_samples=p[1], modulation_ppm=p[2]) for p in parameters.reshape(2, 3)]
        ws = JointComponentWorkspace(samples[rx], fs, edge, epochs[rx], segments)
        fitted = ws.joint_fit(seeds)
        s = ws.statistics(fitted['parameters'], derivatives=False)
        noise.append(s['residual_energy']/max(1, s['sample_count']-3*len(segments)-3))
    np.testing.assert_allclose(noise, row['noise_variance'], atol=1e-8, rtol=1e-10)
    problem = JointReceiverIQ(samples, fs, edge, epochs, segments, noise)
    for full in row['full_start_trials']:
        fitted = problem.fit(np.asarray(full['history'][0]['parameters']), iterations=30)
        np.testing.assert_allclose(fitted['parameters'], full['parameters'], atol=1e-8, rtol=1e-10)
    assert row['full_fit']['quadratic'] == min(r['quadratic'] for r in row['full_start_trials'])
    rng = np.random.default_rng(2026102190+row['index'])
    max_Q = 0.
    optimized = 0
    for record in row['bootstrap_replicates']:
        while True:
            draw = rng.integers(0, len(segments), len(segments))
            if len(np.unique(draw)) >= 4:
                break
        np.testing.assert_array_equal(draw, record['draws'])
        ws = FrameResampledJointIQ(samples, fs, edge, epochs, segments, noise, draw)
        q = independent_Q(ws, np.asarray(record['parameters']))
        max_Q = max(max_Q, abs(q-record['quadratic']))
        np.testing.assert_allclose(q, record['quadratic'], atol=1e-6, rtol=1e-9)
        if record['index'] in [0, 31, 62]:
            refit = ws.fit(np.asarray(row['full_fit']['parameters']), iterations=16)
            np.testing.assert_allclose(refit['parameters'], record['parameters'], atol=1e-8, rtol=1e-10)
            optimized += 1
    frequencies = np.array([r['parameters'][:3] for r in row['bootstrap_replicates']])
    np.testing.assert_allclose(np.cov(frequencies, rowvar=False), row['bootstrap_frequency_covariance'], atol=1e-9, rtol=1e-10)
    return dict(index=row['index'], case=row['case'], window_key=row['entry']['window_key'],
        all63draws_and_weighted_objectives_replayed=True, max_Q_difference=max_Q,
        native_noise_RF_refits=2, full_joint_RF_refits=2, selected_bootstrap_optimization_refits=optimized,
        bootstrap_clock_sigma_hz=row['bootstrap_frequency_sigma_hz'][2],
        Gaussian_clock_sigma_hz=row['Gaussian_frequency_sigma_hz'][2],
        bootstrap_bound_replicates=row['bounded_replicates'],
        unconstrained_bootstrap_max_score=float(max(r['maximum_standardized_score'] for r in row['bootstrap_replicates'] if not r['boundary'])))


def position_case(case, selections=None):
    scan, node, original_mask, powers, means, hyper, original_entries, signed, _ = context_signed(case)
    directory = PNT/case
    plan = read(directory/'plan.json')
    result = []
    maximum_objective_difference = maximum_RF_decoder_difference = 0.
    for selection, selected in plan['plans'].items():
        if selections is not None and selection not in selections:
            continue
        base = make_calibrated_problem(scan, node, original_mask, 'c0', np.zeros(len(means)),
            powers, means, hyper, [], [], projected_receiver_basis)
        keep, entries, disjoint = exclude_probes(scan, base, original_mask, original_entries, selected['measurements'])
        np.testing.assert_array_equal(keep, selected['keep'])
        assert entries == selected['entries'] and disjoint == selected['disjoint']
        control = read(directory/f'{selection}_control.json')
        for noise in ['control', 'bootstrap', 'plus_radio']:
            record = read(directory/f'{selection}_{noise}.json')
            assert record['status'] == 'complete'
            measurements = record['measurements']
            if noise == 'control':
                assert measurements == []
            expected_measurements = [] if noise == 'control' else selected['measurements']
            for m, proposed in zip(measurements, expected_measurements, strict=True):
                sigma = proposed['sigma_hz'] if noise == 'bootstrap' else np.sqrt(proposed['sigma_hz']**2+2*scan.radio_sigma_hz**2)
                np.testing.assert_allclose(m['sigma_hz'], sigma)
            paired = record['paired_valid']
            qualified = paired
            for arm, saved in record['arms'].items():
                p = make_calibrated_problem(scan, node, keep, arm, np.asarray(saved['phase_reference']),
                    powers, means, hyper, [], measurements, projected_receiver_basis)
                attach_calibrated_predictive(p, entries, powers)
                cached(p)
                xy = np.asarray(saved['endpoint_east_north_km'])
                c, state = p.calculate(xy), p.state(xy)
                difference = c['negative_twice_elbo']-saved['negative_twice_elbo']
                maximum_objective_difference = max(maximum_objective_difference, abs(difference))
                np.testing.assert_allclose(difference, 0, atol=1e-6)
                max_innovation = 0.
                for k, m in enumerate(measurements):
                    physical = []
                    t = np.array([m['time_s']])
                    for rx in [1, 2]:
                        virtual = dict(times=t, receiver=rx, channel=m['channel'], rf_hz=m['rf_hz'])
                        physical.append(float((p.scan.hardware(virtual, state['beta'])
                            + m['rf_hz']/11.5e9*projected_receiver_basis(t)@state['smooth'][rx-1])[0]))
                    delta = physical[1]-physical[0]-(m['relative_CFO_hz']-c['calibration_residual_hz'][k])
                    maximum_RF_decoder_difference = max(maximum_RF_decoder_difference, abs(delta))
                    np.testing.assert_allclose(delta, 0, atol=1e-6)
                    max_innovation = max(max_innovation, abs(c['calibration_residual_hz'][k]/m['sigma_hz']))
                phase_limit = float(np.max(abs(np.asarray(state['phases']))))
                qualified = qualified and max_innovation <= 3 and phase_limit <= 15
                result.append(dict(case=case, selection=selection, noise=noise, arm=arm,
                    candidate_error_km=position_error(saved['endpoint_latlon']),
                    matched_control_error_km=position_error(control['arms'][arm]['endpoint_latlon']),
                    source_incumbent_error_km=position_error(signed['policy_arms'][arm]['endpoint_latlon']),
                    frequency_RMS_hz=saved['RMS_hz'], matched_control_RMS_hz=control['arms'][arm]['RMS_hz'],
                    original_track_gates_paired_pass=paired, maximum_RF_innovation_sigma=max_innovation,
                    maximum_phase_s=phase_limit, candidate_endpoint_latlon=saved['endpoint_latlon'],
                    matched_control_endpoint_latlon=control['arms'][arm]['endpoint_latlon'],
                    RF_points=len(measurements), GLRT_curved_points=saved['active_points'],
                    GLRT_predictive_points=saved['predictive_points'],
                    excluded_curved_points=selected['removed_curved_points'],
                    excluded_predictive_points=selected['removed_predictive_points'],
                    independent_calibration_IQ_verified=True))
            for row in result[-2:]:
                row['candidate_augmented_paired_pass'] = bool(qualified)
                row['policy_error_km'] = row['candidate_error_km'] if qualified else row['matched_control_error_km']
    return dict(case=case, rows=result, maximum_objective_difference=maximum_objective_difference,
        maximum_RF_decoder_difference=maximum_RF_decoder_difference,
        masked_controls_and_RF_arms_use_identical_GLRT_and_candidate_sets=True)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bootstrap = read(RF/'evaluation.json')
    assert bootstrap['all_terminal'] and all(r['status'] == 'complete' for r in bootstrap['rows'])
    with ProcessPoolExecutor(max_workers=6) as pool:
        uncertainty = [f.result() for f in as_completed([pool.submit(uncertainty_one, r) for r in bootstrap['rows']])]
    uncertainty.sort(key=lambda r:r['index'])
    write(RF/'independent_replay_audit.json', dict(rows=uncertainty, completed=len(uncertainty),
        weighted_bootstrap_objective_replays=63*len(uncertainty),
        full_joint_RF_refits=2*len(uncertainty), selected_bootstrap_refits=3*len(uncertainty),
        source_sha256=sha(RF/'evaluation.json'),
        no_absolute_covariance_coverage_established=True))
    positions = [position_case(case) for case in ['DS23-0154','DS23-0216']]
    rows = [r for result in positions for r in result['rows']]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    labels = [r['case'].split('-')[1]+'/'+r['window_key'].split('_')[1].lstrip('0') for r in uncertainty]
    x = np.arange(len(uncertainty))
    ax = axes[0]
    ax.scatter(x-.1, [r['Gaussian_clock_sigma_hz'] for r in uncertainty], label='Conditional Gaussian')
    ax.scatter(x+.1, [r['bootstrap_clock_sigma_hz'] for r in uncertainty], label='Paired-frame bootstrap')
    ax.set(ylabel='Receiver-clock sigma estimate(Hz)', title='63 whole paired-frame refits per window')
    ax.legend(fontsize=8)
    ax = axes[1]
    ax.scatter(x, [r['bootstrap_clock_sigma_hz']/r['Gaussian_clock_sigma_hz'] for r in uncertainty])
    ax.axhline(1, color='gray', lw=.7)
    ax.set(ylabel='Bootstrap / Gaussian sigma', title='Correlated frame errors change uncertainty')
    for ax in axes:
        ax.set_xticks(x, labels, rotation=65, ha='right')
    fig.suptitle('Conditional RF uncertainty estimates; absolute coverage and native-branch uncertainty unvalidated', fontsize=11)
    fig.savefig(RF/'paired_frame_uncertainty.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    methods = [('strict', 'control'), ('strict', 'bootstrap'), ('strict', 'plus_radio'),
        ('all_diagnostic', 'control'), ('all_diagnostic', 'bootstrap'), ('all_diagnostic', 'plus_radio')]
    labels = ['Prelim.control','Prelim.tight RF','Prelim.+radio noise','All control','All tight RF','All +radio noise']
    for ax, case in zip(axes, ['DS23-0154','DS23-0216'], strict=True):
        for offset, arm, color in [(-.12,'c0','tab:blue'),(.12,'fitted_c','tab:orange')]:
            selected = [next(r for r in rows if (r['case'],r['selection'],r['noise'],r['arm']) == (case,s,n,arm)) for s,n in methods]
            x = np.arange(len(selected))+offset
            ax.scatter(x, [r['candidate_error_km'] for r in selected], color=color, label=arm)
            bad = [k for k,r in enumerate(selected) if not r['candidate_augmented_paired_pass']]
            ax.scatter(x[bad], [selected[k]['candidate_error_km'] for k in bad], marker='x', s=80, color='crimson')
        ax.set_xticks(np.arange(6), labels, rotation=45, ha='right')
        ax.set(title=case, ylabel='Position error(km)')
        ax.legend(fontsize=8)
    fig.suptitle('Engineering RF-clock sensitivity: matched GLRT exclusions; redX fails gates\n'
        'Preliminary RF selection is not fully qualified by independent-target control; no method promoted', fontsize=11)
    fig.savefig(PNT/'matched_position_sensitivity.png', dpi=160)
    plt.close(fig)
    write(PNT/'independent_replay_evaluation.json', dict(rows=rows, case_audits=positions,
        position_endpoints_replayed=len(rows),
        all_RF_IQ_disjoint_from_retained_GLRT=True,
        no_position_variant_promoted=True,
        later_independent_target_control='reports/2026_10_21_ds23_joint_iq_independent_control/evaluation.json',
        improvement_on2inspected_scans_is_not_new_scan_generalization=True))
    print(dict(uncertainty_cases=len(uncertainty), position_endpoints=len(rows),
        objective_max=max(r['maximum_objective_difference'] for r in positions)), flush=True)


if __name__ == '__main__':
    main()
