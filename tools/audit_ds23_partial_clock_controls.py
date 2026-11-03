"""Independent source-first Gaussian replays and RF-only control figures."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_partially_shared_iq import PartiallySharedIQ
from ds23_phase_marginal_iq import PhaseMarginalIQ
from ds23_shared_receiver_phase import phase_NLL
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import common_segments
from probe_ds23_partially_shared_iq import OUT as PARTIAL,MODES
from probe_ds23_phase_marginal_iq import SOURCE
from probe_ds23_phase_clock_confirmation import OUT as CONFIRMATION
from run_algo01_ds23_sample import read,write,sha


def independent_joint_NLL(problem,p,sigma):
    physical=problem.signals(p);physical[1]*=problem.ratios(p)
    signals=[problem.expanded(physical[r],r) for r in [0,1]] if isinstance(problem,PartiallySharedIQ) else physical
    gain=problem.latent_gain if isinstance(problem,PartiallySharedIQ) else problem.gain
    total=0.
    for ix in problem.frames:
        a=signals[0][ix]-signals[0][ix].mean(axis=0);b=signals[1][ix]-signals[1][ix].mean(axis=0)
        y=problem.y[0,ix]-problem.y[0,ix].mean();z=problem.y[1,ix]-problem.y[1,ix].mean()
        h=np.diag(1/gain)+a.conj().T@a/problem.noise[0];cov=np.linalg.inv(h)
        c=a.conj().T@y/problem.noise[0];coefficient=cov@c
        source=np.vdot(y,y).real/problem.noise[0]-np.vdot(c,coefficient).real
        source+=np.linalg.slogdet(h)[1]+np.log(gain).sum()+(len(ix)-1)*np.log(np.pi*problem.noise[0])
        mean=b@coefficient;ht=h+b.conj().T@b/problem.noise[1]
        def inverse(value):return value/problem.noise[1]-b@np.linalg.solve(ht,b.conj().T@value)/problem.noise[1]**2
        cross=np.vdot(mean,inverse(z))
        statistics=dict(constant=float((len(ix)-1)*np.log(np.pi*problem.noise[1])
            +np.linalg.slogdet(ht)[1]-np.linalg.slogdet(h)[1]),
            y_quadratic=float(np.vdot(z,inverse(z)).real),mean_quadratic=float(np.vdot(mean,inverse(mean)).real),
            cross_real=float(cross.real),cross_imag=float(cross.imag))
        total+=source+phase_NLL(statistics,sigma,grid_size=8192)
    return float(total)


def audit_rows(rows,additional):
    checks=[];authority={r['index']:r for r in read(SOURCE)['rows']}
    for row in rows:
        if row['status']!='complete':raise ValueError('RF comparison failed')
        entry=row['entry'];epochs=np.asarray(row['aligned_epochs'] if additional else authority[row['index']]['aligned_epochs'])
        with np.load(entry['panel'],allow_pickle=False) as panel:raw=panel[entry['window_key']]
        samples=np.array([raw[:,r,0].astype(float)+1j*raw[:,r,1] for r in [0,1]])
        geometry=[fractional_geometry(y,entry['sample_rate_hz'],entry['edge'],epochs[k,r],dict(
            CFO_hz=entry['components'][k]['peaks'][r]['fractional_tracking_cfo_hz'],offset_samples=0.,modulation_ppm=0.))
            for r,y in enumerate(samples) for k in [0,1]]
        segments=common_segments(geometry)
        for fold in row['folds']:
            support=[ix for k,ix in enumerate(segments) if k%2==fold['parity']]
            for name,model in fold['models'].items():
                args=(samples,entry['sample_rate_hz'],entry['edge'],epochs.T,support,fold['noise_variance'],fold['source_gain_variance'])
                problem=(PhaseMarginalIQ(*args) if name=='common_clock' else
                    PartiallySharedIQ(*args,separate_clocks=True,shared_components=MODES[name]))
                fit=model['fit'];replay=independent_joint_NLL(problem,np.asarray(fit['parameters']),fit['sigma_rad'])
                delta=replay-fit['training_NLL']
                if abs(delta)>1e-5:raise ValueError('independent partial-correspondence marginal replay failed')
                checks.append(dict(index=row['index'],case=row['case'],parity=fold['parity'],model=name,
                    source_first_minus_joint_NLL=delta,converged=fit['converged']))
    return checks


def main():
    original=read(PARTIAL/'evaluation.json');additional=read(CONFIRMATION/'evaluation.json')
    audits=[]
    for directory,document,new in [(PARTIAL,original,False),(CONFIRMATION,additional,True)]:
        checks=audit_rows(document['rows'],new)
        write(directory/'independent_replay_audit.json',dict(source_sha256=sha(directory/'evaluation.json'),
            checks=checks,source_first_Gaussian_mixture_replays=len(checks),
            maximum_density_difference=max(abs(c['source_first_minus_joint_NLL']) for c in checks),
            all_density_replays_pass=True,unconverged_fits_remain_explicit=True,
            no_absolute_RF_precision_or_position_improvement_established=True))
        audits.extend(checks)
    fig,axes=plt.subplots(1,2,figsize=(14,5.2),layout='constrained')
    for ax,document,new in [(axes[0],original,False),(axes[1],additional,True)]:
        rows=document['rows'];x=np.arange(len(rows))
        for k,(label,color) in enumerate([('only_0_shared','tab:blue'),('only_1_shared','tab:orange'),('neither_shared','seagreen')]):
            gains=[min(min(q['common_vs_null_held_gain'] if new else q['both_shared_vs_null_held_gain'])
                for f in r['folds'] for q in f['comparisons'] if q['null_model']==label) for r in rows]
            ax.scatter(x+(k-1)*.12,gains,label=label,color=color,s=34)
        if new:
            gains=[min(min(q['common_vs_null_held_gain']) for f in r['folds'] for q in f['comparisons']
                if q['null_model']=='both_shared') for r in rows]
            ax.scatter(x,gains,color='purple',marker='x',label='Separate clocks, both shared')
        ax.axhline(0,color='black',lw=.8);ax.grid(alpha=.2)
        ax.set_xticks(x,[r['case'].split('-')[1]+('/'+str(r['index']) if not new else '') for r in rows],rotation=55,ha='right')
        ax.set(ylabel='Minimum held raw-IQ NLL gain',title='Four additional saved scans' if new else 'Nine previously pinned windows')
        ax.legend(fontsize=8)
    fig.suptitle('Shared signal evidence survives independent-component controls\n'
        'Positive prediction does not establish clock precision; optimizer and phase-bound checks remain required',fontsize=11)
    fig.savefig(CONFIRMATION/'partial_component_controls.png',dpi=160);plt.close(fig)
    print(dict(independent_density_replays=len(audits),max_difference=max(abs(c['source_first_minus_joint_NLL']) for c in audits)),flush=True)


if __name__=='__main__':main()
