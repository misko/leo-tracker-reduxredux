"""Bounded saved-IQ replication of training-only frequency-selective RF fits."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib
import signal
import time

import numpy as np

from ds23_conditional_pilot_components import component_segments
from ds23_differential_frame_phase import unique_frame_intersections
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_gain_controls import frame_coefficients
from ds23_training_channel_rf import TrainingChannelWorkspace, projected_frame_gains
from ds23_training_gain_rf import restricted_workspace
from probe_ds23_cross_RX_gain_prediction import evaluate
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT / 'reports/2026_10_21_ds23_training_channel_rf_v2'
BULK = Path('/srv/bulk/leo/research/ds23-training-channel-rf-v2-20261021')
FLAT = ROOT / 'reports/2026_10_21_ds23_paired_gain_training_only/evaluation.json'


def shape_score(samples, columns, segments, training):
    """Train channel shape on training frames; profile only gain/DC on held IQ."""
    coefficient, covariance = frame_coefficients(samples, columns, segments)
    projected = projected_frame_gains(coefficient, covariance, training)
    _, _, vh = np.linalg.svd(coefficient[training], full_matrices=False)
    signal = columns @ vh[0]
    explained = raw = 0.
    for k, ix in enumerate(segments):
        if training[k]:
            continue
        s = signal[ix] - signal[ix].mean()
        y = samples[ix] - samples[ix].mean()
        explained += float(abs(np.vdot(s, y))**2 / np.vdot(s, s).real)
        raw += float(np.vdot(y, y).real)
    return projected, float(explained / max(raw, 1e-20))


def one(job):
    old = job['row']
    index, entry = old['index'], old['entry']
    path = BULK / f'probe{index:03d}.json'
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('180second per-probe saved-IQ frequency-selective fit cap')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    try:
        with np.load(entry['panel'], allow_pickle=False) as panel:
            values = panel[entry['window_key']]
        if 'sha256:' + hashlib.sha256(values.tobytes()).hexdigest() != entry['raw_window_sha256']:
            raise ValueError('saved native IQ window changed')
        samples = [values[:, rx, 0].astype(float) + 1j*values[:, rx, 1] for rx in [0, 1]]
        fs, edge = entry['sample_rate_hz'], entry['edge']
        epochs = np.asarray(old['aligned_epochs'])
        initial = [dict(CFO_hz=p['fractional_tracking_cfo_hz'], offset_samples=0.,
            modulation_ppm=0.) for p in entry['peaks']]
        geometry = [fractional_geometry(y, fs, edge, epochs[rx], initial[rx])
            for rx, y in enumerate(samples)]
        common = unique_frame_intersections(*geometry, component_segments(*geometry))
        segments = [ix[16:-16] for ix in common if len(ix) >= 112]
        t = np.array([ix.mean()/fs for ix in segments])
        if not np.array_equal(t, np.asarray(old['time_s'])):
            raise ValueError('frozen frame support changed relative to the flat control')
        frames = np.arange(len(t))
        random_phases = np.random.default_rng(2026102160+index).uniform(-np.pi, np.pi, (199, len(t)))
        null_scores = np.empty((199, 4))
        folds = []
        for parity in [0, 1]:
            training = frames % 2 == parity
            support = [ix for k, ix in enumerate(segments) if training[k]]
            old_fold = next(f for f in old['folds'] if f['parity'] == parity)
            fits, gains, held = [], [], []
            for rx, y in enumerate(samples):
                seed = old_fold['native_training_fits'][rx]
                ws = TrainingChannelWorkspace(y, fs, edge, epochs[rx], support)
                fit = ws.fit_from_training_seed(seed, initial[rx]['CFO_hz'])
                fits.append(fit)
                parameters = [fit[k] for k in ['CFO_hz', 'offset_samples', 'modulation_ppm']]
                gain, score = shape_score(y, ws.columns(parameters), segments, training)
                _, control = shape_score(y, ws.columns(parameters, control=True), segments, training)
                gains.append(gain)
                flat = restricted_workspace(y, fs, edge, epochs[rx],
                    [ix for k, ix in enumerate(segments) if not training[k]])
                flat_score = float(flat.evaluate([seed['CFO_hz']], seed['offset_samples'],
                    seed['modulation_ppm'])[0])
                flat_control = float(flat.evaluate([seed['CFO_hz']], seed['offset_samples'],
                    seed['modulation_ppm'], control=True)[0])
                held.append(dict(per_tone_score=score, per_tone_control_score=control,
                    per_tone_margin=score-control, flat_score=flat_score,
                    flat_control_score=flat_control, flat_margin=flat_score-flat_control,
                    channel_shape_uses_training_frames_only=True,
                    held_frame_complex_gain_and_DC_are_profiled=True))
            a, b = [g['gain'] for g in gains]
            va, vb = [g['variance'] for g in gains]
            records = []
            for direction in [0, 1]:
                args = (a, b, va, vb) if direction == 0 else (b, a, vb, va)
                actual = evaluate(t, *args, training)
                records.append(dict(direction=direction, actual=actual))
                for k, phases in enumerate(random_phases):
                    changed = abs(b)*np.exp(1j*phases)
                    args = (a, changed, va, vb) if direction == 0 else (changed, a, vb, va)
                    null_scores[k, 2*parity+direction] = evaluate(t, *args, training)['held_gain']
            folds.append(dict(parity=parity, native_training_fits=fits,
                training_frame_indices=frames[training], held_RF_scores=held, records=records,
                training_rank_one_fractions=[g['training_rank_one_fraction'] for g in gains],
                source_gain_real=a.real, source_gain_imag=a.imag, source_variance=va,
                target_gain_real=b.real, target_gain_imag=b.imag, target_variance=vb))
        score = min(r['actual']['held_gain'] for f in folds for r in f['records'])
        null = null_scores.min(axis=1)
        rank = (1+int(np.sum(null >= score)))/200
        converged = all(r['actual'][m]['converged'] for f in folds for r in f['records']
            for m in ['shared', 'independent'])
        interior = all(not r['actual']['shared']['boundary'] for f in folds for r in f['records'])
        native = all(not any(fit[k] for k in ['frequency_search_boundary',
            'epoch_search_boundary', 'code_rate_search_boundary'])
            for f in folds for fit in f['native_training_fits'])
        held_pass = all(h['per_tone_margin'] > .05 for f in folds for h in f['held_RF_scores'])
        candidate = bool(score > 0 and rank <= .01 and converged and interior)
        result = dict(index=index, case=entry['case'], entry=entry, status='complete',
            frames=len(t), time_s=t, aligned_epochs=epochs, folds=folds,
            actual_score=float(score), phase_control_scores=null, phase_control_rank=rank,
            conditional_candidate=candidate, native_RF_interior=native,
            all_held_RF_margins_above_point05=held_pass,
            conditional_candidate_with_held_RF_support=bool(candidate and native and held_pass),
            flat_actual_score=old['actual_score'], flat_conditional_candidate=old['conditional_candidate'],
            seeds_and_support_conditioned_on_original_native_acquisition=True,
            paired_gain_uses_held_source_and_conditional_extraction_variances=True,
            no750Hz_branch_covariance_or_position_measurement_qualified=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(index=index, case=entry['case'], status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-started
    write(path, result)
    print(index, result['case'], result['status'], result.get('actual_score'),
        result.get('conditional_candidate_with_held_RF_support'), result.get('error'), flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    BULK.mkdir(exist_ok=True)
    source = read(FLAT)
    jobs = [dict(row=r) for r in sorted(source['rows'], key=lambda r:r['index'])]
    protocol = dict(jobs=[dict(index=j['row']['index'], case=j['row']['case'],
        raw_window_sha256=j['row']['entry']['raw_window_sha256']) for j in jobs],
        flat_source_sha256=sha(FLAT), workers=10, per_probe_seconds=180,
        source_sha256={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,
            'ds23_training_channel_rf.py', 'ds23_cross_RX_gain_prediction.py']},
        channel='eight complex gains per frame; separate DC; fractional frame placement',
        RF_training='same disjoint physical parity frames as matched flat control; train-only flat initialization',
        held_RF_validation='channel direction learned on training frames; held gain/DC profiled; rolled-pilot control',
        conditional_gain_validation='both parity folds and RX directions; same199phase controls and seed as flat',
        conditional_support_thresholds=dict(score=0., phase_rank=.01, minimum_each_held_RF_margin=.05,
            native_RF_bounds_must_be_interior=True),
        no_new_RF_GPS_TLE_satellite_label_or_position_used=True,
        no_CFO_branch_covariance_or_position_accuracy_claimed=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('prospective protocol changed')
    if not target.exists():
        write(target, protocol)
    with ProcessPoolExecutor(max_workers=10) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one, j) for j in jobs])]
    rows.sort(key=lambda r:r['index'])
    write(OUT/'evaluation.json', dict(rows=rows, all_terminal=True,
        conditional_candidates=[r['case'] for r in rows if r.get('conditional_candidate')],
        supported_candidates=[r['case'] for r in rows if r.get('conditional_candidate_with_held_RF_support')],
        failures=[dict(case=r['case'], error=r['error']) for r in rows if r['status'] != 'complete'],
        protocol_sha256=sha(target), no_localization_estimate_changed=True))


if __name__ == '__main__':
    main()
