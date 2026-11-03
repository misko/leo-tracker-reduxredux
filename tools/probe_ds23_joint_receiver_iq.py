"""Bounded raw-IQ common-clock qualification on nine previously pinned windows."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib
import signal
import time
import numpy as np

from ds23_joint_receiver_iq import JointReceiverIQ
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from ds23_joint_gain_controls import frame_coefficients
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT/'reports/2026_10_21_ds23_common_clock_alias_refit/evaluation.json'
OUT = ROOT/'reports/2026_10_21_ds23_joint_receiver_iq'
BULK = Path('/srv/bulk/leo/research/ds23-joint-receiver-iq-20261021')


def one(row):
    index, entry = row['index'], row['entry']
    path = BULK/f'probe{index:03d}.json'
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('240second joint raw-IQ carrier/receiver-clock cap')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(240)
    try:
        with np.load(entry['panel'], allow_pickle=False) as panel:
            values = panel[entry['window_key']]
        assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
        samples = np.array([values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]])
        fs, edge, epochs = entry['sample_rate_hz'], entry['edge'], np.asarray(row['aligned_epochs'])
        initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
            offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
        geometries = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
            for rx, y in enumerate(samples) for k in [0, 1]]
        segments = common_segments(geometries)
        times = np.array([ix.mean()/fs for ix in segments])
        np.testing.assert_array_equal(times, row['time_s'])
        folds = []
        for fold in row['folds']:
            parity = fold['parity']
            train = np.arange(len(segments)) % 2 == parity
            support = [ix for k, ix in enumerate(segments) if train[k]]
            held = [ix for k, ix in enumerate(segments) if not train[k]]
            native = [np.array(f['parameters']) for f in fold['native_training_fits']]
            coefficients, variances, sigma = [], [], []
            for rx in [0, 1]:
                ws = JointComponentWorkspace(samples[rx], fs, edge, epochs[:, rx], support)
                statistics = ws.statistics(native[rx], derivatives=False)
                noise = statistics['residual_energy']/max(1, statistics['sample_count']-3*len(support)-3)
                sigma.append(noise)
                c, covariance = frame_coefficients(samples[rx], ws.columns(native[rx]), support)
                coefficients.append(c)
                variances.append(np.diagonal(covariance, axis1=1, axis2=2).real)
            raw_delta = native[1][::3]-native[0][::3]
            if np.ptp(raw_delta) >= 375:
                raise ValueError('RF-selected component clocks require unresolved physical carrier branches')
            clock_record = next(r for r in fold['records'] if r['variant'] == 'exact_sample_times' and r['direction'] == 0)
            clock = float(clock_record['models']['common']['fit']['corrected_RX_delta_hz'][0])
            if abs(clock-raw_delta[0]) > 375:
                raise ValueError('clock initialization is outside the native physical750Hz branch')
            code = np.r_[native[0].reshape(2, 3)[:, 1:].ravel(), native[1].reshape(2, 3)[:, 1:].ravel()]
            models = {}
            for mode, alias in [('common', 0), ('separate', 0), ('common_alias_minus750', -1), ('common_alias_plus750', 1)]:
                separate = mode == 'separate'
                clocks = np.full(2 if separate else 1, clock+alias*750)
                residual_clock = clock+alias*750-raw_delta
                ratio = []
                for k in [0, 1]:
                    a, b = coefficients[0][:, k], coefficients[1][:, k]
                    w = 1/(variances[0][:, k]+variances[1][:, k])
                    correction = np.exp(-2j*np.pi*residual_clock[k]*(times[train]-(len(samples[0])-1)/(2*fs)))
                    ratio.append(np.sum(w*a.conj()*b*correction)/np.sum(w*abs(a)**2))
                ratio = np.array(ratio)
                start = np.r_[native[0][::3], clocks, code, np.column_stack((ratio.real, ratio.imag)).ravel()]
                problem = JointReceiverIQ(samples, fs, edge, epochs.T, support, sigma, separate_clocks=separate)
                fitted = problem.fit(start, iterations=30)
                predictions = [problem.predict(fitted['parameters'], held, source_receiver=r) for r in [0, 1]]
                models[mode] = dict(fit=fitted, predictions=predictions,
                    noise_variance_from_training_IQ_only=sigma,
                    complex_training_samples=2*len(np.concatenate(support)),
                    complex_held_samples=2*len(np.concatenate(held)))
            gains = [models['separate']['predictions'][r]['NLL']-models['common']['predictions'][r]['NLL'] for r in [0, 1]]
            alias_gaps = {mode:models[mode]['fit']['quadratic']-models['common']['fit']['quadratic']
                for mode in ['common_alias_minus750', 'common_alias_plus750']}
            folds.append(dict(parity=parity, models=models, common_vs_separate_held_gain=gains,
                native_carrier_hz=native, raw_native_clock_difference_hz=raw_delta,
                shared_clock_initialization_hz=clock, wrong_global750Hz_alias_training_Q_gap=alias_gaps))
        checks = dict(original_native_RF_interiors=all(not n['boundary'] for f in row['folds'] for n in f['native_training_fits']),
            all_joint_common_clock_interiors=all(not f['models']['common']['fit']['boundary'] for f in folds),
            full_rank_joint_common_clock_covariance=all(f['models']['common']['fit']['covariance_full_rank'] for f in folds),
            common_beats_separate_on_all_RX_and_folds=all(min(f['common_vs_separate_held_gain']) > 0 for f in folds),
            native_global_clock_branch_beats_both750Hz_alternatives=all(min(f['wrong_global750Hz_alias_training_Q_gap'].values()) > 0 for f in folds))
        result = dict(index=index, case=entry['case'], entry=entry, cohort=entry['cohort'], status='complete',
            frames=len(segments), folds=folds, checks=checks,
            conditional_raw_IQ_common_clock_candidate=all(checks.values()),
            raw_native_acquisition_and_training_noise_variance_conditioned=True,
            no_absolute_CFO_covariance_or_position_change_qualified=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(index=index, case=entry['case'], cohort=entry['cohort'], entry=entry,
            status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-started
    write(path, result)
    print(index, entry['case'], entry['window_key'], result['status'],
        result.get('conditional_raw_IQ_common_clock_candidate'), result.get('error'), flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    BULK.mkdir(exist_ok=True)
    source = read(SOURCE)
    protocol = dict(source_sha256=sha(SOURCE), workers=6, per_window_seconds=240,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name, 'ds23_joint_receiver_iq.py',
            'ds23_joint_component_rf.py', 'ds23_training_channel_rf.py']},
        selected_windows=[dict(index=r['index'], case=r['case'], window=r['entry']['window_key']) for r in source['rows']],
        models='joint15parameter common RX clock versus16parameter two RX contrasts; native clock plus/minus750Hz controls',
        transmitter_gains='independent complex pair per native frame, shared acrossRX; independent perRX frame DC',
        fitted_parameters='source carriers, physical RX clock(s),4fractional epochs,4code rates,2complex RX channel ratios',
        same_training_native_frames_and30joint_steps_each_model=True,
        full_complex_source_gain_uncertainty_in_target_IQ_prediction=True,
        held_target_signal_coefficients_never_fitted=True,
        no_GPS_TLE_satellite_ID_or_position_used=True,
        Gaussian_frequency_covariance_is_conditional_proxy_not_calibrated=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen direct joint-IQ experiment changed')
    if not target.exists():
        write(target, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one, r) for r in source['rows']])]
    write(OUT/'evaluation.json', dict(rows=sorted(rows, key=lambda r:r['index']), all_terminal=True,
        protocol_sha256=sha(target), conditional_candidates=[r['index'] for r in rows if r.get('conditional_raw_IQ_common_clock_candidate')],
        no_new_RF_collection_or_position_algorithm_promoted=True))


if __name__ == '__main__':
    main()
