"""Position truth is used only after all inference and isolation audits finish."""
import csv,json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
PARENT=Path('/srv/bulk/leo/research/ds25-20261024')
GROUPS=('all_channels','ch1_4','ch5_8')
ARMS=('c0','fitted_c')
METHODS=('baseline','algo02')
LABELS=dict(all_channels='CH1–8',ch1_4='CH1–4 only',ch5_8='CH5–8 only')
REFERENCE=(37.849061591561885,-122.48574968092912)


def read(p):return json.loads(p.read_bytes()) if p.exists() else {}


def error_km(point):
    a,b=np.radians([point,REFERENCE]);d=b-a
    h=np.sin(d[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h,0,1))))


def stats(rows,total):
    valid=[r for r in rows if r['error_km'] is not None];x=np.array([r['error_km'] for r in valid])
    out=dict(total_cases=total,localized=len(valid),unavailable=total-len(valid))
    if len(x):
        points=sum(r['associated_points'] for r in valid);glrt=sum(r['GLRT_points'] for r in valid)
        out.update(mean_km=float(x.mean()),median_km=float(np.median(x)),p90_km=float(np.quantile(x,.9)),
                   p95_km=float(np.quantile(x,.95)),worst_km=float(x.max()),within_1km=int((x<=1).sum()),
                   mean_curved_RMS_hz=float(np.mean([r['curved_RMS_hz'] for r in valid])),
                   associated_points=points,total_GLRT=glrt,associated_percent=100*points/glrt if glrt else None)
    return out


def common_cases(rows):
    sets=[{r['case'] for r in rows if r['group']==g and r['error_km'] is not None} for g in GROUPS]
    return set.intersection(*sets)


def main():
    assert read(ROOT/'execution.json')['all_terminal']
    assert read(ROOT/'audit.json')['passed']
    members=read(ROOT/'ch1_4/sample.json')['selected'];rows=[]
    for group in GROUPS:
        root=PARENT if group=='all_channels' else ROOT/group
        for m in members:
            case=m['dataset_label'];folder=root/case
            receipt=read(folder/'baseline_execution.json');source=read(folder/'input_receipt.json')
            prepared=read(folder/'prepared.json');old=read(folder/'algo02_result.json')
            current=read(root/'family_cavity/position'/(case+'.json'))
            methods=dict(algo02=old.get('policy_arms',{}) if old.get('status')=='accepted' else {},
                baseline=current.get('policy_arms',{}) if current.get('status')=='complete' else {})
            for method,arms in methods.items():
                valid=all(a in arms and arms[a].get('endpoint_latlon') is not None for a in ARMS)
                for arm in ARMS:
                    fit=arms.get(arm,{})
                    points=fit.get('active_points',0)+fit.get('predictive_points',old.get('linear_used_points',0) if method=='algo02' else 0)
                    rows.append(dict(case=case,recording_id=m['recording_id'],group=group,method=method,arm=arm,
                        captured_utc_ns=m['captured_utc_ns'],status='localized' if valid else receipt.get('status','missing'),
                        reason=source.get('reason',receipt.get('reason',receipt.get('error',''))),
                        error_km=error_km(fit['endpoint_latlon']) if valid else None,
                        latitude=fit.get('endpoint_latlon',[None,None])[0],longitude=fit.get('endpoint_latlon',[None,None])[1],
                        curved_RMS_hz=fit.get('RMS_hz') if valid else None,
                        associated_points=points if valid else None,
                        GLRT_points=prepared.get('GLRT_points',prepared.get('points')),
                        graph_tracks=prepared.get('graph_tracks'),curved_tracks=prepared.get('curved_tracks')))
    (ROOT/'tables').mkdir(exist_ok=True);(ROOT/'figures').mkdir(exist_ok=True)
    with (ROOT/'tables/positions.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    summary={};pairs=[]
    for method in METHODS:
        summary[method]={}
        for arm in ARMS:
            sub=[r for r in rows if r['method']==method and r['arm']==arm];common=common_cases(sub)
            grouped={g:{r['case']:r for r in sub if r['group']==g} for g in GROUPS}
            report=dict(common_cases=sorted(common),groups={})
            for g in GROUPS:
                report['groups'][g]=dict(all_available=stats(list(grouped[g].values()),34),
                    common=stats([r for c,r in grouped[g].items() if c in common],len(common)))
            report['paired_changes']={}
            for g in GROUPS[1:]:
                differences=np.array([grouped[g][c]['error_km']-grouped['all_channels'][c]['error_km'] for c in sorted(common)])
                if len(differences):report['paired_changes'][g]=dict(mean_delta_km=float(differences.mean()),
                    median_delta_km=float(np.median(differences)),improved=int((differences<-1e-6).sum()),
                    worsened=int((differences>1e-6).sum()),cases=len(common))
            for c in sorted(common):
                pairs.append(dict(case=c,method=method,arm=arm,**{g:grouped[g][c]['error_km'] for g in GROUPS}))
            summary[method][arm]=report
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (ROOT/'tables/paired_errors.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['case','method','arm',*GROUPS],lineterminator='\n');w.writeheader();w.writerows(pairs)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=dict(all_channels='#333333',ch1_4='#1976d2',ch5_8='#a348ad')
    fig,axes=plt.subplots(1,2,figsize=(13,5),sharey=True,layout='constrained')
    for ax,arm in zip(axes,ARMS):
        common=set(summary['baseline'][arm]['common_cases'])
        for i,g in enumerate(GROUPS):
            x=np.array([r['error_km'] for r in rows if r['group']==g and r['method']=='baseline' and r['arm']==arm and r['case'] in common])
            if len(x):
                ax.boxplot([x],positions=[i],widths=.4,showfliers=False)
                ax.scatter(i+np.random.default_rng(24).uniform(-.12,.12,len(x)),x,color=colors[g],s=22,alpha=.7)
        ax.set(xticks=range(3),xticklabels=[LABELS[g] for g in GROUPS],ylabel='Position error (km)',
               title=f'{"c = 0" if arm=="c0" else "Fitted c"}: {len(common)} common scans')
        ax.grid(axis='y',alpha=.25)
    fig.suptitle('DS24 fast: independent channel-restricted inference, same physical recordings')
    fig.savefig(ROOT/'figures/error_distribution.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,9),sharex=True,layout='constrained')
    for i,method in enumerate(METHODS):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j];common=set(summary[method][arm]['common_cases'])
            for g in GROUPS:
                x=np.sort([r['error_km'] for r in rows if r['group']==g and r['method']==method and r['arm']==arm and r['case'] in common])
                if len(x):ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',color=colors[g],label=f'{LABELS[g]} (n={len(x)})')
            ax.set(title=f'{method}, {arm}',xlabel='Position error (km)',ylabel='Cumulative fraction',ylim=(0,1.02))
            ax.grid(alpha=.25);ax.legend(fontsize=8)
    fig.suptitle('Common successful scans for all channel groups; missing cases listed separately')
    fig.savefig(ROOT/'figures/error_cdf.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True,sharey=True,layout='constrained')
    for ax,arm in zip(axes,ARMS):
        cases=summary['baseline'][arm]['common_cases']
        for g in GROUPS:
            mapped={r['case']:r['error_km'] for r in rows if r['group']==g and r['method']=='baseline' and r['arm']==arm}
            ax.plot(range(len(cases)),[mapped[c] for c in cases],marker='o',ms=4,color=colors[g],label=LABELS[g],lw=1)
        ax.set(title='c = 0' if arm=='c0' else 'Fitted c',ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend()
    axes[-1].set(xticks=range(len(cases)),xticklabels=[c.replace('DS24-','') for c in cases],xlabel='DS24 fast scan ID')
    fig.suptitle('Same-scan comparison: channel-restricted runs discover their own associations')
    fig.savefig(ROOT/'figures/error_by_scan.png',dpi=170);plt.close(fig)
    lines=['# DS24 fast channel-restricted results','',
        'All position errors are kilometres. The primary comparison uses the same successful scans across all three channel groups. '
        'All available results and failed/missing cases are retained separately.','',
        '| Method | c arm | Channels | Localized / 34 | Common n | Mean | Median | P95 | Worst |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for method in METHODS:
        for arm in ARMS:
            for g in GROUPS:
                s=summary[method][arm]['groups'][g];v=s['common']
                nums=' | '.join(f'{v[k]:.3f}' if k in v else '—' for k in ('mean_km','median_km','p95_km','worst_km'))
                lines.append(f"| {method} | {arm} | {LABELS[g]} | {s['all_available']['localized']}/34 | {v['localized']} | {nums} |")
    lines += ['', '![Position-error distributions](figures/error_distribution.png)','',
              '![Error by scan](figures/error_by_scan.png)','',
              '## Paired changes from CH1–8','',
              '| Method | c arm | Subset | Mean error change, km | Improved scans | Worsened scans |',
              '|---|---|---|---:|---:|---:|']
    for method in METHODS:
        for arm in ARMS:
            for g,s in summary[method][arm]['paired_changes'].items():
                lines.append(f"| {method} | {arm} | {LABELS[g]} | {s['mean_delta_km']:+.3f} | {s['improved']} | {s['worsened']} |")
    lines += ['', '## RF evidence on the common cohort','',
              'Association percentages use each subset’s own GLRT denominator. These are accepted model labels, not independently verified satellite identities. '
              'RMS measures retained curved calibration evidence; different channel groups use different observations.','',
              '| c arm | Channels | GLRT points | Associated points | Associated % | Mean curved RMS, Hz |',
              '|---|---|---:|---:|---:|---:|']
    for arm in ARMS:
        for g in GROUPS:
            v=summary['baseline'][arm]['groups'][g]['common']
            if v['localized']:lines.append(f"| {arm} | {LABELS[g]} | {v['total_GLRT']} | {v['associated_points']} | {v['associated_percent']:.2f} | {v['mean_curved_RMS_hz']:.2f} |")
    lines += ['', '![Both methods and both c controls](figures/error_cdf.png)','',
              '## Missing or unsuccessful primary runs','',
              '| Case | Channels | Status | Reason |','|---|---|---|---|']
    for r in rows:
        if r['method']=='baseline' and r['arm']=='c0' and r['error_km'] is None:
            reason=str(r['reason']).replace('|','/').replace('\n',' ')
            lines.append(f"| {r['case']} | {LABELS[r['group']]} | {r['status']} | {reason} |")
    lines += ['', '[All results including unavailable cases](tables/positions.csv), [paired errors](tables/paired_errors.csv), '
              '[full summary](summary.json), [protocol and interpretation](README.md).','']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
