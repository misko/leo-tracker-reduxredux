"""Independently replay native IQ fits, held scores, and gain predictions."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib

import numpy as np

from ds23_joint_gain_controls import frame_coefficients
from ds23_training_channel_rf import TrainingChannelWorkspace, projected_frame_gains
from probe_ds23_cross_RX_gain_prediction import evaluate
from probe_ds23_training_channel_rf import OUT, FLAT
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(row):
    entry = row['entry']
    old = next(r for r in read(FLAT)['rows'] if r['index'] == row['index'])
    with np.load(entry['panel'], allow_pickle=False) as panel:
        values = panel[entry['window_key']]
    assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
    samples = [values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]]
    fs, edge = entry['sample_rate_hz'], entry['edge']
    t = np.asarray(row['time_s'])
    # The common native intersections are contiguous, so their saved mean and
    # the original frozen support can be reconstructed independently.
    from ds23_conditional_pilot_components import component_segments
    from ds23_differential_frame_phase import unique_frame_intersections
    from ds23_fractional_differential_phase import fractional_geometry
    initial = [dict(CFO_hz=p['fractional_tracking_cfo_hz'], offset_samples=0.,
        modulation_ppm=0.) for p in entry['peaks']]
    geometries = [fractional_geometry(y, fs, edge, row['aligned_epochs'][rx], initial[rx])
        for rx, y in enumerate(samples)]
    segments = [ix[16:-16] for ix in unique_frame_intersections(*geometries,
        component_segments(*geometries)) if len(ix) >= 112]
    np.testing.assert_array_equal(t, [ix.mean()/fs for ix in segments])
    first_phases = np.random.default_rng(2026102160+row['index']).uniform(-np.pi, np.pi, (199, len(t)))[0]
    actuals, first_null = [], []
    maximum_parameter_difference = maximum_gain_difference = maximum_score_difference = 0.
    for fold in row['folds']:
        parity = fold['parity']
        train = np.arange(len(t)) % 2 == parity
        support = [ix for k, ix in enumerate(segments) if train[k]]
        old_fold = next(f for f in old['folds'] if f['parity'] == parity)
        gains = []
        for rx, y in enumerate(samples):
            ws = TrainingChannelWorkspace(y, fs, edge, row['aligned_epochs'][rx], support)
            fitted = ws.fit_from_training_seed(old_fold['native_training_fits'][rx], initial[rx]['CFO_hz'])
            keys = ['CFO_hz', 'offset_samples', 'modulation_ppm']
            parameters = np.array([fitted[k] for k in keys])
            saved = np.array([fold['native_training_fits'][rx][k] for k in keys])
            maximum_parameter_difference = max(maximum_parameter_difference, float(max(abs(parameters-saved))))
            np.testing.assert_allclose(parameters, saved, rtol=1e-10, atol=1e-8)
            for control in [False, True]:
                columns = ws.columns(parameters, control=control)
                coefficients, covariance = frame_coefficients(y, columns, segments)
                projected = projected_frame_gains(coefficients, covariance, train)
                _, _, vh = np.linalg.svd(coefficients[train], full_matrices=False)
                direction = vh[0]
                raw = residual = 0.
                for k, ix in enumerate(segments):
                    if train[k]:
                        continue
                    design = np.column_stack((columns[ix]@direction, np.ones(len(ix))))
                    c = np.linalg.lstsq(design, y[ix], rcond=1e-8)[0]
                    error = y[ix]-design@c
                    residual += float(np.vdot(error, error).real)
                    centered = y[ix]-y[ix].mean()
                    raw += float(np.vdot(centered, centered).real)
                score = 1-residual/raw
                key = 'per_tone_control_score' if control else 'per_tone_score'
                saved_score = fold['held_RF_scores'][rx][key]
                maximum_score_difference = max(maximum_score_difference, abs(score-saved_score))
                np.testing.assert_allclose(score, saved_score, atol=2e-10, rtol=1e-9)
                if not control:
                    gains.append(projected)
        a, b = [g['gain'] for g in gains]
        va, vb = [g['variance'] for g in gains]
        for prefix, current in [('source', a), ('target', b)]:
            saved = np.array(fold[prefix+'_gain_real'])+1j*np.array(fold[prefix+'_gain_imag'])
            maximum_gain_difference = max(maximum_gain_difference, float(max(abs(current-saved))))
            np.testing.assert_allclose(current, saved, atol=1e-8, rtol=1e-9)
        for record in fold['records']:
            direction = record['direction']
            args = (a, b, va, vb) if direction == 0 else (b, a, vb, va)
            actual = evaluate(t, *args, train)
            np.testing.assert_allclose(actual['held_gain'], record['actual']['held_gain'], atol=1e-7, rtol=1e-8)
            actuals.append(actual['held_gain'])
            changed = abs(b)*np.exp(1j*first_phases)
            args = (a, changed, va, vb) if direction == 0 else (changed, a, vb, va)
            first_null.append(evaluate(t, *args, train)['held_gain'])
    null = np.array(row['phase_control_scores'])
    np.testing.assert_allclose(min(first_null), null[0], atol=1e-7, rtol=1e-8)
    score = min(actuals)
    assert abs(score-row['actual_score']) < 1e-7
    assert (1+int(np.sum(null >= score)))/200 == row['phase_control_rank']
    return dict(case=row['case'], native_RF_refits=4, actual_gain_model_refits=4,
        first_randomized_control_refits=4, maximum_parameter_difference=maximum_parameter_difference,
        maximum_gain_difference=maximum_gain_difference, maximum_held_score_difference=maximum_score_difference,
        all_recorded199_control_ranks_recomputed_but_only_first_control_reoptimized=True)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source = read(OUT/'evaluation.json')
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [f.result() for f in as_completed([pool.submit(replay, r) for r in source['rows'] if r['status'] == 'complete'])]
    complete = [r for r in source['rows'] if r['status'] == 'complete']
    flat = np.array([min(h['flat_margin'] for f in r['folds'] for h in f['held_RF_scores']) for r in complete])
    tone = np.array([min(h['per_tone_margin'] for f in r['folds'] for h in f['held_RF_scores']) for r in complete])
    improvements = np.array([min(h['per_tone_score']-h['flat_score'] for f in r['folds'] for h in f['held_RF_scores']) for r in complete])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), layout='constrained')
    ax = axes[0]
    ax.scatter(flat, tone)
    ax.plot([0, .15], [0, .15], color='gray', ls='--')
    ax.axvline(.05, color='gray', lw=.7)
    ax.axhline(.05, color='gray', lw=.7)
    ax.set(xlabel='Flat channel: minimum held RF margin', ylabel='Per-tone channel: minimum held RF margin',
        title='Matched IQ; channel shape trained on other frames')
    ax = axes[1]
    ax.scatter([r['flat_actual_score'] for r in complete], [r['actual_score'] for r in complete])
    ax.plot([-350, 100], [-350, 100], color='gray', ls='--')
    ax.set(xlabel='Flat: minimum held paired-gain NLL gain',
        ylabel='Per-tone: minimum held paired-gain NLL gain', title='Both RX directions and frame folds')
    ax = axes[2]
    ax.bar(np.arange(len(complete)), improvements*100)
    ax.axhline(0, color='black', lw=.7)
    ax.set_xticks(np.arange(len(complete)), [r['case'].split('-')[1] for r in complete], rotation=90)
    ax.set(ylabel='Worst-fold held RF score change\n(percentage points)',
        xlabel='Scan', title=f'{sum(improvements>0)}/{len(complete)} improve in every RX/fold')
    fig.suptitle('Training-only per-tone RF prototype: conditional evidence; no position improvement established', fontsize=12)
    fig.savefig(OUT/'held_RF_comparison.png', dpi=160)
    plt.close(fig)
    write(OUT/'independent_replay_audit.json', dict(rows=rows, completed=len(rows),
        flat_conditional_candidates=sum(r['flat_conditional_candidate'] for r in complete),
        per_tone_conditional_candidates=len(source['conditional_candidates']),
        per_tone_candidates_with_held_RF_support=source['supported_candidates'],
        all_RX_fold_held_RF_score_improvements=int(sum(improvements>0)),
        minimum_held_RF_improvement_median=float(np.median(improvements)),
        actual_native_RF_refits=sum(r['native_RF_refits'] for r in rows),
        actual_gain_model_refits=sum(r['actual_gain_model_refits'] for r in rows),
        control_gain_model_refits=sum(r['first_randomized_control_refits'] for r in rows),
        raw_IQ_hashes_and_disjoint_RF_training_support_verified=True,
        source_sha256=sha(OUT/'evaluation.json'),
        no_absolute_CFO_precision_ambiguity_covariance_or_position_gain_established=True))
    print(dict(complete=len(rows), all_held_RF_scores_improve=int(sum(improvements>0)),
        candidates=source['supported_candidates']), flush=True)


if __name__ == '__main__':
    main()
