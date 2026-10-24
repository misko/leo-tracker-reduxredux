"""GPS-only reporting after the inference cohort reaches terminal accounting."""
import csv
import json
from pathlib import Path
from datetime import datetime, UTC
import numpy as np

OUT=Path(__file__).resolve().parent
REFERENCE=(37.849061591561885,-122.48574968092912)
ARMS=('c0','fitted_c')
METHODS=('baseline','algo02')
MODES=('adaptive','fast')


def error_km(point):
    a,b=np.radians([point,REFERENCE]);d=b-a
    q=np.sin(d[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(q,0,1))))


def statistics(rows,population):
    valid=[r for r in rows if r['error_km'] is not None]
    x=np.array([r['error_km'] for r in valid],float)
    result=dict(population=population,localized=len(valid),unavailable=population-len(valid))
    if not len(x):return result
    result.update(mean_km=float(x.mean()),median_km=float(np.median(x)),
        p90_km=float(np.quantile(x,.9)),p95_km=float(np.quantile(x,.95)),worst_km=float(x.max()),
        within_500m=int((x<=.5).sum()),within_1km=int((x<=1).sum()),
        mean_curved_RMS_hz=float(np.mean([r['curved_RMS_hz'] for r in valid])))
    return result


def temporal_sensitivity(rows):
    """Equal weight shared 3-hour UTC blocks; resample whole blocks, not scans."""
    groups={mode:{} for mode in MODES}
    for r in rows:
        if r['error_km'] is None:continue
        block=r['captured_utc_ns']//(3*3600*10**9)
        groups[r['mode']].setdefault(block,[]).append(r['error_km'])
    blocks=sorted(set(groups['adaptive']) & set(groups['fast']))
    if not blocks:return dict(shared_blocks=0)
    means={mode:np.array([np.mean(groups[mode][b]) for b in blocks]) for mode in MODES}
    diffs=means['adaptive']-means['fast']
    rng=np.random.default_rng(250024)
    boot=diffs[rng.integers(0,len(blocks),(4000,len(blocks)))].mean(axis=1)
    return dict(shared_blocks=len(blocks),block_hours=3,
        adaptive_mean_km=float(means['adaptive'].mean()),fast_mean_km=float(means['fast'].mean()),
        adaptive_minus_fast_km=float(diffs.mean()),
        bootstrap_95pct_km=np.quantile(boot,[.025,.975]).tolist(),
        blocks=[dict(start_utc=datetime.fromtimestamp(b*3*3600,UTC).isoformat(),
                     adaptive_n=len(groups['adaptive'][b]),fast_n=len(groups['fast'][b]),
                     adaptive_mean_km=float(means['adaptive'][i]),fast_mean_km=float(means['fast'][i]))
                for i,b in enumerate(blocks)])


def read(path):return json.loads(path.read_text()) if path.exists() else {}


def main():
    execution=read(OUT/'execution.json')
    if not execution.get('all_terminal'):raise ValueError('wait for all cases before geographic evaluation')
    sample=read(OUT/'sample.json');rows=[];compact=[]
    for member in sample['selected']:
        case=member['dataset_label'];folder=OUT/case
        receipt=read(folder/'baseline_execution.json')
        old=read(folder/'algo02_result.json')
        current=read(OUT/'family_cavity/position'/(case+'.json'))
        methods=dict(algo02=old.get('policy_arms',{}) if old.get('status')=='accepted' else {},
            baseline=current.get('policy_arms',{}) if current.get('status')=='complete' else {})
        source=read(folder/'input_receipt.json');prepared=read(folder/'prepared.json')
        compact.append(dict(case=case,mode=member['mode'],execution=receipt,input_receipt=source,
                            prepared=prepared,methods=methods))
        for method,arms in methods.items():
            pair_ok=all(a in arms and arms[a].get('endpoint_latlon') is not None for a in ARMS)
            for arm in ARMS:
                fit=arms.get(arm,{})
                rows.append(dict(case=case,parent_case=member.get('parent_dataset_label',case),
                    recording_id=member['recording_id'],mode=member['mode'],method=method,arm=arm,
                    captured_utc_ns=member['captured_utc_ns'],
                    utc=datetime.fromtimestamp(member['captured_utc_ns']/1e9,UTC).isoformat(),
                    status='localized' if pair_ok else receipt.get('status','missing'),
                    reason=source.get('reason',receipt.get('reason',receipt.get('error',''))),
                    error_km=error_km(fit['endpoint_latlon']) if pair_ok else None,
                    latitude=fit.get('endpoint_latlon',[None,None])[0],
                    longitude=fit.get('endpoint_latlon',[None,None])[1],
                    curved_RMS_hz=fit.get('RMS_hz') if pair_ok else None,
                    curved_points=fit.get('active_points'),predictive_points=fit.get('predictive_points'),
                    GLRT_points=prepared.get('GLRT_points',prepared.get('points')),graph_tracks=prepared.get('graph_tracks'),
                    curved_tracks=prepared.get('curved_tracks')))
    (OUT/'figures').mkdir(exist_ok=True);(OUT/'tables').mkdir(exist_ok=True)
    with (OUT/'tables/positions.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    summary={}
    for method in METHODS:
        summary[method]={}
        for arm in ARMS:
            subset=[r for r in rows if r['method']==method and r['arm']==arm]
            summary[method][arm]={mode:statistics([r for r in subset if r['mode']==mode],
                sum(m['mode']==mode for m in sample['selected'])) for mode in MODES}
            summary[method][arm]['shared_time_blocks']=temporal_sensitivity(subset)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (OUT/'compact_results.json').write_text(json.dumps(compact,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    colors=dict(adaptive='#8e44ad',fast='#1976d2')
    fig,axes=plt.subplots(2,2,figsize=(12,9),layout='constrained')
    for i,method in enumerate(METHODS):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j]
            for mode in MODES:
                group=[r for r in rows if r['method']==method and r['arm']==arm and r['mode']==mode and r['error_km'] is not None]
                x=np.sort([r['error_km'] for r in group]);pop=sum(m['mode']==mode for m in sample['selected'])
                if len(x):ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',color=colors[mode],
                                 label=f'{mode.capitalize()}: {len(x)}/{pop} localized')
            ax.set(title=f'{"Current baseline" if method=="baseline" else "Original ALGO02"} — {arm}',
                   xlabel='Position error (km)',ylabel='Cumulative fraction of localized scans',ylim=(0,1.02))
            ax.grid(alpha=.25);ax.legend(fontsize=9)
    fig.suptitle('DS25 adaptive vs DS24 fast: same frozen interval, matched inference settings')
    fig.savefig(OUT/'figures/position_error_cdf.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True,layout='constrained')
    for ax,arm in zip(axes,ARMS):
        for i,mode in enumerate(MODES):
            x=np.array([r['error_km'] for r in rows if r['method']=='baseline' and r['arm']==arm and r['mode']==mode and r['error_km'] is not None])
            if len(x):
                ax.boxplot([x],positions=[i],widths=.4,showfliers=False)
                jitter=np.random.default_rng(25).uniform(-.13,.13,len(x))
                ax.scatter(i+jitter,x,s=17,alpha=.65,color=colors[mode])
        labels=[f"{mode.capitalize()}\n{summary['baseline'][arm][mode]['localized']}/{summary['baseline'][arm][mode]['population']} localized" for mode in MODES]
        ax.set(xticks=[0,1],xticklabels=labels,ylabel='Position error (km)',title='c = 0' if arm=='c0' else 'Fitted c')
        ax.grid(axis='y',alpha=.25)
    fig.suptitle('Current baseline: every localized scan; missing cases counted separately')
    fig.savefig(OUT/'figures/position_error_distribution.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(13,7),sharex=True,sharey=True,layout='constrained')
    for ax,arm in zip(axes,ARMS):
        for mode in MODES:
            group=[r for r in rows if r['method']=='baseline' and r['arm']==arm and r['mode']==mode]
            good=[r for r in group if r['error_km'] is not None];bad=[r for r in group if r['error_km'] is None]
            ax.scatter([datetime.fromtimestamp(r['captured_utc_ns']/1e9,UTC) for r in good],
                       [r['error_km'] for r in good],s=23,color=colors[mode],label=mode)
            ax.scatter([datetime.fromtimestamp(r['captured_utc_ns']/1e9,UTC) for r in bad],
                       [-.15]*len(bad),marker='x',s=18,color=colors[mode])
        ax.axhline(0,color='gray',lw=.5);ax.grid(alpha=.2)
        ax.set(title=arm,ylabel='Position error (km)');ax.legend()
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M',tz=UTC))
    axes[-1].set_xlabel('Acquisition start (UTC); crosses below zero indicate unavailable localization')
    fig.suptitle('Temporal coverage and position error: shared interval does not mean simultaneous scans')
    fig.savefig(OUT/'figures/position_error_by_time.png',dpi=170);plt.close(fig)
    lines=['# DS25 adaptive versus same-interval fast position error','',
           'All errors are kilometres. Statistics use every paired localization produced by the stated method. '
           'Coverage is reported against 69 adaptive and 34 fast scans; missing inputs and failed runs have no fabricated position error.','',
           '| Method | c arm | Mode | Localized / total | Mean | Median | P90 | P95 | Worst | Within 1 km |',
           '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for method in METHODS:
        for arm in ARMS:
            for mode in MODES:
                s=summary[method][arm][mode]
                val=lambda k:f"{s[k]:.3f}" if k in s else '—'
                lines.append(f"| {method} | {arm} | {mode} | {s['localized']}/{s['population']} | "+
                             ' | '.join(val(k) for k in ('mean_km','median_km','p90_km','p95_km','worst_km'))+
                             f" | {s.get('within_1km',0)} |")
    lines += ['', '![Current-baseline error distribution](figures/position_error_distribution.png)','',
              '![Both methods and both c arms](figures/position_error_cdf.png)','',
              '## Shared time blocks','',
              'This comparison gives equal weight to shared 3-hour UTC blocks. Intervals resample whole blocks '
              'and describe adaptive minus fast mean error; they do not remove input-availability bias.','',
              '| Method | c arm | Shared blocks | Adaptive mean | Fast mean | Difference | Block-bootstrap 95% interval |',
              '|---|---|---:|---:|---:|---:|---|']
    for method in METHODS:
        for arm in ARMS:
            s=summary[method][arm]['shared_time_blocks']
            if s['shared_blocks']:
                lo,hi=s['bootstrap_95pct_km']
                lines.append(f"| {method} | {arm} | {s['shared_blocks']} | {s['adaptive_mean_km']:.3f} | "
                             f"{s['fast_mean_km']:.3f} | {s['adaptive_minus_fast_km']:+.3f} | [{lo:+.3f}, {hi:+.3f}] |")
    lines += ['', '![Time coverage and errors](figures/position_error_by_time.png)','',
              '## Frequency fit, reported separately','',
              'These RMS values describe retained curved calibration evidence. The two acquisition modes '
              'have different observations; lower RMS is not itself better localization.','',
              '| Method | c arm | Adaptive mean curved RMS, Hz | Fast mean curved RMS, Hz |','|---|---|---:|---:|']
    for method in METHODS:
        for arm in ARMS:
            s=summary[method][arm]
            lines.append(f"| {method} | {arm} | {s['adaptive'].get('mean_curved_RMS_hz',float('nan')):.2f} | "
                         f"{s['fast'].get('mean_curved_RMS_hz',float('nan')):.2f} |")
    lines += ['', '## Cases without a completed primary localization','',
              '| Case | Mode | Status | Reason |','|---|---|---|---|']
    for r in rows:
        if r['method']=='baseline' and r['arm']=='c0' and r['error_km'] is None:
            reason=str(r['reason']).replace('|','/').replace('\n',' ')
            lines.append(f"| {r['case']} | {r['mode']} | {r['status']} | {reason} |")
    lines += ['', '[All per-scan rows](tables/positions.csv), [machine-readable summary](summary.json), '
              '[full protocol and dataset details](README.md).','']
    (OUT/'RESULTS.md').write_text('\n'.join(lines))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
