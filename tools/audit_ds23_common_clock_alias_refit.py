"""Replay RF carrier-branch scores and each shared-clock component prediction."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

import audit_ds23_common_receiver_clock as clock_audit
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from inventory_ds23_paired_component_cycles import PERIOD
from probe_ds23_common_clock_alias_refit import OUT
from run_algo01_ds23_sample import ROOT, read, write, sha

CONTROL = ROOT/'reports/2026_10_21_ds23_common_receiver_clock_v2/evaluation.json'


def profiled_score(samples, columns, segments):
    raw = residual = 0.
    for ix in segments:
        design = np.column_stack((columns[ix], np.ones(len(ix))))
        coefficient = np.linalg.lstsq(design, samples[ix], rcond=1e-8)[0]
        error = samples[ix]-design@coefficient
        residual += float(np.vdot(error, error).real)
        y = samples[ix]-samples[ix].mean()
        raw += float(np.vdot(y, y).real)
    return float(1-residual/raw)


def replay(row):
    base = clock_audit.replay(row)
    entry = row['entry']
    old = next(r for r in read(CONTROL)['rows'] if r['index'] == row['index'])
    with np.load(entry['panel'], allow_pickle=False) as panel:
        values = panel[entry['window_key']]
    samples = [values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]]
    fs, edge, epochs = entry['sample_rate_hz'], entry['edge'], np.asarray(row['aligned_epochs'])
    initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
        offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
    geometry = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
        for rx, y in enumerate(samples) for k in [0, 1]]
    segments = common_segments(geometry)
    rf = []
    for fold in row['folds']:
        train = np.arange(len(segments)) % 2 == fold['parity']
        support = [ix for k, ix in enumerate(segments) if train[k]]
        held = [ix for k, ix in enumerate(segments) if not train[k]]
        old_fold = next(f for f in old['folds'] if f['parity'] == fold['parity'])
        for rx, samples_rx in enumerate(samples):
            fitted = fold['native_training_fits'][rx]
            training = JointComponentWorkspace(samples_rx, fs, edge, epochs[:, rx], support)
            actuals = []
            for branch in fitted['branch_scores']:
                score = training.statistics(np.array(branch['parameters']), derivatives=False)['score']
                np.testing.assert_allclose(score, branch['training_score'], atol=1e-12, rtol=1e-10)
                actuals.append(score)
            assert list(fitted['selected_pilot_aliases']) == list(fitted['branch_scores'][int(np.argmax(actuals))]['pilot_aliases'])
            test = JointComponentWorkspace(samples_rx, fs, edge, epochs[:, rx], held)
            p = np.asarray(fitted['parameters'])
            native_p = np.asarray(old_fold['native_training_fits'][rx]['parameters'])
            selected = test.statistics(p, derivatives=False)['score']
            native = test.statistics(native_p, derivatives=False)['score']
            actual_columns = test.columns(p).copy()
            rolled = test.columns(p, control=True)
            component_margins = []
            for k in [0, 1]:
                changed = actual_columns.copy()
                changed[:, k] = rolled[:, k]
                component_margins.append(selected-profiled_score(samples_rx, changed, held))
            canonical_delta = p[::3]-native_p[::3]-np.array(fitted['selected_pilot_aliases'])*PERIOD
            rf.append(dict(parity=fold['parity'], receiver=rx+1,
                selected_aliases=fitted['selected_pilot_aliases'], selected_held_score=float(selected),
                native_held_score=float(native), held_score_ratio=float(selected/native),
                canonical_CFO_delta_hz=canonical_delta,
                conditional_component_held_rolled_margins=component_margins,
                all9recorded_training_branch_scores_independently_replayed=True))
    return dict(base, RF=rf)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source = read(OUT/'evaluation.json')
    assert all(r['status'] == 'complete' for r in source['rows'])
    with ProcessPoolExecutor(max_workers=9) as pool:
        rows = [f.result() for f in as_completed([pool.submit(replay, r) for r in source['rows']])]
    rows.sort(key=lambda r:r['index'])
    labels = [r['case'].split('-')[1]+'/'+r['window_key'].split('_')[1].lstrip('0') for r in rows]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
    x = np.arange(len(rows))
    ax = axes[0]
    for offset, parity in [(-.1, 0), (.1, 1)]:
        gain = [next(q['held_score_ratio'] for q in r['RF'] if q['receiver'] == 2 and q['parity'] == parity) for r in rows]
        ax.scatter(x+offset, gain, label=f'Frame fold{parity}')
    ax.axhline(1, color='gray', lw=.7)
    ax.set_xticks(x, labels, rotation=70, ha='right')
    ax.set(ylabel='Selected/native held RF explained energy', title='RX2: branch selected on training IQ only')
    ax.legend(fontsize=8)
    ax = axes[1]
    for component, color in [(0, 'tab:blue'), (1, 'tab:orange')]:
        value = [min(q['conditional_component_held_rolled_margins'][component] for q in r['RF']) for r in rows]
        ax.scatter(x+(component-.5)*.2, value, color=color, label=f'Component{component}')
    ax.axhline(0, color='gray', lw=.7)
    ax.set_xticks(x, labels, rotation=70, ha='right')
    ax.set(ylabel='Worst RX/fold held actual-minus-rolled score', title='Individual component pilot support')
    ax.legend(fontsize=8)
    ax = axes[2]
    for component, color in [(0, 'tab:green'), (1, 'tab:red')]:
        value = [min(q['component_marginal_common_vs_independent_gain'][component]
            for q in r['records'] if q['variant'] == 'exact_sample_times') for r in rows]
        ax.scatter(x+(component-.5)*.2, value, color=color, label=f'Component{component}')
    ax.axhline(0, color='gray', lw=.7)
    ax.set_yscale('symlog', linthresh=1)
    ax.set_xticks(x, labels, rotation=70, ha='right')
    ax.set(ylabel='Worst RX/fold held paired-gain NLL gain', title='Common clock: each component vs independent')
    ax.legend(fontsize=8)
    fig.suptitle('RF carrier-branch search and common-clock prediction:2scans,9windows\n'
        'Pilot branch correction improves RF evidence; no position improvement established', fontsize=12)
    fig.savefig(OUT/'RF_branch_and_clock_controls.png', dpi=160)
    plt.close(fig)
    write(OUT/'independent_replay_audit.json', dict(rows=rows, completed=len(rows),
        native_RF_refits=sum(r['native_RF_refits'] for r in rows),
        clock_model_refits=sum(r['actual_clock_model_refits'] for r in rows),
        training_RF_branch_profile_replays=sum(len(r['RF'])*9 for r in rows),
        primary_candidates=[r['index'] for r in rows if r['primary_candidate']],
        primary_candidates_with_all_component_prediction_support=[r['index'] for r in rows
            if r['primary_candidate'] and r['every_component_beats_independent_on_every_fold_direction']],
        source_sha256=sha(OUT/'evaluation.json'),
        no_new_location_or_absolute_frequency_precision_or_position_gain_established=True))
    print(dict(complete=len(rows), candidates=[r['index'] for r in rows if r['primary_candidate']],
        branch_replays=sum(len(r['RF'])*9 for r in rows)), flush=True)


if __name__ == '__main__':
    main()
