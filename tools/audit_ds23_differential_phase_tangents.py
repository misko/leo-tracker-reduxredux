"""Audit exact orbital phase at earlier differential-catalogue nominations.

All RF observations, catalogue pairs, phases, aliases and relative constants
are frozen. This diagnoses a proposal approximation; it does not select a new
identity or use geographic truth.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_causal_phase_location import adjust_means
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase'
SOURCES=[Path('/srv/bulk/leo/research/ds23-all-lane-components-20261020'),Path('/srv/bulk/leo/research/ds23-multilane-confirmation-20261020')]


def profile_constant(raw,sigma,prior_sigma=1000.):
    raw=np.asarray(raw,float)
    if raw.ndim!=2 or sigma<=0 or prior_sigma<=0 or not np.isfinite(raw).all():
        raise ValueError('finite batched residuals and positive noise/prior SD required')
    bias=raw.sum(axis=1)/(raw.shape[1]+sigma**2/prior_sigma**2)
    residual=raw-bias[:,None]
    cost=np.sum(residual**2,axis=1)/sigma**2+(bias/prior_sigma)**2+np.log1p(raw.shape[1]*prior_sigma**2/sigma**2)
    return dict(bias_hz=bias,residual=residual,cost=cost,RMS_hz=np.sqrt(np.mean(residual**2,axis=1)))


def frequencies(scan,indices,times,phases,position,rf_hz):
    indices=np.asarray(indices,int);times=np.asarray(times,float)
    bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][indices],velocity_km_s=scan.sky['velocity_km_s'][indices])
    labels=np.repeat(np.arange(len(indices)),len(times));t=np.tile(times,len(indices))
    f,e=paired_phase_frequency(bank,t,labels,np.asarray(phases,float),*latlon(position))
    return f.reshape(len(indices),len(times))*rf_hz/11.5e9,e.reshape(len(indices),len(times))


def one(case,groups):
    path=OUT/(case+'.json')
    if path.exists():return read(path)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s metadata-only exact-phase audit cap')));signal.alarm(120)
    try:
        scan,node,mask,powers,ordinary,hyper,entries,signed,signed_path=context_signed(case)
        _,receipts=phase_widths(scan,list(range(len(scan.norads))));means=forecast_phase_mean(receipts,hyper['shrinkage'])
        if signed['accepted']:means=adjust_means(means,receipts,hyper,signed['selection'])
        rows=[]
        for item in groups:
            root=Path(item['source']);catalogue=read(root/'catalogue'/(item['group']+'.json'))
            evaluation=read(root/'evaluation.json');protocol=read(root/'protocol.json')
            ids={j['probe'] for j in protocol['jobs'] if j['group']==item['group']}
            rf=sorted([r for r in evaluation['rows'] if r['case']==case and r['probe'] in ids and r['status']=='complete' and r['two_components_qualified']],key=lambda r:r['time_s'])
            stat=next(r for r in evaluation['summary'] if r['group']==item['group'])['RF_qualified_statistics']
            t=np.array([r['time_s'] for r in rf]);y=np.array([r['refined_second_value']-r['refined_first_value'] for r in rf]);noise=stat['difference_sigma_hz']
            lane=next(r['lane'] for r in protocol['selected'] if r['group']==item['group'])
            for position_name,summary in catalogue['results'].items():
                position=np.zeros(2) if position_name=='regional_centre' else np.asarray(signed['policy_arms']['c0']['endpoint_east_north_km'])
                candidates=summary['candidates'];indices=[j for r in candidates for j in [r['first_index'],r['second_index']]]
                phases=np.array([v for r in candidates for v in [r['phase_first_s'],r['phase_second_s']]])
                mu=np.asarray(means)[indices]
                f,_=frequencies(scan,indices,t,mu,position,lane[2])
                plus,_=frequencies(scan,indices,t,mu+.01,position,lane[2]);minus,_=frequencies(scan,indices,t,mu-.01,position,lane[2])
                linear=f+(plus-minus)/.02*(phases-mu)[:,None]
                exact,elevation=frequencies(scan,indices,t,phases,position,lane[2])
                tangent=linear[1::2]-linear[::2];actual=exact[1::2]-exact[::2]
                aliases=np.array([r['difference_alias'] for r in candidates]);bias=np.array([r['relative_bias_hz'] for r in candidates])
                observed=y[None]+aliases[:,None]*PERIOD
                replay=np.sqrt(np.mean((observed-tangent-bias[:,None])**2,axis=1))
                assert np.max(abs(replay-np.array([r['RMS_hz'] for r in candidates])))<1e-5
                refit=profile_constant(observed-actual,noise)
                for k,r in enumerate(candidates):
                    difference=actual[k]-tangent[k]
                    rows.append(dict(group=item['group'],position=position_name,rank=k,first_norad=r['first_norad'],second_norad=r['second_norad'],
                        phase_first_s=r['phase_first_s'],phase_second_s=r['phase_second_s'],noise_sigma_hz=noise,points=len(t),span_s=float(np.ptp(t)),
                        tangent_RMS_hz=r['RMS_hz'],exact_frozen_bias_RMS_hz=float(np.sqrt(np.mean((observed[k]-actual[k]-bias[k])**2))),
                        exact_refitted_bias_RMS_hz=float(refit['RMS_hz'][k]),
                        tangent_approximation_RMS_hz=float(np.sqrt(np.mean(difference**2))),
                        centred_tangent_approximation_RMS_hz=float(np.std(difference)),
                        exact_above_horizon=bool(elevation[2*k:2*k+2].min()>=0),source_catalogue_sha256=sha(root/'catalogue'/(item['group']+'.json'))))
        result=dict(case=case,status='complete',rows=rows,signed_sha256=sha(signed_path),
            GPS_or_new_RF_or_postscan_TLE_used=False,no_identity_or_position_changed=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    write(path,result);print(case,result['status'],len(result.get('rows',[])),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);groups=[]
    for root in SOURCES:
        for r in read(root/'catalogue/execution.json')['rows']:
            if r['status']=='complete':groups.append(dict(case=r['case'],group=r['group'],source=str(root)))
    protocol=dict(groups=groups,all_saved_top20_pairs_at_both_positions=True,
        observations_phases_aliases_and_constants_frozen=True,relative_constant_refit_as_separate_diagnostic=True,
        maximum_seconds_per_case=120,workers=6,no_GPS_new_RF_postscan_TLE_or_new_identity=True,
        source_sha256=sha(Path(__file__)))
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('exact-phase audit protocol changed')
    if not path.exists():write(path,protocol)
    cases=sorted({r['case'] for r in groups})
    with ProcessPoolExecutor(max_workers=6) as pool:results=[f.result() for f in as_completed([pool.submit(one,c,[g for g in groups if g['case']==c]) for c in cases])]
    rows=[v for r in results for v in r.get('rows',[])]
    write(OUT/'evaluation.json',dict(cases=results,rows=rows,all_terminal=True,no_position_accuracy_gain_claim=True))
    if rows:
        fig,axes=plt.subplots(1,2,figsize=(11,4.6));first=[r for r in rows if r['rank']==0]
        for ax,subset,title in [(axes[0],rows,'All saved top20 nominations'),(axes[1],first,'Rank-one nominations')]:
            x=np.array([r['tangent_RMS_hz'] for r in subset]);y=np.array([r['exact_refitted_bias_RMS_hz'] for r in subset])
            ax.scatter(x,y,s=12,alpha=.5);limit=max(x.max(),y.max());ax.plot([0,limit],[0,limit],'k--',lw=1)
            ax.set(xlabel='Phase-tangent RMS (Hz)',ylabel='Exact-phase RMS; constant refitted (Hz)',title=title);ax.grid(alpha=.2)
        fig.suptitle('Earlier differential-catalogue proposals · exact phase check; no new association accepted')
        fig.tight_layout();fig.savefig(OUT/'phase_tangent_audit.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
