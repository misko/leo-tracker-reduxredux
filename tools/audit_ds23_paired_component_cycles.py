"""Replay two-component RF fits and render conditional clock-cycle checks."""

import hashlib
import numpy as np

from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from ds23_joint_gain_controls import frame_coefficients
from ds23_training_channel_rf import projected_frame_gains
from inventory_ds23_paired_component_cycles import PERIOD, wrap
from probe_ds23_cross_RX_gain_prediction import evaluate
from probe_ds23_paired_component_cycles import OUT
from run_algo01_ds23_sample import ROOT, read, write, sha


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source = read(OUT/'evaluation.json')
    audits = []
    fig, axes = plt.subplots(len(source['rows']), 2, figsize=(12, 8), layout='constrained', squeeze=False)
    for row, (ax, score_ax) in zip(source['rows'], axes, strict=True):
        entry = row['entry']
        with np.load(entry['panel'], allow_pickle=False) as panel:
            values = panel[entry['window_key']]
        assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
        samples = [values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]]
        fs, edge = entry['sample_rate_hz'], entry['edge']
        epochs = np.array(row['aligned_epochs'])
        initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
            offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
        geometry = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
            for rx, y in enumerate(samples) for k in [0, 1]]
        segments = common_segments(geometry)
        t = np.array([ix.mean()/fs for ix in segments])
        np.testing.assert_array_equal(t, row['time_s'])
        first_phases = np.random.default_rng(2026102170+row['index']).uniform(-np.pi, np.pi, (199, len(t)))[0]
        maximum_parameter_difference = maximum_gain_difference = 0.
        actual_refits = native_refits = control_refits = 0
        for mode, result in row['modes'].items():
            per_tone = mode == 'per_tone'
            actuals = [[], []]
            first_controls = [[], []]
            for fold in result['folds']:
                train = np.arange(len(t)) % 2 == fold['parity']
                support = [ix for k, ix in enumerate(segments) if train[k]]
                gains = []
                for rx, y in enumerate(samples):
                    saved_fit = fold['native_training_fits'][rx]
                    seeds = [dict(CFO_hz=p[0], offset_samples=p[1], modulation_ppm=p[2])
                        for p in np.array(saved_fit['history'][0]['parameters']).reshape(2, 3)]
                    ws = JointComponentWorkspace(y, fs, edge, epochs[:, rx], support, per_tone=per_tone)
                    replay = ws.joint_fit(seeds)
                    delta = float(max(abs(replay['parameters']-saved_fit['parameters'])))
                    maximum_parameter_difference = max(maximum_parameter_difference, delta)
                    np.testing.assert_allclose(replay['parameters'], saved_fit['parameters'], atol=1e-8, rtol=1e-10)
                    native_refits += 1
                    coefficients, covariance = frame_coefficients(y, ws.columns(replay['parameters']), segments)
                    receiver = []
                    for k in [0, 1]:
                        selection = slice(8*k, 8*k+8) if per_tone else slice(k, k+1)
                        receiver.append(projected_frame_gains(coefficients[:, selection], covariance[:, selection, selection], train))
                    gains.append(receiver)
                for k, component in enumerate(fold['components']):
                    a, b = gains[0][k]['gain'], gains[1][k]['gain']
                    va, vb = gains[0][k]['variance'], gains[1][k]['variance']
                    for prefix, gain in [('source', a), ('target', b)]:
                        saved = np.array(component[prefix+'_gain_real'])+1j*np.array(component[prefix+'_gain_imag'])
                        maximum_gain_difference = max(maximum_gain_difference, float(max(abs(gain-saved))))
                        np.testing.assert_allclose(gain, saved, atol=1e-8, rtol=1e-9)
                    corrections = []
                    for record in component['records']:
                        direction = record['direction']
                        args = (a, b, va, vb) if direction == 0 else (b, a, vb, va)
                        actual = evaluate(t, *args, train)
                        actual_refits += 1
                        np.testing.assert_allclose(actual['held_gain'], record['actual']['held_gain'], atol=1e-7, rtol=1e-8)
                        actuals[k].append(actual['held_gain'])
                        corrections.append(actual['shared']['frequency_correction_mod750_hz']*(1 if direction == 0 else -1))
                        changed = abs(b)*np.exp(1j*first_phases)
                        args = (a, changed, va, vb) if direction == 0 else (changed, a, vb, va)
                        first_controls[k].append(evaluate(t, *args, train)['held_gain'])
                        control_refits += 1
                    measured = float(wrap(component['native_delta_hz']+np.mean(corrections), PERIOD))
                    np.testing.assert_allclose(measured, component['principal_corrected_RX_delta_hz'], atol=1e-7, rtol=1e-9)
            for k, summary in enumerate(result['components']):
                np.testing.assert_allclose(min(actuals[k]), summary['minimum_held_gain'], atol=1e-7, rtol=1e-8)
                np.testing.assert_allclose(min(first_controls[k]), summary['phase_control_scores'][0], atol=1e-7, rtol=1e-8)
                p = (1+sum(np.array(summary['phase_control_scores']) >= min(actuals[k])))/200
                assert p == summary['phase_control_rank']
        audits.append(dict(case=row['case'], native_RF_refits=native_refits,
            actual_gain_model_refits=actual_refits, first_control_gain_refits=control_refits,
            maximum_parameter_difference=maximum_parameter_difference,
            maximum_gain_difference=maximum_gain_difference,
            native_glrt_seed_and_extraction_variances_conditioned=True,
            first_control_reoptimized_all199stored_null_ranks_recomputed=True))
        labels = ['Native', 'Flat fold0', 'Flat fold1', 'Tones fold0', 'Tones fold1']
        cycle = [row['original_native_component_disagreement_hz']]
        cycle += [f['principal_component_disagreement_hz'] for mode in ['flat', 'per_tone'] for f in row['modes'][mode]['folds']]
        ax.bar(np.arange(5), cycle, color=['gray', 'tab:blue', 'tab:blue', 'tab:orange', 'tab:orange'])
        ax.axhline(0, color='black', lw=.7)
        ax.set_xticks(np.arange(5), labels, rotation=25, ha='right')
        ax.set(ylabel='Component1 minus component0 RX contrast (Hz)', title=row['case']+' · same-probe clock consistency')
        for offset, mode, color in [(-.12, 'flat', 'tab:blue'), (.12, 'per_tone', 'tab:orange')]:
            scores = [c['minimum_held_gain'] for c in row['modes'][mode]['components']]
            score_ax.scatter(np.arange(2)+offset, scores, color=color, label=mode)
        score_ax.axhline(0, color='black', lw=.7)
        score_ax.set_xticks([0, 1], ['Component0', 'Component1'])
        score_ax.set(ylabel='Minimum held paired-gain NLL gain',
            title='Both RX directions/folds\nIndependent-gain baseline')
        score_ax.legend()
    fig.suptitle('Two simultaneous native component pairs: conditional RF diagnostic\n'
        '750Hz ambiguity and total covariance unvalidated; no clock or position update adopted', fontsize=12)
    fig.savefig(OUT/'component_cycle_controls.png', dpi=160)
    plt.close(fig)
    write(OUT/'independent_replay_audit.json', dict(rows=audits,
        evaluation_sha256=sha(OUT/'evaluation.json'),
        both_native_fits_and_actual_predictions_reoptimized=True,
        no_750Hz_branch_total_covariance_or_position_estimate_qualified=True))
    print(dict(completed=len(audits), audits=audits), flush=True)


if __name__ == '__main__':
    main()
