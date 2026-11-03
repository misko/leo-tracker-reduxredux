"""Controlled position sensitivity to frame-resampled independent RF clocks.

All GLRT data from a calibration probe are removed in both matched arms.
The RF covariance is still an engineering estimate; no production promotion.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_disjoint_rf_calibration import exclude_probes
from ds23_radio_calibration_factor import make_calibrated_problem, attach_calibrated_predictive, principal_radio_contrast
from investigate_dsx01_localization_failures import fit
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_frequency_events import cached, summary
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_joint_clock_position'
RF = ROOT/'reports/2026_10_21_ds23_joint_iq_frame_bootstrap'
RAW = ROOT/'reports/2026_10_21_ds23_joint_receiver_iq'
CASES = ['DS23-0154', 'DS23-0216']
ARMS = ('c0', 'fitted_c')


def prepare(case):
    directory = OUT/case
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/'plan.json'
    if path.exists():
        return read(path)
    scan, node, keep, powers, means, hyper, entries, signed, signed_path = context_signed(case)
    for i, track in enumerate(scan.tracks):
        np.testing.assert_allclose(scan.rx_basis[i], projected_receiver_basis(track['times']), atol=1e-12, rtol=0)
    tracking_path = ROOT/'reports/2026_10_19_algo02_ds23_full'/case/'tracking.json'
    tracking = read(tracking_path)
    source = tracking.get('source', tracking)
    first_counter = min(p['valid_start_counter'] for p in source['probes'])
    bootstrap = [r for r in read(RF/'evaluation.json')['rows'] if r['case'] == case]
    raw = {r['index']:r for r in read(RAW/'evaluation.json')['rows'] if r['case'] == case}
    measurements = []
    for row in bootstrap:
        entry = row['entry']
        p = next(p for p in source['probes'] if p['visit_index'] == entry['visit_index'] and p['receiver_id'] == 0)
        if p['valid_start_counter'] != entry['sample_counter']:
            raise ValueError('saved RF window differs from native probe counter')
        midpoint = (p['valid_start_counter']-first_counter)/source['sample_rate_hz']+.01
        sigma = max(5., row['bootstrap_frequency_sigma_hz'][2], row['fold_clock_difference_hz']/np.sqrt(2))
        measurements.append(dict(index=row['index'], visit_index=entry['visit_index'], time_s=midpoint,
            channel=entry['channel'], rf_hz=entry['rf_hz'],
            relative_CFO_hz=float(principal_radio_contrast(row['full_fit']['receiver_clock_hz'][0])),
            raw_relative_CFO_hz=row['full_fit']['receiver_clock_hz'][0], sigma_hz=float(sigma),
            strict_candidate=raw[row['index']]['conditional_raw_IQ_common_clock_candidate'],
            bootstrap_bounds=row['bounded_replicates'], bootstrap_rank_deficiencies=row['rank_deficient_replicates']))
    # Fix each RF policy before any position outcomes are calculated.
    plans = {}
    for selection in ['strict', 'all_diagnostic']:
        chosen = [r for r in measurements if selection == 'all_diagnostic' or r['strict_candidate']]
        base = make_calibrated_problem(scan, node, keep, 'c0', np.zeros(len(means)), powers, means, hyper, [], [], projected_receiver_basis)
        mask, predictive, disjoint = exclude_probes(scan, base, keep, entries, chosen)
        plans[selection] = dict(measurements=chosen, keep=mask, entries=predictive, disjoint=disjoint,
            removed_curved_points=len(disjoint['removed_curved_ids']),
            removed_predictive_points=len(disjoint['removed_predictive_ids']))
    null = {}
    for arm in ARMS:
        saved = signed['policy_arms'][arm]
        p = make_calibrated_problem(scan, node, keep, arm, np.asarray(saved['phase_reference']), powers, means, hyper, [], [], projected_receiver_basis)
        attach_calibrated_predictive(p, entries, powers)
        cached(p)
        delta = p.calculate(np.asarray(saved['endpoint_east_north_km']))['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta) > 1e-5:
            raise ValueError('disabled calibration fails signed-incumbent replay: '+str(delta))
        null[arm] = float(delta)
    result = dict(case=case, plans=plans, source_incumbent=signed['policy_arms'],
        signed_path=str(signed_path), signed_sha256=sha(signed_path),
        bootstrap_sha256=sha(RF/'evaluation.json'), raw_IQ_sha256=sha(RAW/'evaluation.json'),
        tracking_sha256=sha(tracking_path), original_endpoint_replay_differences=null,
        radio_sigma_hz=scan.radio_sigma_hz, no_GPS_TLE_or_satellite_selection_in_RF_calibration=True)
    write(path, result)
    return result


def one(job):
    case, selection, noise = job
    path = OUT/case/f'{selection}_{noise}.json'
    if path.exists():
        return read(path)
    began = time.monotonic()
    def timeout(*_):
        raise TimeoutError('180second paired position sensitivity cap')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    try:
        plan = read(OUT/case/'plan.json')
        scan, node, _, powers, means, hyper, _, _, signed_path = context_signed(case)
        assert sha(signed_path) == plan['signed_sha256']
        selected = plan['plans'][selection]
        keep = np.asarray(selected['keep'], bool)
        entries = selected['entries']
        measurements = [] if noise == 'control' else selected['measurements']
        if noise == 'plus_radio':
            measurements = [dict(r, sigma_hz=float(np.sqrt(r['sigma_hz']**2+2*scan.radio_sigma_hz**2))) for r in measurements]
        pair = {}
        for arm in ARMS:
            x = np.zeros(2)
            reference = np.zeros(len(means))
            history = []
            for _ in range(5):
                p = make_calibrated_problem(scan, node, keep, arm, reference, powers, means, hyper, [], measurements, projected_receiver_basis)
                attach_calibrated_predictive(p, entries, powers)
                cached(p)
                fitted = fit(p, x, iterations=48)
                x = np.asarray(fitted['parameters'])
                phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
                change = float(np.max(abs(phase-reference)))
                history.append(dict(fit=fitted, phase_change_s=change))
                reference = phase
            result = summary(p, x, entries)
            result.update(history=history, final_phase_change_s=change)
            if measurements:
                c = p.calculate(x)
                result.update(calibration_residual_hz=c['calibration_residual_hz'], calibration_sigma_hz=c['calibration_sigma_hz'])
            pair[arm] = result
        accepted = pair_passes(pair, include_linear=True)
        result = dict(case=case, selection=selection, noise=noise, status='complete', arms=pair,
            paired_valid=accepted, measurements=measurements, calibration_GLRT_IQ_disjoint=True,
            no_GPS_in_initialization_optimization_or_policy=True,
            full25km_regional_box_and_cold_center_start=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(case=case, selection=selection, noise=noise, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-began
    write(path, result)
    print(case, selection, noise, result['status'], result.get('paired_valid'), result.get('error'), flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    protocol = dict(cases=CASES, selections=['strict','all_diagnostic'], noise=['control','bootstrap','plus_radio'],
        RF_evaluation_sha256=sha(RF/'evaluation.json'), raw_IQ_evaluation_sha256=sha(RAW/'evaluation.json'),
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name, 'ds23_disjoint_rf_calibration.py',
            'ds23_radio_calibration_factor.py', 'ds23_frequency_events.py']},
        matched_c0_fitted_c=True, workers=6, per_pair_seconds=180,
        region_center=[37.906,-122.545], regional_box_width_km=25, cold_start=[0,0], phase_rounds=5, steps_per_round=48,
        mask_control='all graph and predictive GLRT from each reused physical RF probe removed in both matched arms',
        bootstrap_sigma='max5Hz,paired-frame clock SD,fold clock difference/sqrt2; engineering sensitivity, not calibrated absolute error',
        plus_radio_sigma='quadrature addition of2*original radio-noise variance for unknown per-probe LO differences',
        same_observations_candidates_other_priors_and_budgets_per_controlled_pair=True,
        all_diagnostic_RF_policy_not_qualified_or_promoted=True,
        no_GPS_new_RF_following_TLE_or_location_specific_satellite_selection=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen disjoint RF clock position sensitivity protocol changed')
    if not target.exists():
        write(target, protocol)
    for case in CASES:
        prepare(case)
    jobs = [(case, selection, noise) for case in CASES for selection in protocol['selections'] for noise in protocol['noise']]
    with ProcessPoolExecutor(max_workers=6) as pool:
        results = [f.result() for f in as_completed([pool.submit(one, j) for j in jobs])]
    write(OUT/'execution.json', dict(rows=results, all_terminal=True, no_position_method_promoted=True))


if __name__ == '__main__':
    main()
