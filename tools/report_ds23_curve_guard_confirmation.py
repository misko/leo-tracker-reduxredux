"""Score the random20 only after its RF-only decisions have been sealed."""

from pathlib import Path
import shutil
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import confirm_ds23_curve_predictive_guard as study
import report_ds23_dbg01_iteration_003 as report
from run_algo01_ds23_sample import ROOT, read, write

OUT=report.OUT
METHODS=['Published incumbent','Unrestricted curve growth','Family-predictive guard']


def summarize(rows):
    result=[]
    for method in METHODS:
        for arm in ['c0','fitted_c']:
            selected=[r for r in rows if r['method']==method and r['arm']==arm]
            errors=np.asarray([r['position_error_km'] for r in selected])
            total=sum(r['all_GLRT'] for r in selected);associated=sum(r['associated_points'] for r in selected)
            result.append(dict(method=method,arm=arm,scans=len(selected),mean_error_km=float(np.mean(errors)),
                median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9)),
                worst_error_km=float(max(errors)),within_half_km=int(sum(errors<=.5)),
                total_GLRT=total,associated_points=associated,pooled_association_percent=100*associated/total,
                mean_scan_association_percent=float(np.mean([r['associated_percent'] for r in selected])),
                mean_curved_RMS_hz=float(np.mean([r['RMS_hz'] for r in selected])),
                original_accepted_points_lost=sum(r['original_accepted_points_lost'] for r in selected)))
    return result


def main():
    path=study.RAW/'family_predictive_guard/selection.json';selection=read(path)
    assert selection['all_passed'] and selection['selection_sealed_before_geographic_reporting']
    study.configure();cases=read(study.RAW/'protocol.json')['cases'];rows=[]
    assert len(cases)==len(set(cases))==20
    for case in cases:
        data=study.context.current_setup(case)
        baseline=read(study.RAW/case/'inventory.json')['arms']
        proposal=read(study.RAW/'all_curve_families'/(case+'_positions.json'))['selected']
        expanded=read(study.RAW/'all_curve_families'/(case+'_audit.json'))['coverage']
        decision=next(r for r in selection['rows'] if r['case']==case)
        _,expanded_arms=report.curves.baseline_or_trial(data,proposal)
        for method,arms,inventory in [(METHODS[0],data['arms'],baseline),(METHODS[1],expanded_arms,expanded),
            (METHODS[2],expanded_arms if decision['adopted'] else data['arms'],expanded if decision['adopted'] else baseline)]:
            for arm,fit in arms.items():
                r=report.result_row(case,method,arm,fit,inventory[arm],baseline[arm])
                r.update(proposal_exists=proposal is not None,guard_adopted=decision['adopted'])
                rows.append(r)
    summary=summarize(rows);changes=[]
    for arm in ['c0','fitted_c']:
        for method in METHODS[1:]:
            old={r['case']:r for r in rows if r['method']==METHODS[0] and r['arm']==arm}
            new=[r for r in rows if r['method']==method and r['arm']==arm]
            difference=np.array([r['position_error_km']-old[r['case']]['position_error_km'] for r in new])
            changes.append(dict(method=method,arm=arm,improved=int(sum(difference<-1e-6)),
                worse=int(sum(difference>1e-6)),unchanged=int(sum(abs(difference)<=1e-6)),
                mean_error_change_km=float(np.mean(difference)),worst_regression_km=float(max(difference)),
                best_gain_km=float(-min(difference))))
    report.figures.csv_write(OUT/'tables/confirmation_positions.csv',rows)
    report.figures.csv_write(OUT/'tables/confirmation_summary.csv',summary)
    report.figures.csv_write(OUT/'tables/confirmation_paired_changes.csv',changes)
    colors=['tab:blue','tab:orange','tab:green']
    fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained')
    ordered=sorted(cases,key=lambda c:-next(r['position_error_km'] for r in rows if r['case']==c and r['method']==METHODS[0] and r['arm']=='fitted_c'))
    for method,color in zip(METHODS,colors,strict=True):
        subset=[next(r for r in rows if r['case']==c and r['method']==method and r['arm']=='fitted_c') for c in ordered]
        axes[0].plot(range(20),[r['position_error_km'] for r in subset],'.-',label=method,c=color)
        axes[1].scatter([r['associated_percent'] for r in subset],[r['position_error_km'] for r in subset],label=method,c=color,s=24,alpha=.7)
    axes[0].set_xticks(range(20),[c.replace('DS23-','') for c in ordered],rotation=70)
    axes[0].set(xlabel='Scan (sorted by incumbent error)',ylabel='Position error (km)');axes[0].legend(fontsize=8)
    axes[1].set(xlabel='Original GLRT associated (%)',ylabel='Position error (km)')
    for ax in axes:ax.axhline(.5,c='gray',ls='--');ax.grid(alpha=.2)
    fig.suptitle('Preselected random20 · frozen RF-only decisions · fitted c\n'
                 'All20 scans included; rejected/no-proposal scans use exact incumbent; same DS23 site')
    fig.savefig(OUT/'figures/confirmation_positions.png',dpi=165);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(14,5),layout='constrained')
    for j,(metric,label) in enumerate([('mean_error_km','Mean error (km)'),('median_error_km','Median error (km)'),('pooled_association_percent','Pooled association (%)')]):
        for a,arm in enumerate(['c0','fitted_c']):
            for k,(method,color) in enumerate(zip(METHODS,colors,strict=True)):
                r=next(r for r in summary if r['method']==method and r['arm']==arm)
                x=a+(k-1)*.25;axes[j].bar(x,r[metric],width=.23,color=color,label=method if a==0 else None)
                axes[j].text(x,r[metric]+(.025 if j<2 else .4),f"{r[metric]:.3f}" if j<2 else f"{r[metric]:.1f}",ha='center',fontsize=7,rotation=0)
        axes[j].set_xticks([0,1],['c=0','fitted c']);axes[j].set_ylabel(label);axes[j].grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=7);axes[0].axhline(.5,c='gray',ls='--');axes[1].axhline(.5,c='gray',ls='--')
    fig.suptitle('Random20 confirmation · separate localization and RF coverage outcomes')
    fig.savefig(OUT/'figures/confirmation_summary.png',dpi=165);plt.close(fig)
    write(OUT/'evidence/confirmation_evaluation.json',dict(rows=rows,summary=summary,changes=changes,
        all20_cases_included=True,selection_sealed_before_geographic_reporting=True,
        same_site_previously_studied_dataset_not_untouched_or_new_location_validation=True))
    for name in ['protocol.json','family_predictive_guard/protocol.json','family_predictive_guard/selection.json',
                 'family_predictive_guard/folds_execution.json','all_curve_families/audit_execution.json']:
        shutil.copyfile(study.RAW/name,OUT/'evidence'/('confirmation_'+name.replace('/','_')))
    # One archive per case keeps individual published artifacts small without
    # dropping any raw endpoint, nomination, covariance or fold evidence.
    archives=OUT/'evidence/confirmation_receipts';archives.mkdir(exist_ok=True)
    sources={c:[] for c in cases};sources['common']=[]
    for p in sorted(study.RAW.rglob('*')):
        if not p.is_file() or p.suffix not in ['.json','.csv']:continue
        relative=p.relative_to(study.RAW)
        owner=next((c for c in cases if c in relative.parts or p.name.startswith(c+'_')), 'common')
        sources[owner].append(p)
    for case,paths in sources.items():
        with tarfile.open(archives/(case+'.tar.gz'),'w:gz') as archive:
            for p in paths:archive.add(p,arcname=str(p.relative_to(study.RAW)),recursive=False)
    write(archives/'index.json',{case:dict(files=len(paths),uncompressed_bytes=sum(p.stat().st_size for p in paths))
                                  for case,paths in sources.items()})
    shutil.copyfile(Path(__file__),OUT/'source/tools'/Path(__file__).name)
    for r in summary:print(r,flush=True)
    print('paired changes',changes,flush=True)


if __name__=='__main__':main()
