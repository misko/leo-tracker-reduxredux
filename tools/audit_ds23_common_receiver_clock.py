"""Independent RF/clock replay, component marginals, and ambiguity diagnostics."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from ds23_common_receiver_clock import fit, predict, project_components, align_frame_phase_branch, frequency_corrections
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from ds23_joint_gain_controls import frame_coefficients
from inventory_ds23_paired_component_cycles import PERIOD, wrap
from probe_ds23_common_receiver_clock import OUT, PREVIOUS, VARIANTS
from run_algo01_ds23_sample import ROOT, read, write, sha


def component_NLL(model, times, first, second, covariance_first, covariance_second):
    """Univariate marginals of the same multivariate conditional density."""
    p, native = np.asarray(model['parameters']), np.asarray(model['native_delta_hz'])
    sa, sb = np.asarray(model['first_scale']), np.asarray(model['second_scale'])
    a, b = np.asarray(first)/sa, np.asarray(second)/sb
    va = np.diagonal(covariance_first, axis1=1, axis2=2).real/(sa*sa)
    vb = np.diagonal(covariance_second, axis1=1, axis2=2).real/(sb*sb)
    k = len(native)
    ratio = p[:2*k:2]+1j*p[1:2*k:2]
    correction = frequency_corrections(p, native, model['mode'])
    rotation = ratio*np.exp(2j*np.pi*(np.asarray(times)-model['time_center_s'])[:, None]*correction[None])
    shared = model['mode'] != 'independent'
    variance = vb+np.exp(p[-k:])[None]
    if shared:
        variance += abs(rotation)**2*va
    residual = b-rotation*(a if shared else np.ones_like(a))
    return np.sum(np.log(np.pi*variance)+abs(residual)**2/variance, axis=0)+2*len(times)*np.log(sb)


def saved_receivers(fold):
    result = []
    for prefix in ['first', 'second']:
        gain = np.array(fold[prefix+'_gains_real'])+1j*np.array(fold[prefix+'_gains_imag'])
        covariance = np.array(fold[prefix+'_covariance_real'])+1j*np.array(fold[prefix+'_covariance_imag'])
        result.append(dict(gain=gain, covariance=covariance))
    return result


def replay(row):
    entry = row['entry']
    with np.load(entry['panel'], allow_pickle=False) as panel:
        values = panel[entry['window_key']]
    import hashlib
    assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
    samples = [values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]]
    fs, edge, epochs = entry['sample_rate_hz'], entry['edge'], np.asarray(row['aligned_epochs'])
    initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
        offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
    geometry = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
        for rx, y in enumerate(samples) for k in [0, 1]]
    segments = common_segments(geometry)
    t = np.array([ix.mean()/fs for ix in segments])
    np.testing.assert_array_equal(t, row['time_s'])
    records, closure = [], []
    maximum_native_difference = maximum_gain_difference = maximum_covariance_difference = 0.
    for fold in row['folds']:
        train = np.arange(len(t)) % 2 == fold['parity']
        support = [ix for k, ix in enumerate(segments) if train[k]]
        receivers = []
        for rx, y in enumerate(samples):
            stored = fold['native_training_fits'][rx]
            start = np.array(stored['history'][0]['parameters']).reshape(2, 3)
            seeds = [dict(CFO_hz=p[0], offset_samples=p[1], modulation_ppm=p[2]) for p in start]
            ws = JointComponentWorkspace(y, fs, edge, epochs[:, rx], support)
            native = ws.joint_fit(seeds)
            maximum_native_difference = max(maximum_native_difference,
                float(max(abs(native['parameters']-stored['parameters']))))
            np.testing.assert_allclose(native['parameters'], stored['parameters'], atol=1e-8, rtol=1e-10)
            coefficients, covariance = frame_coefficients(y, ws.columns(native['parameters']), segments)
            receivers.append(project_components(coefficients, covariance, train))
        for fresh, stored in zip(receivers, saved_receivers(fold), strict=True):
            np.testing.assert_allclose(fresh['gain'], stored['gain'], atol=1e-8, rtol=1e-9)
            np.testing.assert_allclose(fresh['covariance'], stored['covariance'], atol=1e-8, rtol=1e-9)
            maximum_gain_difference = max(maximum_gain_difference, float(np.max(abs(fresh['gain']-stored['gain']))))
            maximum_covariance_difference = max(maximum_covariance_difference,
                float(np.max(abs(fresh['covariance']-stored['covariance']))))
        raw = np.asarray(fold['raw_native_delta_hz'])
        for variant in VARIANTS:
            aligned = align_frame_phase_branch(raw, t, receivers[1]['gain'], receivers[1]['covariance'],
                exact=variant == 'exact_sample_times')
            transformed = [receivers[0], dict(gain=aligned['gain'], covariance=aligned['covariance'])]
            for direction in [0, 1]:
                source, target = transformed if direction == 0 else transformed[::-1]
                native_delta = aligned['native_delta_hz']*(1 if direction == 0 else -1)
                arrays = (source['gain'], target['gain'], source['covariance'], target['covariance'])
                saved = next(r for r in fold['records'] if r['variant'] == variant and r['direction'] == direction)
                scores, parts = {}, {}
                for mode in ['common', 'separate', 'independent']:
                    model = fit(t[train], *(v[train] for v in arrays), native_delta, mode=mode)
                    score = predict(model, t[~train], *(v[~train] for v in arrays))
                    np.testing.assert_allclose(score, saved['models'][mode]['held_NLL'], atol=1e-7, rtol=1e-8)
                    scores[mode] = score
                    parts[mode] = component_NLL(model, t[~train], *(v[~train] for v in arrays))
                records.append(dict(parity=fold['parity'], variant=variant, direction=direction,
                    common_vs_separate_held_gain=scores['separate']-scores['common'],
                    common_vs_independent_held_gain=scores['independent']-scores['common'],
                    component_marginal_common_vs_separate_gain=parts['separate']-parts['common'],
                    component_marginal_common_vs_independent_gain=parts['independent']-parts['common']))
                if direction == 0:
                    separate = saved['models']['separate']['fit']
                    d = np.array(separate['corrected_RX_delta_hz'])
                    common = saved['models']['common']['fit']
                    closure.append(dict(parity=fold['parity'], variant=variant,
                        separate_component_disagreement_hz=float(d[1]-d[0]),
                        common_clock_mod750_hz=float(wrap(common['corrected_RX_delta_hz'][0], 750))))
    primary = [r for r in records if r['variant'] == 'exact_sample_times']
    return dict(index=row['index'], case=row['case'], window_key=entry['window_key'], cohort=row['cohort'],
        records=records, closure=closure,
        every_component_beats_independent_on_every_fold_direction=all(
            min(r['component_marginal_common_vs_independent_gain']) > 0 for r in primary),
        primary_candidate=row['conditional_common_clock_candidate'],
        native_RF_refits=4, actual_clock_model_refits=len(records)*3,
        maximum_native_difference=maximum_native_difference, maximum_gain_difference=maximum_gain_difference,
        maximum_covariance_difference=maximum_covariance_difference)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source = read(OUT/'evaluation.json')
    assert all(r['status'] == 'complete' for r in source['rows'])
    with ProcessPoolExecutor(max_workers=9) as pool:
        rows = [f.result() for f in as_completed([pool.submit(replay, r) for r in source['rows']])]
    rows.sort(key=lambda r:r['index'])
    old = read(PREVIOUS)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
    ax = axes[0]
    index = len(rows)-1
    previous = next(r for r in old['rows'] if r['index'] == index)
    current = rows[-1]
    before = []
    for f in previous['folds']:
        r = next(q for q in f['records'] if q['direction'] == 0)
        d = r['models']['separate']['fit']['corrected_RX_delta_hz']
        before.append(d[1]-d[0])
    after = [r['separate_component_disagreement_hz'] for r in current['closure'] if r['variant'] == 'exact_sample_times']
    ax.scatter([0, 1], before, label='Removed pilot CFO alias first', marker='x', s=70)
    ax.scatter([0, 1], after, label='Raw carrier + exact frame phase', marker='o', s=45)
    ax.axhline(0, color='gray', lw=.7)
    ax.set_xticks([0, 1], ['Frame fold0', 'Frame fold1'])
    ax.set(title='0216 window2506: alias bookkeeping', ylabel='Component clock disagreement (Hz)')
    ax.legend(fontsize=8)
    x = np.arange(len(rows))
    labels = [r['case'].split('-')[1]+'/'+r['window_key'].split('_')[1].lstrip('0') for r in rows]
    ax = axes[1]
    for offset, mode, color in [(-.13, 'common_vs_separate_held_gain', 'tab:blue'),
        (.13, 'common_vs_independent_held_gain', 'tab:orange')]:
        values = [min(q[mode] for q in r['records'] if q['variant'] == 'exact_sample_times') for r in rows]
        ax.scatter(x+offset, values, color=color, label='vs separate clocks' if 'separate' in mode else 'vs independent gains')
    ax.axhline(0, color='gray', lw=.7)
    ax.set_yscale('symlog', linthresh=1)
    ax.set_xticks(x, labels, rotation=70, ha='right')
    ax.set(title='Joint held NLL gain: worst RX/fold', ylabel='Positive favors common clock')
    ax.legend(fontsize=8)
    ax = axes[2]
    for k, color in [(0, 'tab:green'), (1, 'tab:red')]:
        values = [min(q['component_marginal_common_vs_independent_gain'][k]
            for q in r['records'] if q['variant'] == 'exact_sample_times') for r in rows]
        ax.scatter(x+(k-.5)*.2, values, color=color, label=f'Component{k}')
    ax.axhline(0, color='gray', lw=.7)
    ax.set_yscale('symlog', linthresh=1)
    ax.set_xticks(x, labels, rotation=70, ha='right')
    ax.set(title='Each component: worst held NLL gain', ylabel='Positive beats independent target gains')
    ax.legend(fontsize=8)
    fig.suptitle('Shared receiver-clock RF qualification:2engineering +7other windows in2scans\n'
        'Conditional RF evidence; total CFO uncertainty and position improvement remain unvalidated', fontsize=12)
    fig.savefig(OUT/'common_clock_and_alias_controls.png', dpi=160)
    plt.close(fig)
    write(OUT/'independent_replay_audit.json', dict(rows=rows,
        completed=len(rows), native_RF_refits=sum(r['native_RF_refits'] for r in rows),
        clock_model_refits=sum(r['actual_clock_model_refits'] for r in rows),
        primary_candidates=[r['index'] for r in rows if r['primary_candidate']],
        primary_candidates_with_every_component_held_gain=[r['index'] for r in rows if r['primary_candidate']
            and r['every_component_beats_independent_on_every_fold_direction']],
        source_sha256=sha(OUT/'evaluation.json'),
        not_scan_disjoint_confirmation_or_absolute_frequency_accuracy_or_position_gain=True))
    print(dict(complete=len(rows), primary=[r['index'] for r in rows if r['primary_candidate']],
        individual=[r['index'] for r in rows if r['primary_candidate'] and r['every_component_beats_independent_on_every_fold_direction']]), flush=True)


if __name__ == '__main__':
    main()
