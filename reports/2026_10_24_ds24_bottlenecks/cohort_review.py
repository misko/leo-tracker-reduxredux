"""Saved-estimate comparisons and evaluation-only fixed-site loss diagnostics.

No GPS coordinate enters a fitted-position or association decision. The supplied
evaluation site is used only to probe the already selected model at fixed x.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv, json, argparse, hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent
HALF=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
FULL=Path('/srv/bulk/leo/research/ds25-20261024')
TRUTH=np.array([37.849061591561885,-122.48574968092912])
GROUPS=['all_channels','ch1_4','ch5_8']
COLORS=['#222222','#2786bd','#df7e25']

def write(path,value):
    def conv(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,default=conv,indent=2)+'\n')

def rows():
    return [r for r in csv.DictReader((HALF/'tables/positions.csv').open())
            if r['method']=='baseline' and r['status']=='localized']

def errors(r):
    # Consistent local tangent coordinate, adequate for these <10 km comparisons.
    return np.array([(float(r['longitude'])-TRUTH[1])*111.320*np.cos(np.deg2rad(TRUTH[0])),
                     (float(r['latitude'])-TRUTH[0])*111.132])

def saved_comparison():
    data=rows();cases=sorted({r['case'] for r in data});results={}
    for arm in ('c0','fitted_c'):
        vectors={g:np.array([errors(next(r for r in data if r['case']==case and r['arm']==arm and r['group']==g)) for case in cases]) for g in GROUPS}
        stats={}
        for g,v in vectors.items():
            z=v-v.mean(axis=0)
            stats[g]=dict(mean_vector_east_north_km=v.mean(axis=0),mean_error_km=np.linalg.norm(v,axis=1).mean(),
                          RMS_error_km=np.sqrt(np.mean(np.sum(v*v,axis=1))),
                          bias_squared_fraction=float(np.sum(v.mean(axis=0)**2)/np.mean(np.sum(v*v,axis=1))),
                          centered_covariance=np.cov(v.T),median_error_km=np.median(np.linalg.norm(v,axis=1)))
        lo,hi=vectors['ch1_4'],vectors['ch5_8'];mid=(lo+hi)/2
        cl,ch=lo-lo.mean(axis=0),hi-hi.mean(axis=0)
        cross=float(np.sum(cl*ch)/np.sqrt(np.sum(cl*cl)*np.sum(ch*ch)))
        stats['unweighted_midpoint_diagnostic']=dict(mean_error_km=float(np.linalg.norm(mid,axis=1).mean()),
            median_error_km=float(np.median(np.linalg.norm(mid,axis=1))),RMS_error_km=float(np.sqrt(np.mean(np.sum(mid*mid,axis=1)))),
            improved_vs_joint=int(np.sum(np.linalg.norm(mid,axis=1)<np.linalg.norm(vectors['all_channels'],axis=1))))
        results[arm]=dict(statistics=stats,half_centered_error_vector_correlation=cross,
            median_half_endpoint_separation_km=float(np.median(np.linalg.norm(lo-hi,axis=1))),vectors=vectors,cases=cases)
    write(OUT/'cohort_summary.json',results)
    fig,axs=plt.subplots(1,2,figsize=(12,5.5),constrained_layout=True)
    for ax,arm in zip(axs,results):
        v=results[arm]['vectors']
        for g,col in zip(GROUPS,COLORS):
            z=v[g];ax.scatter(z[:,0],z[:,1],s=23,c=col,label=g.replace('_',' '),alpha=.75)
            ax.scatter(*z.mean(axis=0),s=160,marker='X',c=col,edgecolors='white')
        for i in range(len(cases)):
            ax.plot([v[g][i,0] for g in ['ch1_4','all_channels','ch5_8']],
                    [v[g][i,1] for g in ['ch1_4','all_channels','ch5_8']],c='gray',alpha=.17,lw=.7)
        ax.scatter(0,0,marker='*',s=170,c='#36a04d',label='Evaluation GPS');ax.axhline(0,c='gray',lw=.5);ax.axvline(0,c='gray',lw=.5)
        ax.set(title=arm.replace('_',' '),xlabel='East error (km)',ylabel='North error (km)',aspect='equal');ax.grid(alpha=.2)
    axs[0].legend(fontsize=8);fig.suptitle('24 paired DS24 scans: endpoint error vectors\nX marks cohort mean; gray joins the same scan, not optimizer paths')
    (OUT/'figures').mkdir(exist_ok=True);fig.savefig(OUT/'figures/error_vectors.png',dpi=170);plt.close(fig)
    return cases

def fixed_site(case):
    import algo02_scan as algo
    from probe_ds23_graph_seeded_paths import build
    from debug_algo02_ds23_0268 import decomposition
    saved_result=json.loads((FULL/'family_cavity/position'/f'{case}.json').read_text())
    algo.bind_run_directory(FULL)
    selected=saved_result['selected'] if saved_result['accepted'] else None
    d=dict(scan=algo.load_scan(FULL,case),keep=np.asarray(saved_result['original_mask'],bool),
           powers=np.asarray(saved_result['powers']),model=saved_result['model'],
           node=selected['node'] if selected else saved_result['baseline_node'],
           entries=selected['entries'] if selected else saved_result['baseline_entries'],
           means=np.asarray(selected['means'] if selected else saved_result['baseline_means']),
           arms=saved_result['policy_arms'])
    # The local engine uses these exact coordinate conversion factors.
    from scipy.optimize import root
    from prototype_dsx01_continuous_position import latlon
    truth_x=root(lambda x: np.array(latlon(x))-TRUTH,[5.,-6.]).x
    result=dict(case=case,fixed_evaluation_xy=truth_x,arms={})
    for arm,saved in d['arms'].items():
        x=np.array(saved['endpoint_east_north_km']);ref=np.array(saved['phase_reference'])
        p=build(d,'default',arm,ref);c=p.calculate(x)
        replay=float(c['negative_twice_elbo']-saved['negative_twice_elbo'])
        # Small solver/BLAS roundoff is recorded; accept only a tiny absolute
        # AND relative error against the saved full objective.
        if abs(replay)>min(1e-3,1e-8*max(abs(saved['negative_twice_elbo']),1)):
            raise ValueError(f'endpoint replay {case} {arm}: {replay}')
        original=dict(loss=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),decomposition=decomposition(p,x))
        history=[]
        for _ in range(8):
            p=build(d,'default',arm,ref);c=p.calculate(truth_x)
            nextref=np.clip(p.state(truth_x)['phases'][p.labels],-15,15)
            change=float(np.max(np.abs(nextref-ref)));history.append(change)
            if change<1e-5:break
            ref=nextref
        diagnostic=dict(loss=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),decomposition=decomposition(p,truth_x),phase_changes_s=history)
        result['arms'][arm]=dict(endpoint=original,evaluation_site=diagnostic,replay_difference=replay,
            loss_at_truth_minus_endpoint=float(diagnostic['loss']-original['loss']),
            RMS_at_truth_minus_endpoint_hz=float(diagnostic['RMS_hz']-original['RMS_hz']))
    write(OUT/'objective'/f'{case}.json',result)
    return dict(case=case,status='complete')

def plot_objectives():
    rr=[json.loads(p.read_text()) for p in sorted((OUT/'objective').glob('DS24*.json'))]
    fig,axs=plt.subplots(1,2,figsize=(12,4.7),constrained_layout=True)
    summary={}
    for arm,col in zip(['c0','fitted_c'],['#3185bd','#cb496c']):
        dl=np.array([r['arms'][arm]['loss_at_truth_minus_endpoint'] for r in rr]);dr=np.array([r['arms'][arm]['RMS_at_truth_minus_endpoint_hz'] for r in rr])
        axs[0].plot(range(len(rr)),dl,'.-',label=arm,c=col,alpha=.8);axs[1].plot(range(len(rr)),dr,'.-',label=arm,c=col,alpha=.8)
        summary[arm]=dict(n=len(rr),truth_higher_loss_count=int(sum(dl>0)),loss_gap_median=float(np.median(dl)),loss_gap_range=[float(dl.min()),float(dl.max())],RMS_gap_median_hz=float(np.median(dr)),RMS_gap_range_hz=[float(dr.min()),float(dr.max())])
    for ax in axs:
        ax.axhline(0,c='gray',lw=.7);ax.set_xticks(range(len(rr)),[r['case'][-4:] for r in rr],rotation=90,fontsize=8);ax.grid(alpha=.2);ax.set_xlabel('DS24 scan');ax.legend()
    axs[0].set_ylabel('Loss at GPS − loss at returned position');axs[1].set_ylabel('RMS at GPS − RMS at returned position (Hz)')
    fig.suptitle('Fixed-site diagnostic: same observations and satellite labels\nNuisance coefficients refitted and orbital phase refreshed at the evaluation GPS')
    fig.savefig(OUT/'figures/objective_at_truth.png',dpi=170);plt.close(fig)
    write(OUT/'objective_summary.json',summary)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--objectives',action='store_true');parser.add_argument('--case');a=parser.parse_args()
    cases=saved_comparison()
    if a.case: print(fixed_site(a.case),flush=True)
    elif a.objectives:
        pending=[c for c in cases if not (OUT/'objective'/f'{c}.json').exists()]
        with ProcessPoolExecutor(max_workers=4) as pool:
            for f in as_completed({pool.submit(fixed_site,c):c for c in pending}):print(f.result(),flush=True)
        plot_objectives()
