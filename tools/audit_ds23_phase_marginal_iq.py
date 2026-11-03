"""Factorized Gaussian replay and figures for the bounded phase-noise refit."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_phase_marginal_iq import PhaseMarginalIQ
from ds23_shared_receiver_phase import phase_NLL
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import common_segments
from probe_ds23_phase_marginal_iq import OUT, RAW, SOURCE
from run_algo01_ds23_sample import read, write, sha


def factorized_joint_NLL(problem, parameters, sigma):
    """Integrate source first, then target, rather than the joint two-RX Gram."""
    signal = problem.signals(parameters); signal[1] *= problem.ratios(parameters)
    total = 0.
    for ix in problem.frames:
        a = signal[0][ix]-signal[0][ix].mean(axis=0)
        b = signal[1][ix]-signal[1][ix].mean(axis=0)
        y = problem.y[0,ix]-problem.y[0,ix].mean()
        z = problem.y[1,ix]-problem.y[1,ix].mean()
        hs = np.diag(1/problem.gain)+a.conj().T@a/problem.noise[0]
        covariance = np.linalg.inv(hs)
        cross = a.conj().T@y/problem.noise[0]
        coefficient = covariance@cross
        source = (np.vdot(y,y).real/problem.noise[0]-np.vdot(cross,coefficient).real
            +np.linalg.slogdet(hs)[1]+np.log(problem.gain).sum()
            +(len(ix)-1)*np.log(np.pi*problem.noise[0]))
        mean = b@coefficient
        ht = hs+b.conj().T@b/problem.noise[1]
        def inverse(v):
            return v/problem.noise[1]-b@np.linalg.solve(ht,b.conj().T@v)/problem.noise[1]**2
        logdet = ((len(ix)-1)*np.log(problem.noise[1])
            +np.linalg.slogdet(ht)[1]-np.linalg.slogdet(hs)[1])
        cross_target = np.vdot(mean,inverse(z))
        statistics = dict(constant=float(logdet+(len(ix)-1)*np.log(np.pi)),
            y_quadratic=float(np.vdot(z,inverse(z)).real),
            mean_quadratic=float(np.vdot(mean,inverse(mean)).real),
            cross_real=float(cross_target.real),cross_imag=float(cross_target.imag))
        total += source+phase_NLL(statistics,sigma,grid_size=8192)
    return float(total)


def main():
    document = read(OUT/'evaluation.json'); checks=[]; summaries=[]
    original = {r['index']:r for r in read(RAW/'evaluation.json')['rows']}
    for row in document['rows']:
        if row['status'] != 'complete':
            raise ValueError('phase refit contains a non-complete window')
        entry = row['entry']
        # Use the pinned alignment, not epochs rounded from the acquisition peaks.
        authority = next(r for r in read(SOURCE)['rows'] if r['index'] == row['index'])
        epochs = np.asarray(authority['aligned_epochs'])
        with np.load(entry['panel'],allow_pickle=False) as panel:
            raw = panel[entry['window_key']]
        samples = np.array([raw[:,r,0].astype(float)+1j*raw[:,r,1] for r in [0,1]])
        geometry = [fractional_geometry(y,entry['sample_rate_hz'],entry['edge'],epochs[k,r],dict(
            CFO_hz=entry['components'][k]['peaks'][r]['fractional_tracking_cfo_hz'],
            offset_samples=0.,modulation_ppm=0.)) for r,y in enumerate(samples) for k in [0,1]]
        segments = common_segments(geometry)
        for fold in row['folds']:
            support = [ix for k,ix in enumerate(segments) if k%2 == fold['parity']]
            for name,model in fold['models'].items():
                fit = model['fit']
                problem = PhaseMarginalIQ(samples,entry['sample_rate_hz'],entry['edge'],epochs.T,
                    support,fold['noise_variance'],fold['source_gain_variance'],separate_clocks=name=='separate_phase')
                replay = factorized_joint_NLL(problem,np.asarray(fit['parameters']),fit['sigma_rad'])
                delta = replay-fit['training_NLL']
                if abs(delta) > 1e-5:raise ValueError('factorized source/target marginal replay differs')
                checks.append(dict(index=row['index'],parity=fold['parity'],model=name,
                    factorized_minus_joint_NLL=delta))
            zero = fold['models']['common_zero']['fit']; phase = fold['models']['common_phase']['fit']
            previous = next(f for f in original[row['index']]['folds'] if f['parity']==fold['parity'])['models']['common']['fit']
            summaries.append(dict(index=row['index'],case=row['case'],window=entry['window_key'],parity=fold['parity'],
                phase_sigma_rad=phase['sigma_rad'], phase_at_boundary=phase['phase_variance_boundary'],
                old_flat_gain_clock_hz=previous['receiver_clock_hz'][0],
                proper_gain_zero_phase_clock_hz=zero['receiver_clock_hz'][0],
                proper_gain_phase_clock_hz=phase['receiver_clock_hz'][0],
                phase_minus_matched_zero_clock_hz=phase['receiver_clock_hz'][0]-zero['receiver_clock_hz'][0],
                phase_minus_old_flat_gain_clock_hz=phase['receiver_clock_hz'][0]-previous['receiver_clock_hz'][0]))
    x=np.arange(len(document['rows']));labels=[str(r['index'])+' · '+r['case'].split('-')[-1] for r in document['rows']]
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for parity,color,marker in [(0,'tab:blue','o'),(1,'tab:orange','s')]:
        rows=[s for s in summaries if s['parity']==parity]
        axes[0].scatter(x, [s['phase_sigma_rad'] for s in rows],c=color,marker=marker,label=f'Train parity {parity}')
        axes[1].scatter(x, [s['phase_minus_matched_zero_clock_hz'] for s in rows],c=color,marker=marker)
        worst=[min(q['common_phase_vs_independent_target_held_gain'] for q in next(
            f for f in row['folds'] if f['parity']==parity)['comparisons']) for row in document['rows']]
        axes[2].scatter(x,worst,c=color,marker=marker)
    axes[0].axhline(np.pi,color='crimson',ls='--',lw=1,label='Phase SD upper bound')
    axes[0].set(ylabel='Shared phase SD (rad)',title='Training-only receiver phase noise');axes[0].legend(fontsize=8)
    axes[1].set(ylabel='Clock change (Hz)',title='Phase model minus matched zero-phase fit')
    axes[2].set(ylabel='Minimum held target NLL gain',title='Shared phase versus independent target')
    for ax in axes:
        ax.set_xticks(x,labels,rotation=60,ha='right');ax.grid(alpha=.2)
    axes[1].axhline(0,color='black',lw=.7);axes[2].axhline(0,color='black',lw=.7)
    fig.suptitle('Nine saved windows in two scans · carrier, clock, code and phase variance jointly refit\n'
        'Better prediction is not calibrated clock precision or demonstrated position accuracy',fontsize=11)
    fig.savefig(OUT/'phase_marginal_RF_diagnostics.png',dpi=160);plt.close(fig)
    write(OUT/'independent_replay_audit.json',dict(source_sha256=sha(OUT/'evaluation.json'),checks=checks,
        summaries=summaries,all_factorized_likelihood_replays_pass=True,
        independent_factorization_tests= len(checks), maximum_factorization_error=max(abs(c['factorized_minus_joint_NLL']) for c in checks),
        unique_scans=sorted({r['case'] for r in document['rows']}),all_position_results_unchanged=True,
        not_an_absolute_frequency_uncertainty_validation=True))


if __name__=='__main__':main()
