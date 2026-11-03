"""Independent endpoint and gate replay for measurement-precision controls."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from ds23_synthetic_precision import make_precision_control
from probe_ds23_frequency_events import summary,cached
from probe_ds23_synthetic_noise import gate_counts
from probe_ds23_synthetic_precision import OUT,FRACTIONS,setup
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha


def replay_case(case,site):
    rows=[]
    for fraction in FRACTIONS:
        path=OUT/(case+'_fraction'+str(fraction)+'.json');saved=read(path)
        if saved['status']!='complete':raise ValueError('incomplete precision experiment')
        scan,node,mask,powers,means,hyper,entries,truth,sigma,baseline=setup(case,site,fraction)
        pair={}
        for arm in ARMS:
            r=saved['arms'][arm]
            p=make_precision_control(scan,node,mask,arm,np.asarray(r['phase_reference']),powers,means,hyper,entries,sigma);cached(p)
            fresh=summary(p,np.asarray(r['endpoint_east_north_km']),entries)
            delta=float(fresh['negative_twice_elbo']-r['negative_twice_elbo'])
            if abs(delta)>1e-6 or fresh['linear_calibration_max_difference']!=0:
                raise ValueError('precision normalized objective or curved-only calibration failed replay')
            for key in ('gates','linear_gates'):
                a=fresh[key]['tracks'] if key=='gates' else fresh[key]
                b=r[key]['tracks'] if key=='gates' else r[key]
                if [(x['component'],x['compatible']) for x in a]!=[(x['component'],x['compatible']) for x in b]:
                    raise ValueError('original precision-control gate booleans differ')
            fresh['final_phase_change_s']=r['final_phase_change_s'];pair[arm]=fresh
            rows.append(dict(case=case,fraction=fraction,arm=arm,error_km=r['synthetic_position_error_km'],
                median_declared_noise_hz=saved['declared_noise_sigma_quantiles_hz'][1],
                absolute_phase_error_s=abs(np.asarray(saved['phase_error_s'][arm])),
                residual_RMS_hz=fresh['RMS_hz'],RF_objective_replay_difference=delta,
                original_gates_pass=gate_counts(fresh)['all_original_gates_pass'],
                source_result_sha256=sha(path)))
        if valid(pair)!=saved['paired_qualified']:raise ValueError('paired original qualification changed')
    return rows


def main():
    protocol=read(OUT/'protocol.json');evaluation=read(OUT/'evaluation.json')
    if evaluation['pending'] or evaluation['failures']:raise ValueError('precision run is incomplete')
    for name,expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected:raise ValueError('precision implementation changed')
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(replay_case,c,protocol['site_by_case'][c]) for c in protocol['cases']]):rows.extend(f.result())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(16,5.5))
    labels=['Original','¼ noise','⅒ noise','¹⁄₄₀ noise']
    for ax,arm in zip(axes[:2],ARMS,strict=True):
        for k,fraction in enumerate(FRACTIONS):
            errors=[r['error_km'] for r in rows if r['fraction']==fraction and r['arm']==arm]
            ax.scatter(k+np.linspace(-.12,.12,len(errors)),errors,s=18,color='#197c91',alpha=.65)
            ax.plot([k-.2,k+.2],[np.median(errors)]*2,color='#c44c31',lw=2)
            ax.scatter([k],[np.mean(errors)],marker='D',s=30,color='#5e3c99',zorder=3)
        ax.axhline(.5,color='black',ls='--',lw=.8);ax.grid(alpha=.2)
        ax.set(xticks=range(4),xticklabels=labels,yscale='log',ylabel='Synthetic position error (km)',title=arm)
    for arm,color in zip(ARMS,['#197c91','#c44c31'],strict=True):
        values=[np.median(np.concatenate([r['absolute_phase_error_s'] for r in rows if r['fraction']==f and r['arm']==arm])) for f in FRACTIONS]
        axes[2].plot(range(4),values,'o-',label=arm,color=color)
    axes[2].set(xticks=range(4),xticklabels=labels,yscale='log',ylabel='Median absolute estimated phase error (s)',title='Phase learned from CFO; truth not supplied')
    axes[2].grid(alpha=.2);axes[2].legend()
    fig.suptitle('Measurement-precision experiment · 20 fixed DS23 templates · same nonzero nuisance and noise draws\nSame causal priors, labels, masks and regional cold start · simulated precision, not real-data accuracy\nRed bars: position medians · purple diamonds: means · declared noise floor: 1 Hz')
    fig.tight_layout();fig.savefig(OUT/'measurement_precision_diagnostics.png',dpi=175);plt.close(fig)
    write(OUT/'independent_replay_audit.json',dict(rows=rows,replayed_instance_arms=len(rows),
        maximum_RF_objective_replay_difference=max(abs(r['RF_objective_replay_difference']) for r in rows),
        protocol_sha256=sha(OUT/'protocol.json'),evaluation_sha256=sha(OUT/'evaluation.json'),
        audit_source_sha256=sha(Path(__file__)),real_DS23_accuracy_gain=False))
    print('PRECISION_AUDIT_COMPLETE',len(rows),'endpoint arms',flush=True)


if __name__=='__main__':main()
