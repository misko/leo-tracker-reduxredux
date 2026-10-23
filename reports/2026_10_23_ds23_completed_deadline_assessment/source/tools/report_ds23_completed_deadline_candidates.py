"""Report the frozen410-case completed-candidate replay, without new fitting."""

from collections import Counter
from pathlib import Path
import shutil
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import inventory_ds23_completed_deadline_candidates as study
from analyze_ds23_paired_evidence_population import bootstrap
from audit_ds23_archived_qualification import qualification
from run_algo02_ds23 import DEFAULT_RUN
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_ds23_dbg01_iteration_001 import csv_write

OUT=ROOT/'reports/2026_10_23_ds23_completed_deadline_assessment'
OLD_QUAL=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_006_raw/archived_qualification/v2/audit.json'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=150);plt.close(fig)


def summarize(rows):
    errors=np.array([r['error_km'] for r in rows]);changes=np.array([r['error_change_km'] for r in rows])
    return dict(cases=len(rows),mean_error_km=float(errors.mean()),median_error_km=float(np.median(errors)),
        p90_error_km=float(np.quantile(errors,.9)),maximum_error_km=float(errors.max()),
        improved=int(sum(changes< -1e-6)),worsened=int(sum(changes>1e-6)),regressions_over500m=int(sum(changes>.5)),
        associated_points=sum(r['associated_points'] for r in rows),total_GLRT=sum(r['total_GLRT'] for r in rows))


def main():
    for folder in ['figures','tables','evidence','source/tools','source/tests']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    data=read(study.OUT/'evaluation/evaluation.json');selection=read(study.OUT/'evaluation/RF_selection.json');inventory=read(study.OUT/'RF_inventory.json')
    assert data['canonical_baseline_reproduced'] and read(study.OUT/'fresh_audit/execution.json')['all_passed']
    assert sha(study.OUT/'evaluation/RF_selection.json')==data['RF_selection_sha256']
    assert selection['RF_selection_frozen_before_geographic_evaluation'] and len(selection['rows'])==410
    rows=data['rows'];methods=['Incumbent','Completed deadline candidate'];arms=['c0','fitted_c'];meta=read(DEFAULT_RUN/'sample.json')
    metadata={r['dataset_label']:r for r in meta['selected']};formats=[];uncertainty=[]
    cases=sorted(r['case'] for r in selection['rows']);changed=[r for r in rows if r['accepted_rescue']]
    selected=[r for r in selection['rows'] if r['accepted']];audits=[];offers=[];qualification_rows=[]
    oldqual={(r['case'],r['arm']):r for r in read(OLD_QUAL)['rows']}
    for choice in selection['rows']:
        if choice['accepted']:
            source=study.SOURCE/'reentry'/(choice['case']+'.json');assert sha(source)==choice['source_sha256'];record=read(source)
            trial=record['trials'][choice['trial_index']];a=read(study.OUT/'fresh_audit'/(choice['case']+'.json'))
            assert sha(study.OUT/'fresh_audit'/(choice['case']+'.json'))==choice['audit_sha256']
            audits.extend(dict(case=choice['case'],**r) for r in a['checks'])
            offers.append(dict(case=choice['case'],trial=choice['trial_index'],norad=trial['offer']['norad'],
                new_curved_points=trial['group']['added_points'],owners=trial['group']['owners'],rows=trial['group']['rows'],
                completed_trials=len(record['trials']),search_seconds=record['seconds'],status=record['status'],
                fine_receiver_basis=True,original_400second_fit_budget_unchanged=True))
        for arm in arms:
            q=qualification(trial['arms'][arm]) if choice['accepted'] else oldqual[choice['case'],arm]
            qualification_rows.append(dict(case=choice['case'],arm=arm,qualified=q['qualified'],
                strict_phase_limit_pass=q['strict_phase_limit_pass'],residual_gates_pass=q['residual_gates_pass'],
                phase_refresh_converged=q['phase_refresh_converged'],regional_box_pass=q['regional_box_pass'],
                fresh_numerical_replay=choice['accepted']))
    for arm in arms:
        old={r['case']:r for r in rows if r['arm']==arm and r['method']==methods[0]}
        new={r['case']:r for r in rows if r['arm']==arm and r['method']==methods[1]}
        assert len(old)==len(new)==410 and set(old)==set(new)==set(cases)
        for fmt in sorted({metadata[c]['recording_format'] for c in cases}):
            for method in methods:
                rr=[r for r in rows if r['arm']==arm and r['method']==method and metadata[r['case']]['recording_format']==fmt]
                formats.append(dict(arm=arm,method=method,recording_format=fmt,**summarize(rr)))
        a=np.array([old[c]['error_km'] for c in cases]);b=np.array([new[c]['error_km'] for c in cases]);times=[metadata[c]['captured_utc_ns'] for c in cases]
        for hours in [1,3,6]:uncertainty.append(dict(arm=arm,**bootstrap(a,b,times,hours,seed=2026102313)))
    quals=[dict(arm=arm,cases=410,qualified=sum(r['qualified'] for r in qualification_rows if r['arm']==arm),
                exceptions=[r['case'] for r in qualification_rows if r['arm']==arm and not r['qualified']]) for arm in arms]
    assert all(r['exceptions']==['DS23-0068'] for r in quals)
    assert all(sum(r['associated_points'] for r in changed if r['arm']==arm)-sum(r['associated_points'] for r in rows if r['arm']==arm and r['method']==methods[0] and r['case'] in {c['case'] for c in selected})==729 for arm in arms)
    csv_write(OUT/'tables/positions.csv',rows);csv_write(OUT/'tables/summary.csv',data['summary']);csv_write(OUT/'tables/changed_cases.csv',changed)
    csv_write(OUT/'tables/format_summary.csv',formats);csv_write(OUT/'tables/bootstrap.csv',uncertainty);csv_write(OUT/'tables/native_replay.csv',audits)
    csv_write(OUT/'tables/completed_offers.csv',offers);csv_write(OUT/'tables/status_inventory.csv',inventory['rows']);csv_write(OUT/'tables/qualification.csv',qualification_rows)

    fig,axes=plt.subplots(2,3,figsize=(17,10),layout='constrained')
    for k,arm in enumerate(arms):
        for j,method in enumerate(methods):
            rr=next(r for r in data['summary'] if r['arm']==arm and r['method']==method)
            for m,key in enumerate(['mean_error_km','median_error_km']):
                x=m+(j-.5)*.32;axes[k,0].bar(x,rr[key],width=.3,color=f'C{j}',label=method if m==0 else None);axes[k,0].text(x,rr[key]+.01,f'{rr[key]:.4f}',ha='center',fontsize=9)
            er=sorted(r['error_km'] for r in rows if r['arm']==arm and r['method']==method)
            axes[k,1].plot(er,np.arange(1,411)/410,label=method)
            axes[k,2].bar(j,rr['associated_percent'],color=f'C{j}');axes[k,2].text(j,rr['associated_percent']+.01,f"{rr['associated_percent']:.4f}%",ha='center')
        axes[k,0].set(title=arm,ylabel='Position error (km)',xticks=[0,1],xticklabels=['Mean','Median']);axes[k,0].axhline(.5,c='green',ls='--',label='Goal');axes[k,0].legend(fontsize=8)
        axes[k,1].set(title=arm,xlabel='Position error (km)',ylabel='Fraction of410 scans',xlim=(0,5));axes[k,1].legend(fontsize=8)
        axes[k,2].set(title=arm,ylabel='Original GLRT associated (%)',xticks=[0,1],xticklabels=['Incumbent','Completed candidate'],ylim=(69.9,70.3))
    for ax in axes.flat:ax.grid(axis='y',alpha=.2)
    fig.suptitle('Full DS23 · cached completed-candidate decision replay ·6 changed endpoints,404 exact fallbacks\nSame saved causal trials and matched c arms; this is not a new410-scan fitting campaign or ALGO release')
    save(fig,'full_DS23_summary.png')

    fig,axes=plt.subplots(2,2,figsize=(15,10),layout='constrained');names=[r['case'] for r in selected]
    for k,arm in enumerate(arms):
        rr=[next(r for r in changed if r['case']==case and r['arm']==arm) for case in names]
        for j,method in enumerate(methods):
            axes[k,0].bar(np.arange(6)+(j-.5)*.3,[r['original_error_km'] if j==0 else r['error_km'] for r in rr],width=.28,label=method,color=f'C{j}')
        bars=axes[k,1].bar(range(6),[1000*r['error_change_km'] for r in rr],color=['C2' if r['error_change_km']<0 else 'crimson' for r in rr]);axes[k,1].axhline(0,c='black')
        for bar,r in zip(bars,rr,strict=True):axes[k,1].text(bar.get_x()+bar.get_width()/2,1000*r['error_change_km'],f"{1000*r['error_change_km']:+.0f}m",ha='center',va='bottom' if r['error_change_km']>0 else 'top')
        axes[k,0].set(title=arm,ylabel='Position error (km)');axes[k,0].legend(fontsize=8);axes[k,1].set(title=arm,ylabel='New minus old error (m; negative improves)')
    for ax in axes.flat:ax.set_xticks(range(6),[n.replace('DS23-','') for n in names]);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Every changed scan ·4 improve,2 worsen in both c arms\n0234 worsens by about0.91km despite passing residual gates;0081 still has12.26km error')
    save(fig,'all_six_changed_cases.png')

    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for k,arm in enumerate(arms):
        for r in changed:
            if r['arm']!=arm:continue
            axes[k].scatter(r['associated_percent'],r['error_change_km'],s=55,c='C2' if r['error_change_km']<0 else 'crimson');axes[k].annotate(r['case'].replace('DS23-',''),(r['associated_percent'],r['error_change_km']),xytext=(5,5),textcoords='offset points')
        axes[k].axhline(0,c='black');axes[k].set(title=arm,xlabel='New original GLRT associated (%)',ylabel='Position error change (km)');axes[k].grid(alpha=.2)
    fig.suptitle('Higher association does not guarantee better localization\nAll six preserve every original associated measurement ID; no failed candidate is counted')
    save(fig,'association_and_accuracy.png')

    fig,axes=plt.subplots(2,1,figsize=(17,8),layout='constrained',sharex=True)
    for ax,arm in zip(axes,arms,strict=True):
        for j,method in enumerate(methods):
            rr=sorted([r for r in rows if r['arm']==arm and r['method']==method],key=lambda r:r['case']);ax.plot(range(410),[r['error_km'] for r in rr],'.-',ms=2,lw=.6,label=method)
        ax.set(ylabel=arm+' error (km)',yscale='symlog');ax.legend(fontsize=8);ax.grid(alpha=.2)
        for case in names:
            i=cases.index(case);ax.scatter(i,next(r['error_km'] for r in changed if r['arm']==arm and r['case']==case),c='C1',marker='s',s=26)
    axes[1].set_xticks(range(0,410,20),[cases[j].replace('DS23-','') for j in range(0,410,20)],rotation=60);axes[1].set_xlabel('DS23 scan · unavailable0012/0184/0286 not imputed')
    fig.suptitle('All410 available scans retained · cached decisions only · no new fits')
    save(fig,'all_scans.png')

    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for ax,metric in zip(axes,['mean','median'],strict=True):
        for k,arm in enumerate(arms):
            for j,u in enumerate([r for r in uncertainty if r['arm']==arm]):
                lo,hi=np.asarray(u[metric+'_change95_km'])*1000;y=k*4+j;ax.plot([lo,hi],[y,y],lw=4,c=f'C{k}');ax.scatter([lo,hi],[y,y],c=f'C{k}',s=15)
        ax.axvline(0,c='black');ax.set(title=metric+' change',xlabel='New minus old error (m)',yticks=[0,1,2,4,5,6],yticklabels=['c0:1h','c0:3h','c0:6h','fit:1h','fit:3h','fit:6h']);ax.grid(alpha=.2)
    fig.suptitle('Whole UTC time-block bootstrap ·5000 draws, seed2026102313 · descriptive only\nSame site after extensive development; these are not new-location confidence intervals')
    save(fig,'temporal_uncertainty.png')

    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained');fmts=sorted({r['recording_format'] for r in formats})
    for k,arm in enumerate(arms):
        for m,key in enumerate(['mean_error_km','median_error_km']):
            for j,method in enumerate(methods):
                rr=[next(r for r in formats if r['arm']==arm and r['recording_format']==fmt and r['method']==method) for fmt in fmts];axes[k,m].bar(np.arange(len(fmts))+(j-.5)*.3,[r[key] for r in rr],width=.28,label=method)
            axes[k,m].set(title=arm+' '+key.replace('_',' '),ylabel='Position error (km)',xticks=range(len(fmts)),xticklabels=[f"{fmt}\nn={next(r['cases'] for r in formats if r['recording_format']==fmt)}" for fmt in fmts]);axes[k,m].grid(axis='y',alpha=.2);axes[k,m].legend(fontsize=7)
    fig.suptitle('Matched full-population breakdown by recording format · no exclusions or GPS-based policy choice')
    save(fig,'recording_formats.png')

    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained');counts=Counter(r['status'] for r in inventory['rows']);axes[0].bar(range(len(counts)),list(counts.values()),color=['C0','C1']);axes[0].set(xticks=range(len(counts)),xticklabels=list(counts),ylabel='Available scans')
    for j,v in enumerate(counts.values()):axes[0].text(j,v+3,str(v),ha='center')
    axes[1].bar(range(4),[410,24,6,6],color=['C0','C1','C2','C2']);axes[1].set(xticks=range(4),xticklabels=['Inventory','Deadline hit','Completed, same\nRF context','Fresh audits pass'],ylabel='Scans')
    for j,v in enumerate([410,24,6,6]):axes[1].text(j,v+3,str(v),ha='center')
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle('Candidate omission is a deadline-return behavior ·12 matched endpoint arms independently replay\nA valid candidate is not proof of correct identity or good position')
    save(fig,'deadline_inventory.png')

    # Preserve all raw audit/evaluation records and the six exact saved candidates.
    archive=OUT/'evidence/raw_and_completed_candidates.tar.gz';manifest=[]
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(study.OUT.rglob('*')):
            if p.is_file() and p.suffix in ['.json','.csv']:
                name='deadline_inventory/'+str(p.relative_to(study.OUT));tar.add(p,arcname=name,recursive=False);manifest.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size))
        for r in selected:
            p=study.SOURCE/'reentry'/(r['case']+'.json');name='saved_reentry/'+p.name;tar.add(p,arcname=name,recursive=False);manifest.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size))
        for p in [study.SOURCE/'protocol.json',study.reference.AUTHORITY,OLD_QUAL,DEFAULT_RUN/'sample.json']:
            name='provenance/'+str(p.relative_to(ROOT));tar.add(p,arcname=name,recursive=False);manifest.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size))
    assert archive.stat().st_size<45*1024**2
    write(OUT/'evidence/archive_manifest.json',dict(file=str(archive.relative_to(OUT)),bytes=archive.stat().st_size,sha256=sha(archive),members=manifest))
    for name in ['inventory_ds23_completed_deadline_candidates.py','audit_ds23_completed_deadline_candidates.py','evaluate_ds23_completed_deadline_candidates.py',Path(__file__).name,'analyze_ds23_paired_evidence_population.py','probe_ds23_owner_reentry.py','audit_ds23_archived_qualification.py']:
        shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    shutil.copyfile(ROOT/'tests/analysis/test_ds23_completed_deadline_inventory.py',OUT/'source/tests/test_ds23_completed_deadline_inventory.py')
    csv_write(OUT/'tables/qualification_summary.csv',quals)
    write(OUT/'evidence/report_checks.json',dict(all410included=True,canonical_baseline_reproduced=True,all6fresh_replays_passed=True,
        changed_cases=[r['case'] for r in selected],endpoint_arms=12,additional_curved_points=sum(r['new_curved_points'] for r in offers),
        additional_associated_points_each_arm=729,original_associated_IDs_lost=0,source_hashes={str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')},
        original_search_budget_s=400,no_new_fit_or_GPS_selected_decision=True,no_new_ALGO_release=True,
        qualification_summary=quals,format_summary=formats,temporal_bootstrap=uncertainty,
        uncertainty_descriptive_after_extensive_same_site_development=True))
    print('Deadline report',len(list((OUT/'figures').glob('*.png'))),'figures',len(list((OUT/'tables').glob('*.csv'))),'tables',archive.stat().st_size,'archive bytes',flush=True)
    print('Format summaries',formats,flush=True);print('Uncertainty',uncertainty,flush=True)


if __name__=='__main__':main()
