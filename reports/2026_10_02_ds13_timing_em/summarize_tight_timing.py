"""Audit and summarize the isolated hard-bounded Gaussian timing experiment."""
import csv
import json
from pathlib import Path
import numpy as np
from run_tight_timing_comparison import OUT,BASE,ROOT


def run():
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    parent=json.loads((BASE/'receipt.json').read_text());scans=[];rows=[];hashes=snapshot_files([__file__,BASE/'receipt.json'])
    for oldscan in parent['scans']:
        sid=oldscan['session'];path=OUT/sid/'result.json';scan=json.loads(path.read_text())
        assert_snapshot_unchanged(scan['source_hashes']);hashes.update(scan['source_hashes']);hashes.update(snapshot_files([path]))
        scan['old_variants']=oldscan['variants'];violations=[]
        for e in scan['evaluations']:
            path=OUT/sid/f"fit-{e['index']:04d}.json";fit=json.loads(path.read_text());hashes.update(snapshot_files([path]))
            d=np.asarray(fit['individual_tau_s']);common=fit['common_tau_s']
            assert abs(common)<=1+1e-7 and np.max(np.abs(d))<=.5+1e-7
            assert abs(d.sum())<1e-9
            np.testing.assert_allclose(fit['total_tau_s'],common+d,rtol=0,atol=1e-10)
            prior=.5*common**2+.5*np.sum((d/.5)**2)
            np.testing.assert_allclose(prior,fit['nuisance_prior_nll'],rtol=0,atol=1e-8)
            np.testing.assert_allclose(fit['objective'],fit['data_nll']+prior,rtol=0,atol=1e-7)
            assert fit['detection_probability']==.8/len(oldscan['candidates'])
            if not fit['success']:violations.append(dict(index=e['index'],kkt_residual=fit['kkt_residual']))
        scan['unconverged_evaluations']=violations
        for v,old in zip(scan['variants'],oldscan['variants']):
            assert v['policy']==old['policy'] and v['threshold']==old['threshold']
            best=v['best'];roof_support=float(sum(v['roof']['satellite_support']))
            rows.append(dict(scan=scan['scan_index'],session=sid,threshold='off' if v['threshold'] is None else v['threshold'],
                original_error_m=v['old_distance_m'],new_error_m=v['distance_m'],change_m=v['distance_m']-v['old_distance_m'],
                original_boundary=old['boundary'],new_boundary=v['boundary'],new_best_converged=best['success'],
                new_best_kkt_residual=best['kkt_residual'],start_agreement_m=v['start_agreement_m'],
                minimum_neighbor_increase=min(n['delta'] for n in v['neighbors']),
                original_roof_support=v['old_roof_support'],new_roof_support=roof_support,
                roof_support_change_pct=100*(roof_support/v['old_roof_support']-1),
                new_roof_gradient_norm=float(np.linalg.norm(v['roof_gradient_per_100m'])),gradient_check=v['gradient_check'],
                common_timing_s=best['common_tau_s'],common_bound_active=best['common_bound_active'],
                individual_bounds_active=best['individual_bound_active_count'],candidate_count=len(v['policy']['kept'])))
        scans.append(scan)
    colors=['#0072B2','#E69F00','#009E73','#CC79A7'];labels=['Off','1.1','1.075','1.05','1.025']
    fig,axes=plt.subplots(2,2,figsize=(13,9),sharey=True)
    supportfig,supportaxes=plt.subplots(2,2,figsize=(13,9),sharey=True)
    for scan,ax,sax,color in zip(scans,axes.flat,supportaxes.flat,colors):
        current=[r for r in rows if r['scan']==scan['scan_index']]
        x=np.arange(5)
        ax.plot(x,[r['original_error_m']/1000 for r in current],ls='--',color='.55',lw=1.5)
        ax.plot(x,[r['new_error_m']/1000 for r in current],color=color,lw=2)
        for i,(r,old) in enumerate(zip(current,scan['old_variants'])):
            om='^' if old['boundary'] else '*' if old['start_agreement_m']>1 else 'o'
            nm='x' if not r['new_best_converged'] else '^' if r['new_boundary'] else '*' if r['start_agreement_m']>1 else 'o'
            ax.scatter(i,r['original_error_m']/1000,marker=om,s=65,edgecolor='.45',facecolor='white',zorder=3)
            ax.scatter(i,r['new_error_m']/1000,marker=nm,s=95 if nm=='*' else 65,color=color,zorder=4)
        ax.set_ylim(bottom=0);ax.set_xticks(x,labels);ax.grid(alpha=.2)
        ax.set_xlabel('Frozen curvature-filter cutoff');ax.set_ylabel('Best-found distance from roof (km)')
        ax.set_title(f"Scan {scan['scan_index']} · {scan['session'][8:]}",fontsize=11)
        sax.bar(x-.17,[r['original_roof_support'] for r in current],width=.34,color='.65',label='Original')
        sax.bar(x+.17,[r['new_roof_support'] for r in current],width=.34,color=color,label='Tight timing')
        sax.set_xticks(x,labels);sax.grid(axis='y',alpha=.2);sax.set_xlabel('Frozen curvature-filter cutoff')
        sax.set_ylabel('Effective associated GLRT groups at roof')
        sax.set_title(f"Scan {scan['scan_index']} · {scan['session'][8:]}",fontsize=11)
    axes.flat[0].set_ylim(0,1.08*max(max(r['original_error_m'],r['new_error_m'])/1000 for r in rows))
    legend=[Line2D([],[],ls='--',color='.55',label='Original timing'),Line2D([],[],color='k',label='Tight timing')]
    fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.5,.94),ncol=2,frameon=False)
    fig.suptitle('Four DS13 scans · tighter zero-centered timing priors and hard bounds',fontsize=16)
    fig.text(.5,.025,'New: common σ=1 s, bound ±1 s; individual deviation σ=0.5 s, bound ±0.5 s. Same frozen satellite sets.\nTriangle: position-search boundary. Star: starts differ. Cross: convergence not verified. These are local searches.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.09,1,.90));fig.savefig(OUT/'timing-prior-comparison.png',dpi=170);plt.close(fig)
    supportfig.suptitle('Same observations · association support before and after tightening timing',fontsize=15)
    supportaxes.flat[0].legend();supportfig.text(.5,.025,'Sum of posterior satellite associations, not a hard track count. Lower support can mean more observations assigned to clutter.\nEvaluated at the known roof, with all original GLRT groups retained and all allowed nuisance terms refitted.',ha='center',fontsize=10)
    supportfig.tight_layout(rect=(0,.09,1,.94));supportfig.savefig(OUT/'timing-prior-support.png',dpi=170);plt.close(supportfig)
    with (OUT/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert_snapshot_unchanged(hashes)
    receipt=dict(scans=scans,summary=rows,source_hashes=hashes,configuration=dict(common_sigma_s=1.,common_bound_s=1.,individual_sigma_s=.5,individual_bound_s=.5),
        scope='Compare position errors and association support, not absolute scores across different priors. All exclusions frozen from original experiment. '
        'Hard constraints checked on actual zero-sum satellite deviations, not Helmert coordinates. Total shifts may reach +/-1.5s. '
        'RX/RF nuisance model unchanged. Local constrained searches, not independently validated localization performance.')
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    for r in rows:print(r)


if __name__=='__main__':run()
