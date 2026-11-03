"""Bounded shared-phase mean refits on the nine frozen paired-IQ windows.

This experiment changes no position result. All RF starts, variances and model
choices use training IQ; the untouched opposite frame parity checks prediction.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib
import signal
import time

import numpy as np

from ds23_phase_marginal_iq import PhaseMarginalIQ
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from ds23_joint_gain_controls import frame_coefficients
from probe_ds23_joint_receiver_iq import SOURCE, OUT as RAW
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_phase_marginal_iq'
BULK = Path('/srv/bulk/leo/research/ds23-phase-marginal-iq-20261021')
CONTROL = ROOT/'reports/2026_10_21_ds23_joint_iq_independent_control/evaluation.json'


def one(row):
    index, entry = row['index'], row['entry']
    path = BULK/f'probe{index:03d}.json'
    if path.exists():
        return read(path)
    began = time.monotonic()
    def timeout(*_):
        raise TimeoutError('240second joint phase-marginal RF refit cap')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(240)
    try:
        with np.load(entry['panel'], allow_pickle=False) as panel:
            values = panel[entry['window_key']]
        assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
        samples = np.array([values[:, r, 0].astype(float)+1j*values[:, r, 1] for r in [0, 1]])
        fs, edge, epochs = entry['sample_rate_hz'], entry['edge'], np.asarray(row['aligned_epochs'])
        geometries = [fractional_geometry(y, fs, edge, epochs[k, r], dict(
            CFO_hz=entry['components'][k]['peaks'][r]['fractional_tracking_cfo_hz'],
            offset_samples=0., modulation_ppm=0.)) for r, y in enumerate(samples) for k in [0, 1]]
        segments = common_segments(geometries)
        raw = next(r for r in read(RAW/'evaluation.json')['rows'] if r['index'] == index)
        control = next(r for r in read(CONTROL)['rows'] if r['index'] == index)
        folds = []
        for fold in row['folds']:
            parity = fold['parity']
            support = [ix for k, ix in enumerate(segments) if k % 2 == parity]
            held = [ix for k, ix in enumerate(segments) if k % 2 != parity]
            native = [np.asarray(f['parameters']) for f in fold['native_training_fits']]
            noise = []; gain = None
            for r in [0, 1]:
                ws = JointComponentWorkspace(samples[r], fs, edge, epochs[:, r], support)
                statistics = ws.statistics(native[r], derivatives=False)
                noise.append(statistics['residual_energy']/max(1, statistics['sample_count']-3*len(support)-3))
                if r == 0:
                    coefficient, covariance = frame_coefficients(samples[r], ws.columns(native[r]), support)
                    gain = np.maximum(np.mean(abs(coefficient)**2, axis=0)
                        - np.mean(np.diagonal(covariance, axis1=1, axis2=2).real, axis=0), 1e-12)
            old = next(f for f in raw['folds'] if f['parity'] == parity)
            models = {}
            for name, separate, phase in [('common_zero', False, False),
                    ('common_phase', False, True), ('separate_phase', True, True)]:
                problem = PhaseMarginalIQ(samples, fs, edge, epochs.T, support, noise, gain,
                    separate_clocks=separate)
                seed = np.asarray(old['models']['separate' if separate else 'common']['fit']['parameters'])
                trials = [problem.fit(seed, fit_sigma=phase, sigma_start=sigma, maxiter=60)
                    for sigma in ([.15, .7] if phase else [.0])]
                fitted = min(trials, key=lambda f:f['training_NLL'])
                predictions = [problem.predict(fitted, held, source_receiver=r) for r in [0, 1]]
                independently_replayed = problem.statistics(fitted['full_parameters'],
                    fixed_sigma=None if phase else 0., gradient=False)['NLL']
                if abs(independently_replayed-fitted['training_NLL']) > 1e-6:
                    raise ValueError('training marginal likelihood replay failed')
                fine = PhaseMarginalIQ(samples, fs, edge, epochs.T, support, noise, gain,
                    separate_clocks=separate, grid_size=8192)
                fine_NLL = fine.statistics(fitted['full_parameters'],
                    fixed_sigma=None if phase else 0., gradient=False)['NLL']
                models[name] = dict(fit=fitted, trials=trials, predictions=predictions,
                    training_replay_difference=independently_replayed-fitted['training_NLL'],
                    quadrature8192_minus2048_NLL=fine_NLL-independently_replayed)
            comparisons = []
            for r in [0, 1]:
                independent = next(q for q in control['records']
                    if q['parity'] == parity and q['source_receiver'] == r+1)
                common = models['common_phase']['predictions'][r]['NLL']
                comparisons.append(dict(source_receiver=r+1,
                    common_phase_vs_zero_held_gain=models['common_zero']['predictions'][r]['NLL']-common,
                    common_phase_vs_separate_phase_held_gain=models['separate_phase']['predictions'][r]['NLL']-common,
                    common_phase_vs_independent_target_held_gain=independent['independent_target_raw_NLL']-common))
            folds.append(dict(parity=parity, models=models, comparisons=comparisons,
                noise_variance=noise, source_gain_variance=gain))
        checks = dict(training_optimizers_converged=all(f['models']['common_phase']['fit']['converged'] for f in folds),
            common_RF_and_phase_interiors=all(not f['models']['common_phase']['fit']['boundary']
                and not f['models']['common_phase']['fit']['phase_variance_boundary'] for f in folds),
            positive_phase_vs_zero_prediction=all(q['common_phase_vs_zero_held_gain'] > 0 for f in folds for q in f['comparisons']),
            positive_phase_vs_independent_prediction=all(q['common_phase_vs_independent_target_held_gain'] > 0
                for f in folds for q in f['comparisons']),
            positive_common_vs_separate_prediction=all(q['common_phase_vs_separate_phase_held_gain'] > 0
                for f in folds for q in f['comparisons']),
            quadrature_converged=all(abs(m['quadrature8192_minus2048_NLL']) < .01 for f in folds for m in f['models'].values()))
        result = dict(index=index, case=entry['case'], entry=entry, status='complete', folds=folds,
            checks=checks, all_checks_pass=all(checks.values()),
            absolute_clock_uncertainty_and_transmitter_correspondence_not_qualified=True,
            no_position_result_changed=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(index=index, case=entry['case'], entry=entry, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-began
    write(path, result)
    print(index, entry['case'], result['status'], result.get('all_checks_pass'), result.get('error'), flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    protocol = dict(source_sha256=sha(SOURCE), raw_zero_phase_sha256=sha(RAW/'evaluation.json'),
        independent_control_sha256=sha(CONTROL), workers=6, per_window_seconds=240,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name, 'ds23_phase_marginal_iq.py',
            'ds23_training_channel_rf.py','ds23_shared_receiver_phase.py']},
        common15_or_separate16_RF_parameters_plus_one_log_phase_SD=True,
        normalized_joint_training_density_with_training_only_fixed_Gaussian_TX_gain_power=True,
        zero_phase_control_uses_same_Gaussian_gain_power_prior=True,
        phase_sigma_starts_rad=[.15,.7], iterations_per_start=60,
        two_frame_parity_folds=True, held_target_signal_and_phase_never_fitted=True,
        clock_carrier_code_ratios_and_phase_variance_jointly_refit=True,
        previous_branch_corrected_native_acquisition_conditioned=True,
        no_GPS_TLE_satellite_ID_new_RF_or_position_used=True,
        no_absolute_clock_covariance_or_location_gain_claimed=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen phase-marginal refit protocol changed')
    if not target.exists():write(target, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one,r) for r in read(SOURCE)['rows']])]
    write(OUT/'evaluation.json', dict(rows=sorted(rows,key=lambda r:r['index']),
        all_terminal=True, protocol_sha256=sha(target), no_position_method_promoted=True))


if __name__ == '__main__':main()
