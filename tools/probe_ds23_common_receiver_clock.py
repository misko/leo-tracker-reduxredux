"""Bounded, native-RF-only shared-clock versus separate-clock prediction test."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib
import signal
import time
import numpy as np

from ds23_common_receiver_clock import fit, predict, project_components, align_frame_phase_branch
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from ds23_joint_gain_controls import frame_coefficients
from ds23_training_gain_rf import restricted_workspace
from inventory_ds23_paired_component_cycles import PERIOD, wrap
from inventory_ds23_common_clock import OUT as INVENTORY_OUT
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_common_receiver_clock_v2'
BULK = Path('/srv/bulk/leo/research/ds23-common-receiver-clock-v2-20261021')
PREVIOUS = ROOT/'reports/2026_10_21_ds23_common_receiver_clock/evaluation.json'
VARIANTS = ('exact_sample_times', 'periodic_frame_approximation')


def one(job):
    index, entry = job['index'], job['entry']
    path = BULK/f'probe{index:03d}.json'
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('180second bounded common-clock RF test')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    try:
        with np.load(entry['panel'], allow_pickle=False) as panel:
            values = panel[entry['window_key']]
        assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
        samples = [values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]]
        fs, edge = entry['sample_rate_hz'], entry['edge']
        epochs = np.array([c['epochs'] for c in entry['components']])
        for k in [0, 1]:
            epochs[k, 1] += np.rint((epochs[k, 0]-epochs[k, 1])/(fs/750))*(fs/750)
        initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
            offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
        geometries = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
            for rx, y in enumerate(samples) for k in [0, 1]]
        segments = common_segments(geometries)
        if len(segments) < 10:
            raise ValueError('ten supported distinct four-geometry frames required')
        t = np.array([ix.mean()/fs for ix in segments])
        old = next((r for r in read(PREVIOUS)['rows'] if r['case'] == entry['case']
            and r['entry']['window_key'] == entry['window_key']), None)
        if old is None or not np.array_equal(t, np.asarray(old['time_s'])):
            raise ValueError('exact native-RF support must match the preceding experiment')
        folds = []
        for parity in [0, 1]:
            training = np.arange(len(t)) % 2 == parity
            support = [ix for k, ix in enumerate(segments) if training[k]]
            receivers, native_fits = [], []
            for rx, y in enumerate(samples):
                if old is not None:
                    previous = next(f for f in old['folds'] if f['parity'] == parity)
                    start = np.array(previous['native_training_fits'][rx]['history'][0]['parameters']).reshape(2, 3)
                    seeds = [dict(CFO_hz=p[0], offset_samples=p[1], modulation_ppm=p[2]) for p in start]
                else:
                    seeds = [restricted_workspace(y, fs, edge, epochs[k, rx], support).fast_joint_fit(
                        initial[rx][k]['CFO_hz']) for k in [0, 1]]
                ws = JointComponentWorkspace(y, fs, edge, epochs[:, rx], support)
                native = ws.joint_fit(seeds)
                native_fits.append(native)
                coefficients, covariance = frame_coefficients(y, ws.columns(native['parameters']), segments)
                receivers.append(project_components(coefficients, covariance, training))
            raw = np.array(native_fits[1]['parameters'])[::3]-np.array(native_fits[0]['parameters'])[::3]
            records = []
            for variant in VARIANTS:
                aligned = align_frame_phase_branch(raw, t, receivers[1]['gain'], receivers[1]['covariance'],
                    exact=variant == 'exact_sample_times')
                changed = [receivers[0], dict(gain=aligned['gain'], covariance=aligned['covariance'])]
                for direction in [0, 1]:
                    source, target = changed if direction == 0 else changed[::-1]
                    native_delta = aligned['native_delta_hz']*(1 if direction == 0 else -1)
                    data = (source['gain'], target['gain'], source['covariance'], target['covariance'])
                    models = {}
                    for mode in ['common', 'separate', 'independent']:
                        fitted = fit(t[training], *(v[training] for v in data), native_delta, mode=mode)
                        held = predict(fitted, t[~training], *(v[~training] for v in data))
                        models[mode] = dict(fit=fitted, held_NLL=held)
                    records.append(dict(direction=direction, variant=variant, models=models,
                        removed_frame_phase_cycles=aligned['removed_frame_phase_cycles'],
                        common_vs_separate_held_gain=models['separate']['held_NLL']-models['common']['held_NLL'],
                        common_vs_independent_held_gain=models['independent']['held_NLL']-models['common']['held_NLL']))
            folds.append(dict(parity=parity, native_training_fits=native_fits, raw_native_delta_hz=raw,
                training_frame_indices=np.flatnonzero(training), records=records,
                first_gains_real=receivers[0]['gain'].real, first_gains_imag=receivers[0]['gain'].imag,
                second_gains_real=receivers[1]['gain'].real, second_gains_imag=receivers[1]['gain'].imag,
                first_covariance_real=receivers[0]['covariance'].real, first_covariance_imag=receivers[0]['covariance'].imag,
                second_covariance_real=receivers[1]['covariance'].real, second_covariance_imag=receivers[1]['covariance'].imag,
                joint_cross_component_covariance_in_prediction=True))
        variant_checks = {}
        for variant in VARIANTS:
            records = [r for f in folds for r in f['records'] if r['variant'] == variant]
            checks = dict(all_native_RF_interiors=all(not n['boundary'] for f in folds for n in f['native_training_fits']),
                all_clock_optimizers_converged=all(m['fit']['converged'] for r in records for m in r['models'].values()),
                all_common_clock_interiors=all(not r['models']['common']['fit']['boundary'] for r in records),
                all_common_clock_branch_interiors=all(not r['models']['common']['fit']['branch_correction_boundary'] for r in records),
                common_beats_separate_on_every_fold_direction=all(r['common_vs_separate_held_gain'] > 0 for r in records),
                common_beats_independent_on_every_fold_direction=all(r['common_vs_independent_held_gain'] > 0 for r in records))
            variant_checks[variant] = checks
        checks = variant_checks['exact_sample_times']
        records = [r for f in folds for r in f['records'] if r['variant'] == 'exact_sample_times']
        result = dict(index=index, entry=entry, case=entry['case'], cohort=entry['cohort'], status='complete',
            frames=len(t), time_s=t, aligned_epochs=epochs, folds=folds, checks=checks, variant_checks=variant_checks,
            conditional_common_clock_candidate=all(checks.values()),
            minimum_common_vs_separate_gain=min(r['common_vs_separate_held_gain'] for r in records),
            minimum_common_vs_independent_gain=min(r['common_vs_independent_held_gain'] for r in records),
            native_acquisition_and_held_extraction_noise_conditioned=True,
            no_clock_ambiguity_total_covariance_or_position_measurement_adopted=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(index=index, case=entry['case'], entry=entry, cohort=entry['cohort'], status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-started
    write(path, result)
    print(index, entry['case'], entry['window_key'], result['status'],
        result.get('minimum_common_vs_separate_gain'), result.get('conditional_common_clock_candidate'), result.get('error'), flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    BULK.mkdir(exist_ok=True)
    inventory = INVENTORY_OUT/'inventory.json'
    jobs = [dict(index=k, entry=e) for k, e in enumerate(read(inventory)['selected'])]
    protocol = dict(jobs=jobs, inventory_sha256=sha(inventory), workers=9, per_window_seconds=180,
        source_sha256={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,
            'ds23_common_receiver_clock.py', 'ds23_joint_component_rf.py', 'ds23_training_channel_rf.py']},
        models='common physical RX contrast, separate contrasts, independent target gains',
        same_native_fits_frame_masks_full_complex_covariance_and100Hz_per_component_frequency_prior=True,
        primary='flat joint RF channels; both parity folds and receiver directions',
        qualification='allfold/direction common held NLL below separate and independent, with convergence and RF/clock bounds',
        common_clock_confirmation_has7other_windows_not_new_scans=True,
        raw_carrier_differences_preserved_before_frame_phase=True,
        phase_branch_period_hz=750, pilot_CFO_alias_period_hz=PERIOD,
        exact_target_gain_and_covariance_rotation_primary_periodic_frame_approximation_control=True,
        previous_native_RF_seed_source_sha256=sha(PREVIOUS),
        no_GPS_TLE_satellite_label_or_position_used=True,
        conditional_prediction_not_absolute_CFO_precision_or_position_gain=True)
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('frozen common-clock protocol changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=9) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one, job) for job in jobs])]
    write(OUT/'evaluation.json', dict(rows=sorted(rows, key=lambda r:r['index']), all_terminal=True,
        protocol_sha256=sha(path), conditional_candidates=[r['index'] for r in rows if r.get('conditional_common_clock_candidate')],
        no_position_algorithm_promoted=True))


if __name__ == '__main__':
    main()
