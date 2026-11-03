"""Independent raw-IQ objective/prediction replays and phase residual diagnostics."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import numpy as np
from scipy.linalg import null_space

from ds23_joint_receiver_iq import JointReceiverIQ, conditional_frame_density
from ds23_joint_component_rf import common_segments
from ds23_fractional_differential_phase import fractional_geometry
from probe_ds23_joint_receiver_iq import OUT
from run_algo01_ds23_sample import ROOT, read, write, sha


def context(row):
    entry = row['entry']
    with np.load(entry['panel'], allow_pickle=False) as panel:
        values = panel[entry['window_key']]
    assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
    samples = np.array([values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]])
    fs, edge = entry['sample_rate_hz'], entry['edge']
    epochs = np.array([c['epochs'] for c in entry['components']])
    for k in [0, 1]:
        epochs[k, 1] += np.rint((epochs[k, 0]-epochs[k, 1])/(fs/750))*(fs/750)
    initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
        offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
    geometries = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
        for rx, y in enumerate(samples) for k in [0, 1]]
    return samples, fs, edge, epochs.T, common_segments(geometries)


def independent_Q(problem, parameters):
    signals = problem.signals(parameters)
    signals[1] *= problem.ratios(parameters)
    total = 0.
    for ix in problem.frames:
        n = len(ix)
        x = np.zeros((2*n, 4), complex)
        x[:n, :2], x[n:, :2] = signals[0][ix], signals[1][ix]
        x[:n, 2], x[n:, 3] = 1., 1.
        w = np.repeat(1/np.sqrt(problem.noise), n)
        x *= w[:, None]
        y = np.r_[problem.y[0, ix], problem.y[1, ix]]*w
        c = np.linalg.lstsq(x, y, rcond=1e-8)[0]
        error = y-x@c
        total += float(np.vdot(error, error).real)
    return total


def dense_prediction(source, target, bs, bt, var_source, var_target):
    x = np.column_stack((bs, np.ones(len(bs))))
    c = np.linalg.lstsq(x, source, rcond=1e-8)[0]
    covariance = var_source*np.linalg.inv(x.conj().T@x)[:2, :2]
    q = null_space(np.ones((1, len(target))))
    error = q.conj().T@(target-bt@c[:2])
    dense = q.conj().T@(var_target*np.eye(len(target))+bt@covariance@bt.conj().T)@q
    return float(np.vdot(error, np.linalg.solve(dense, error)).real
        + np.linalg.slogdet(dense)[1]+(len(target)-1)*np.log(np.pi))


def frame_phases(problem, parameters, segments, training):
    signals = problem.signals(parameters)
    signals[1] *= problem.ratios(parameters)
    phases, variances, amplitudes = [], [], []
    for ix in segments:
        gain, covariance = [], []
        for r in [0, 1]:
            x = np.column_stack((signals[r][ix], np.ones(len(ix))))
            coefficient = np.linalg.lstsq(x, problem.y[r, ix], rcond=1e-8)[0]
            gain.append(coefficient[:2])
            covariance.append(problem.noise[r]*np.linalg.inv(x.conj().T@x)[:2, :2])
        phases.append(np.angle(gain[1]/gain[0]))
        variances.append(.5*(np.diag(covariance[0]).real/abs(gain[0])**2
            + np.diag(covariance[1]).real/abs(gain[1])**2))
        amplitudes.append(abs(gain[1]/gain[0]))
    phases, variances = np.array(phases), np.array(variances)
    return dict(time_s=np.array([ix.mean()/problem.fs for ix in segments]),
        phase_residual_rad=phases, conditional_thermal_phase_variance=variances,
        gain_amplitude_ratio=amplitudes, training_frames=training,
        held_phase_component_correlation=float(np.corrcoef(phases[~training].T)[0, 1]),
        held_component_phase_RMS_rad=np.sqrt(np.mean(phases[~training]**2, axis=0)))


def one(row):
    samples, fs, edge, epochs, segments = context(row)
    maximum_Q_difference = maximum_parameter_difference = maximum_dense_difference = 0.
    diagnostics = []
    refits = 0
    for fold in row['folds']:
        train = np.arange(len(segments)) % 2 == fold['parity']
        support = [ix for k, ix in enumerate(segments) if train[k]]
        held = [ix for k, ix in enumerate(segments) if not train[k]]
        for mode, saved in fold['models'].items():
            fitted = saved['fit']
            problem = JointReceiverIQ(samples, fs, edge, epochs, support,
                saved['noise_variance_from_training_IQ_only'], separate_clocks=mode == 'separate')
            reoptimized = problem.fit(np.array(fitted['history'][0]['parameters']), iterations=30)
            refits += 1
            difference = float(max(abs(np.asarray(fitted['parameters'])-reoptimized['parameters'])))
            maximum_parameter_difference = max(maximum_parameter_difference, difference)
            np.testing.assert_allclose(reoptimized['parameters'], fitted['parameters'], atol=1e-8, rtol=1e-10)
            q = independent_Q(problem, np.asarray(fitted['parameters']))
            maximum_Q_difference = max(maximum_Q_difference, abs(q-fitted['quadratic']))
            np.testing.assert_allclose(q, fitted['quadratic'], atol=1e-6, rtol=1e-9)
            signals = problem.signals(np.asarray(fitted['parameters']))
            signals[1] *= problem.ratios(np.asarray(fitted['parameters']))
            for direction, expected in enumerate(saved['predictions']):
                actual = problem.predict(np.array(fitted['parameters']), held, source_receiver=direction)
                np.testing.assert_allclose(actual['NLL'], expected['NLL'], atol=1e-6, rtol=1e-9)
                ix = held[0]
                subset = ix[np.linspace(0, len(ix)-1, 64).astype(int)]
                a = conditional_frame_density(samples[direction, ix], samples[1-direction, subset],
                    signals[direction][ix], signals[1-direction][subset], problem.noise[direction], problem.noise[1-direction])
                b = dense_prediction(samples[direction, ix], samples[1-direction, subset],
                    signals[direction][ix], signals[1-direction][subset], problem.noise[direction], problem.noise[1-direction])
                maximum_dense_difference = max(maximum_dense_difference, abs(a['NLL']-b))
                np.testing.assert_allclose(a['NLL'], b, atol=1e-7, rtol=1e-9)
            if mode == 'common':
                diagnostics.append(dict(parity=fold['parity'], **frame_phases(problem,
                    np.asarray(fitted['parameters']), segments, train)))
    return dict(index=row['index'], case=row['case'], window_key=row['entry']['window_key'], cohort=row['cohort'],
        RF_optimizations_replayed=refits, maximum_Q_difference=maximum_Q_difference,
        maximum_parameter_difference=maximum_parameter_difference, maximum_dense_prediction_difference=maximum_dense_difference,
        frame_phase_diagnostics=diagnostics, primary_candidate=row['conditional_raw_IQ_common_clock_candidate'])


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source = read(OUT/'evaluation.json')
    assert all(r['status'] == 'complete' for r in source['rows'])
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one, r) for r in source['rows']])]
    rows.sort(key=lambda r:r['index'])
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
    x = np.arange(len(rows))
    labels = [r['case'].split('-')[1]+'/'+r['window_key'].split('_')[1].lstrip('0') for r in rows]
    originals = source['rows']
    ax = axes[0]
    for offset, rx in [(-.1, 0), (.1, 1)]:
        ax.scatter(x+offset, [min(f['common_vs_separate_held_gain'][rx] for f in r['folds']) for r in originals], label=f'Source RX{rx+1}')
    ax.axhline(0, color='gray', lw=.7)
    ax.set_yscale('symlog', linthresh=1)
    ax.set(ylabel='Worst-fold held NLL gain', title='Positive favors common physical RX clock')
    ax.legend(fontsize=8)
    ax = axes[1]
    gaps = [min(min(f['wrong_global750Hz_alias_training_Q_gap'].values()) for f in r['folds']) for r in originals]
    ax.scatter(x, gaps)
    ax.set(ylabel='Minimum wrong-branch increase in Q', title='Both global clock aliases +/-750Hz')
    ax = axes[2]
    normalized = []
    for r in originals:
        a, b = [f['models']['common']['fit'] for f in r['folds']]
        sigma = np.sqrt(a['frequency_covariance'][2][2]+b['frequency_covariance'][2][2])
        normalized.append(abs(a['receiver_clock_hz'][0]-b['receiver_clock_hz'][0])/sigma)
    ax.scatter(x, normalized)
    ax.axhline(1, color='gray', lw=.7)
    ax.set(ylabel='Fold clock difference / Gaussian sigma', title='Local Gaussian covariance is optimistic')
    for ax in axes:
        ax.set_xticks(x, labels, rotation=70, ha='right')
    fig.suptitle('Joint raw-IQ carrier/clock validation:9windows in2scans; no position change adopted', fontsize=12)
    fig.savefig(OUT/'joint_IQ_clock_controls.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(3, 3, figsize=(13, 10), layout='constrained')
    for ax, r in zip(axes.ravel(), rows, strict=True):
        d = r['frame_phase_diagnostics'][0]
        times = np.asarray(d['time_s'])*1000
        phases = np.asarray(d['phase_residual_rad'])
        training = np.asarray(d['training_frames'])
        for k, color in [(0, 'tab:blue'), (1, 'tab:orange')]:
            ax.plot(times, phases[:, k], color=color, lw=.6, alpha=.5)
            ax.scatter(times[training], phases[training, k], color=color, marker='o', s=18, label=f'Component{k} training')
            ax.scatter(times[~training], phases[~training, k], color=color, marker='x', s=28, label=f'Component{k} held')
        ax.axhline(0, color='gray', lw=.6)
        ax.set(title=r['case']+'/'+r['window_key'], xlabel='Saved-window time(ms)', ylabel='RX phase residual(rad)')
    axes[0, 0].legend(fontsize=6)
    fig.suptitle('Independently extracted RX phase residuals after common raw-IQ fit\n'
        'Per-frame TX gains remain free; held phases are diagnostic, not calibration inputs', fontsize=12)
    fig.savefig(OUT/'joint_IQ_frame_phase_residuals.png', dpi=150)
    plt.close(fig)
    write(OUT/'independent_replay_audit.json', dict(rows=rows, completed=len(rows),
        raw_RF_optimizations_replayed=sum(r['RF_optimizations_replayed'] for r in rows),
        independent_complex_LS_objective_replays=sum(r['RF_optimizations_replayed'] for r in rows),
        independent_dense_predictive_covariance_checks=2*sum(r['RF_optimizations_replayed'] for r in rows),
        source_sha256=sha(OUT/'evaluation.json'), no_absolute_CFO_truth_or_covariance_coverage_or_position_gain_established=True))
    print(dict(completed=len(rows), optimizations=sum(r['RF_optimizations_replayed'] for r in rows)), flush=True)


if __name__ == '__main__':
    main()
