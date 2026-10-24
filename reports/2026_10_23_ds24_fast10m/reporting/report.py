"""Evaluation only: position truth never enters inference."""
import csv
import json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parents[1]
REFERENCE=(37.849061591561885,-122.48574968092912)
METHODS=('algo02_historical','baseline','native_full','native_full_matched','native_fixed','native_contrasts')
LABELS=dict(algo02_historical='ALGO02',baseline='Current baseline',native_full='Native: existing policy',
            native_full_matched='Native: matched start',native_fixed='Native: fixed position',
            native_contrasts='Native: temporal contrasts')


def error_km(point,reference):
    a,b=np.radians([point,reference]); d=b-a
    h=np.sin(d[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h,0,1))))


def summarize(values,population):
    x=np.asarray(values,float)
    if not len(x):return dict(localized=0,population=population)
    return dict(localized=len(x),population=population,mean_km=float(x.mean()),
        median_km=float(np.median(x)),p90_km=float(np.quantile(x,.9)),
        p95_km=float(np.quantile(x,.95)),worst_km=float(x.max()),
        fraction_all_within_500m=float((x<=.5).sum()/population))


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    sample=json.loads((OUT/'sample.json').read_text());members=sample['selected']
    rows=[]; allmethods=set()
    for member in members:
        case=member['dataset_label'];path=OUT/'results'/(case+'.json')
        record=json.loads(path.read_text()) if path.exists() else {}
        methods=dict(record.get('methods',{}))
        execution=OUT/case/'baseline_execution.json'
        receipt=json.loads(execution.read_text()) if execution.exists() else {}
        for method in METHODS:
            if method not in methods:
                status=record.get('status') if record else receipt.get('status','pending')
                if status=='complete':status='method_pending_or_missing'
                methods[method]=dict(status=status,accepted=False)
        allmethods.update(methods)
        for method,saved in methods.items():
            for arm in ('c0','fitted_c'):
                s=saved.get('arms',{}).get(arm,{})
                cov=saved.get('coverage',{}).get(arm,{})
                accepted=bool(saved.get('accepted',False))
                point=s.get('endpoint_latlon')
                rows.append(dict(case=case,method=method,arm=arm,
                    status=saved.get('status','unknown'),accepted=accepted,
                    error_km=error_km(point,REFERENCE) if accepted and point is not None else None,
                    associated=cov.get('associated'),total_GLRT=cov.get('total_GLRT'),
                    frequency_RMS_hz=s.get('RMS_hz'),fallback=saved.get('fallback',False)))
    (OUT/'tables').mkdir(exist_ok=True);(OUT/'figures').mkdir(exist_ok=True)
    if not rows:raise ValueError('no numerical results')
    with (OUT/'tables/positions.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={};fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c')):
        valid={m:{r['case'] for r in rows if r['method']==m and r['arm']==arm and r['error_km'] is not None} for m in METHODS}
        paired=set.intersection(*valid.values()) if valid else set()
        summary[arm]=dict(common_qualified_cases=sorted(paired),methods={})
        for m in METHODS:
            group=[r for r in rows if r['method']==m and r['arm']==arm]
            values=[r['error_km'] for r in group if r['error_km'] is not None]
            matched=[r['error_km'] for r in group if r['case'] in paired]
            summary[arm]['methods'][m]=dict(all_qualified=summarize(values,len(members)),common=summarize(matched,len(members)))
            usable=[r for r in group if r['case'] in paired]
            numerator=sum(r['associated'] or 0 for r in usable)
            denominator=sum(r['total_GLRT'] or 0 for r in usable)
            summary[arm]['methods'][m].update(associated_points=numerator,total_GLRT=denominator,
                associated_percent=100*numerator/denominator if denominator else None,
                fallback_count=sum(bool(r['fallback']) for r in usable),
                mean_frequency_RMS_hz=float(np.mean([r['frequency_RMS_hz'] for r in usable if r['frequency_RMS_hz'] is not None])) if usable else None)
            if matched:
                x=np.sort(matched);ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=f'{LABELS[m]} (n={len(x)})')
        ax.set(title=f'{arm}: same qualified scans across methods',xlabel='Position error (km)',ylabel='Empirical cumulative fraction',ylim=(0,1.02))
        ax.grid(alpha=.25);ax.legend(fontsize=7)
    fig.suptitle('DS24 paired position-error distributions at the confirmed evaluation site')
    fig.savefig(OUT/'figures/position_error_cdf.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c')):
        paired=set(summary[arm]['common_qualified_cases'])
        methods=list(METHODS)
        data=[[r['error_km'] for r in rows if r['method']==m and r['arm']==arm and r['case'] in paired] for m in methods]
        if paired:
            ax.boxplot(data,tick_labels=[LABELS[m] for m in methods],showfliers=True)
            for j,values in enumerate(data):
                ax.scatter(np.full(len(values),j+1),values,s=12,alpha=.4)
        ax.set(title=f'{arm}, paired n={len(paired)} / {len(members)}',ylabel='Position error (km)')
        ax.tick_params(axis='x',rotation=35,labelsize=8);ax.grid(axis='y',alpha=.25)
    fig.savefig(OUT/'figures/position_error_distributions.png',dpi=170);plt.close(fig)
    summary.update(population=len(members),evaluation_reference=REFERENCE,
        reference_confirmation_required=False,reference_confirmed_by_user=True,
        no_GPS_used_by_this_report_for_inference=True)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    body=['# Numerical results','',f"Frozen DS24 population: {len(members)} recordings. Errors below use the intersection of qualified final policies across all six methods; missing positions remain in the population denominator.",'',
          '| Arm | Method | Paired n / dataset | Mean km | Median km | P95 km | Worst km | GLRT associated |',
          '|---|---|---:|---:|---:|---:|---:|---:|']
    for arm in ('c0','fitted_c'):
        for method,r in summary[arm]['methods'].items():
            s=r['common']
            metrics=[f"{s[k]:.3f}" if k in s else '—' for k in ['mean_km','median_km','p95_km','worst_km']]
            coverage=f"{r['associated_percent']:.2f}%" if r['associated_percent'] is not None else '—'
            body.append('| '+' | '.join([arm,method,f"{s['localized']} / {len(members)}",*metrics,coverage])+' |')
    body+=['','![Paired error distributions](figures/position_error_distributions.png)','',
           '![Paired empirical cumulative distributions](figures/position_error_cdf.png)','',
           'Percentiles describe only qualified paired recordings. This is the analysis-ready subset, not a random sample of DS24. Association percentage is pooled physical GLRT IDs over the same paired scans. RMS diagnostics refer to the original curved calibration observations and are not a pooled residual over recovered native points.']
    (OUT/'RESULTS.md').write_text('\n'.join(body)+'\n')


if __name__=='__main__':main()
