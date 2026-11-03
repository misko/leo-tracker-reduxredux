"""Two simultaneous signals as a receiver-clock consistency experiment."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib
import signal
import time

import numpy as np

from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from ds23_joint_gain_controls import frame_coefficients
from ds23_training_gain_rf import restricted_workspace
from ds23_training_channel_rf import projected_frame_gains
from inventory_ds23_paired_component_cycles import PERIOD, wrap
from probe_ds23_cross_RX_gain_prediction import evaluate
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_paired_component_cycles_v2'
BULK = Path('/srv/bulk/leo/research/ds23-paired-component-cycles-v2-20261021')
INVENTORY = ROOT/'reports/2026_10_21_ds23_paired_component_cycles/inventory.json'


def one(job):
    index, entry = job['index'], job['entry']
    path = BULK/f'probe{index:03d}.json'
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('240second joint two-component RF cap')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(240)
    try:
        with np.load(entry['panel'], allow_pickle=False) as panel:
            values = panel[entry['window_key']]
        if 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() != entry['raw_window_sha256']:
            raise ValueError('saved native IQ window changed')
        samples = [values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]]
        fs, edge = entry['sample_rate_hz'], entry['edge']
        epochs = np.array([c['epochs'] for c in entry['components']])
        for k in range(2):
            epochs[k, 1] += np.rint((epochs[k, 0]-epochs[k, 1])/(fs/750))*(fs/750)
        initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
            offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
        geometry = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
            for rx, y in enumerate(samples) for k in [0, 1]]
        segments = common_segments(geometry)
        if len(segments) < 10:
            raise ValueError('ten distinct common frames for all four component geometries required')
        t = np.array([ix.mean()/fs for ix in segments])
        frames = np.arange(len(t))
        random_phases = np.random.default_rng(2026102170+index).uniform(-np.pi, np.pi, (199, len(t)))
        modes = {}
        for per_tone in [False, True]:
            mode = 'per_tone' if per_tone else 'flat'
            folds = []
            null_scores = [np.empty((199, 4)) for _ in range(2)]
            for parity in [0, 1]:
                training = frames % 2 == parity
                support = [ix for k, ix in enumerate(segments) if training[k]]
                fits, gains = [], []
                for rx, y in enumerate(samples):
                    if per_tone:
                        seed = next(f for f in modes['flat']['folds'] if f['parity'] == parity)['native_training_fits'][rx]['parameters']
                        seeds = [dict(CFO_hz=p[0], offset_samples=p[1], modulation_ppm=p[2])
                            for p in np.array(seed).reshape(2, 3)]
                    else:
                        seeds = [restricted_workspace(y, fs, edge, epochs[k, rx], support).fast_joint_fit(
                            initial[rx][k]['CFO_hz']) for k in [0, 1]]
                    ws = JointComponentWorkspace(y, fs, edge, epochs[:, rx], support, per_tone=per_tone)
                    fitted = ws.joint_fit(seeds)
                    fits.append(fitted)
                    columns = ws.columns(fitted['parameters'])
                    coefficient, covariance = frame_coefficients(y, columns, segments)
                    receiver_gains = []
                    for k in [0, 1]:
                        selection = slice(8*k, 8*k+8) if per_tone else slice(k, k+1)
                        receiver_gains.append(projected_frame_gains(coefficient[:, selection],
                            covariance[:, selection, selection], training))
                    gains.append(receiver_gains)
                components = []
                for k in [0, 1]:
                    a, b = gains[0][k]['gain'], gains[1][k]['gain']
                    va, vb = gains[0][k]['variance'], gains[1][k]['variance']
                    records = []
                    for direction in [0, 1]:
                        args = (a, b, va, vb) if direction == 0 else (b, a, vb, va)
                        actual = evaluate(t, *args, training)
                        records.append(dict(direction=direction, actual=actual))
                        for j, phases in enumerate(random_phases):
                            changed = abs(b)*np.exp(1j*phases)
                            args = (a, changed, va, vb) if direction == 0 else (changed, a, vb, va)
                            null_scores[k][j, 2*parity+direction] = evaluate(t, *args, training)['held_gain']
                    raw_delta = float(fits[1]['parameters'][3*k]-fits[0]['parameters'][3*k])
                    corrections = [r['actual']['shared']['frequency_correction_mod750_hz']*(1 if r['direction'] == 0 else -1)
                        for r in records]
                    components.append(dict(component=k, records=records,
                        native_delta_hz=raw_delta,
                        oriented_gain_frequency_corrections_hz=corrections,
                        principal_corrected_RX_delta_hz=float(wrap(raw_delta+np.mean(corrections), PERIOD)),
                        source_gain_real=a.real, source_gain_imag=a.imag, source_variance=va,
                        target_gain_real=b.real, target_gain_imag=b.imag, target_variance=vb,
                        training_channel_rank_one_fractions=[gains[rx][k]['training_rank_one_fraction'] for rx in [0, 1]]))
                values_delta = [c['principal_corrected_RX_delta_hz'] for c in components]
                folds.append(dict(parity=parity, native_training_fits=fits, components=components,
                    principal_component_disagreement_hz=float(wrap(values_delta[1]-values_delta[0], PERIOD))))
            summaries = []
            for k in [0, 1]:
                records = [r for f in folds for r in f['components'][k]['records']]
                score = min(r['actual']['held_gain'] for r in records)
                null = null_scores[k].min(axis=1)
                p = (1+int(np.sum(null >= score)))/200
                passed = bool(score > 0 and p <= .01
                    and all(r['actual'][m]['converged'] for r in records for m in ['shared', 'independent'])
                    and all(not r['actual']['shared']['boundary'] for r in records))
                summaries.append(dict(component=k, minimum_held_gain=float(score), phase_control_rank=p,
                    phase_control_scores=null, conditional_candidate=passed))
            modes[mode] = dict(folds=folds, components=summaries,
                both_components_conditional_candidates=all(c['conditional_candidate'] for c in summaries),
                all_native_joint_fits_interior=all(not fit['boundary'] for f in folds for fit in f['native_training_fits']))
        native = [c['peaks'][1]['fractional_tracking_cfo_hz']-c['peaks'][0]['fractional_tracking_cfo_hz']
            for c in entry['components']]
        result = dict(index=index, case=entry['case'], entry=entry, status='complete',
            aligned_epochs=epochs, frames=len(t), time_s=t, modes=modes,
            original_native_component_disagreement_hz=float(wrap(native[1]-native[0], PERIOD)),
            joint_tone_coefficient_covariance_retained_inside_each_extraction=True,
            independent_gain_frequency_fits_NOT_jointly_covariance_calibrated=True,
            no750Hz_branch_cross_component_covariance_or_position_measurement_qualified=True,
            original_native_GLRT_acquisition_seeds_and_support_remain_conditioned=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(index=index, case=entry['case'], status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-started
    write(path, result)
    print(index, result['case'], result['status'], result.get('error'), flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    BULK.mkdir(exist_ok=True)
    inventory = INVENTORY
    jobs = [dict(index=k, entry=e) for k, e in enumerate(read(inventory)['selected'])]
    protocol = dict(jobs=jobs, workers=2, per_probe_seconds=240,
        inventory_sha256=sha(inventory),
        source_sha256={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,
            'ds23_joint_component_rf.py', 'ds23_training_channel_rf.py', 'ds23_cross_RX_gain_prediction.py']},
        models='joint simultaneous two-component flat and per-tone known-pilot profiles; separate frame gains/DC',
        training='same four-geometry native frame intersections, trim16samples, parity folds, fit RF only on training IQ',
        prediction='conditional shared source-target frame gain vs independent; both directions;199phase controls',
        comparison='RX2minusRX1 carrier contrast should agree between distinct simultaneously observed components',
        ambiguity_and_covariance_NOT_validated=True, no_new_RF_GPS_TLE_satellite_labels_or_position_used=True)
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('frozen joint-component protocol changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one, j) for j in jobs])]
    write(OUT/'evaluation.json', dict(rows=sorted(rows, key=lambda r:r['index']), all_terminal=True,
        protocol_sha256=sha(path), no_RF_measurement_or_position_improvement_adopted=True))


if __name__ == '__main__':
    main()
