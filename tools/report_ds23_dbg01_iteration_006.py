"""Report the next bounded ALGO02/03 batch and saved-population qualification."""

from pathlib import Path
import shutil
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_006 as runner
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_002 as curves
import report_ds23_dbg01_iteration_004 as coverage_helper
import probe_ds23_supported_feasibility as feasible
from report_ds23_dbg01_iteration_005 import result_row
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write

RAW=runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_006'


def archives(cases):
    files=[p for p in RAW.rglob('*') if p.is_file() and p.suffix in ['.json','.csv','.py']]
    groups={'shared':[]}
    for case in cases:
        for part in ['restarts','other']:groups[case+'_'+part]=[]
    for p in files:
        name=str(p.relative_to(RAW));matched=next((c for c in cases if c in name),None)
        group='shared' if matched is None else matched+('_restarts' if '/DBG01/restart_' in name else '_other')
        groups[group].append(p)
    for group,paths in groups.items():
        with tarfile.open(OUT/'evidence'/('raw_'+group+'.tar.gz'),'w:gz') as archive:
            for p in sorted(paths):archive.add(p,arcname=str(p.relative_to(RAW)),recursive=False)


def confirmation():
    root=RAW/'feasibility_confirmation_disjoint'
    assert read(root/'execution.json')['all_terminal']
    cases=read(root/'protocol_v3.json')['cases'];choices={};rows=[]
    for case in cases:
        controls=[t for t in read(root/'support_aware_reentry'/(case+'.json'))['trials'] if t['paired_valid']]
        old=max(controls,key=lambda t:t['added_curved_points']) if controls else None
        new=read(root/'supported_feasibility'/(case+'.json'))['selected']
        selected=new if new is not None and (old is None or new['added_curved_points']>old['added_curved_points']) else old
        choices[case]=dict(control=old,refined=selected)
    write(root/'RF_policy_selection.json',dict(choices=choices,rule='maximum passing new points, ties keep unconstrained support control; no extra union',
        sealed_before_geographic_scoring=True,development0069_and0291_excluded=True))
    for case in cases:
        d=runner.engine.current_setup(case);original=read(root/case/'inventory.json')['arms']
        for method,selected in [('Published incumbent',None),('Supported mode control',choices[case]['control']),('Supported feasibility',choices[case]['refined'])]:
            if selected is None:arms,cov=d['arms'],original
            else:_,arms,cov=coverage_helper.residual_and_coverage(d,selected,'support')
            for arm,r in arms.items():rows.append(result_row(case,method,arm,r,cov[arm],original[arm]))
    summaries=[]
    for arm in ['c0','fitted_c']:
        for method in ['Published incumbent','Supported mode control','Supported feasibility']:
            group=[r for r in rows if r['arm']==arm and r['method']==method];errors=[r['position_error_km'] for r in group]
            total=sum(r['all_GLRT'] for r in group);associated=sum(r['associated_points'] for r in group)
            summaries.append(dict(arm=arm,method=method,cases=len(group),mean_error_km=float(np.mean(errors)),median_error_km=float(np.median(errors)),
                p90_error_km=float(np.quantile(errors,.9)),associated_points=associated,total_GLRT=total,associated_percent=100*associated/total,
                mean_frequency_RMS_hz=float(np.mean([r['RMS_hz'] for r in group]))))
    fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained')
    for method in ['Published incumbent','Supported mode control','Supported feasibility']:
        group=[next(r for r in rows if r['case']==c and r['arm']=='fitted_c' and r['method']==method) for c in cases]
        axes[0].plot(range(len(cases)),[r['position_error_km'] for r in group],'.-',label=method)
        axes[1].scatter([r['associated_percent'] for r in group],[r['position_error_km'] for r in group],s=25,label=method)
    axes[0].set_xticks(range(len(cases)),[c.replace('DS23-','') for c in cases],rotation=65);axes[0].set(ylabel='Position error (km)',xlabel='Frozen confirmation scan');axes[0].legend(fontsize=8)
    axes[1].set(ylabel='Position error (km)',xlabel='Original GLRT associated (%)')
    for ax in axes:ax.grid(alpha=.2);ax.axhline(.5,c='gray',ls='--')
    fig.suptitle('19 scan-disjoint confirmation cases · fitted c · original frozen nominations\nPreviously studied same site; no new-location or full-DS23 improvement claim')
    fig.savefig(OUT/'figures/feasibility_confirmation19.png',dpi=160);plt.close(fig)
    figures.csv_write(OUT/'tables/confirmation19_positions.csv',rows);figures.csv_write(OUT/'tables/confirmation19_summary.csv',summaries)
    write(OUT/'evidence/confirmation19_evaluation.json',dict(rows=rows,summary=summaries,RF_selection_sealed_before_geographic_scoring=True))
    print('Confirmation summary',summaries,flush=True)


def qualifications():
    record=read(RAW/'archived_qualification/v2/audit.json')
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for arm in ['c0','fitted_c']:
        rows=[r for r in record['rows'] if r['arm']==arm];x=np.sort([r['maximum_absolute_phase_s'] for r in rows])
        axes[0].plot(x,np.arange(1,len(x)+1)/len(x),label=arm)
    axes[0].axvline(15,c='crimson',ls='--');axes[0].set(xlabel='Maximum absolute saved posterior phase (s)',ylabel='Fraction of410 scans');axes[0].legend();axes[0].grid(alpha=.2)
    for k,row in enumerate(record['summary']):
        axes[1].bar(k,row['qualified'],label='Pass' if k==0 else None,color='tab:blue')
        axes[1].bar(k,410-row['qualified'],bottom=row['qualified'],color='crimson',label='Fail phase' if k==0 else None)
        axes[1].text(k,390,f"{row['qualified']}/410",ha='center',c='white')
    axes[1].set_xticks([0,1],['c0','fitted_c']);axes[1].set(ylabel='Saved endpoints',ylim=(0,420));axes[1].legend(fontsize=8)
    fig.suptitle('Archived full DS23 qualification · saved metadata audit, no refit or fresh numerical replay\nOnly0068 fails the strict15s phase gate in either arm; all410 outputs retained in accuracy metrics')
    fig.savefig(OUT/'figures/full_DS23_qualification.png',dpi=160);plt.close(fig)
    figures.csv_write(OUT/'tables/archived_qualification.csv',record['rows'])
    figures.csv_write(OUT/'tables/archived_qualification_summary.csv',record['summary'])


def constrained_trials(cases):
    rows=[];records=[]
    for case in cases:
        record=read(feasible.OUT/(case+'.json'));initial=read(RAW/'support_aware_reentry'/(case+'.json'))
        for i,t in enumerate(record['trials']):
            for arm,r in t['arms'].items():
                rows.append(dict(case=case,trial=i,arm=arm,added_points=t['added_curved_points'],
                    paired_valid=t['paired_valid'],position_error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],
                    minimum_constraint_slack=r.get('minimum_constraint_slack'),final_phase_change_s=r['final_phase_change_s'],
                    negative_twice_elbo=r['negative_twice_elbo'],components=[a['component'] for a in t['additions']]))
        for t in initial['trials']:
            after=next((r for r in record['trials'] if r['additions']==t['additions']),None)
            for arm,r in t['arms'].items():
                for g in r['gates']['tracks']:
                    if g['component'] not in {a['component'] for a in t['additions']}:continue
                    changed=next((v for v in after['arms'][arm]['gates']['tracks'] if v['component']==g['component']),None) if after else None
                    records.append(dict(case=case,arm=arm,component=g['component'],norad=g['norad'],
                        before_quadratic_bic=g['conditional_residual_gate']['diagnostics']['quadratic_bic_gain'],
                        after_quadratic_bic=changed['conditional_residual_gate']['diagnostics']['quadratic_bic_gain'] if changed else None,
                        before_rms_hz=g['conditional_residual_gate']['rms_hz'],after_rms_hz=changed['conditional_residual_gate']['rms_hz'] if changed else None,
                        paired_trial_valid=after['paired_valid'] if after else False))
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    shown=[r for r in records if r['case']=='DS23-0291' and r['arm']=='fitted_c']
    for k,r in enumerate(shown):
        for ax,before,after in [(axes[0],r['before_quadratic_bic'],r['after_quadratic_bic']),
                                (axes[1],r['before_rms_hz'],r['after_rms_hz'])]:
            ax.scatter(k-.08,before,c='tab:blue',s=50,label='Unconstrained' if k==0 else None)
            if after is not None:ax.scatter(k+.08,after,c='tab:orange',s=50,marker='o' if r['paired_trial_valid'] else 'x',label='Constrained' if k==0 else None)
    axes[0].axhline(10,c='crimson',ls='--');axes[1].axhline(450,c='crimson',ls='--')
    axes[0].set(ylabel='Conditional quadratic BIC gain');axes[1].set(ylabel='Conditional RMS (Hz)')
    for ax in axes:ax.set_xticks(range(len(shown)),[str(r['norad']) for r in shown]);ax.set_xlabel('Frozen satellite hypothesis');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('0291 · same supported-mode model and whole observations · fitted c\nOriginal gates enforced in bounded optimization; markers do not establish satellite ground truth')
    fig.savefig(OUT/'figures/supported_feasibility_gates.png',dpi=160);plt.close(fig)
    if rows:figures.csv_write(OUT/'tables/constrained_trials.csv',rows)
    figures.csv_write(OUT/'tables/constrained_gate_comparison.csv',records)


def overview(rows,ceilings):
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,method in enumerate(['Published incumbent','Supported feasibility policy']):
            r=next(r for r in rows if r['case']==case and r['method']==method and r['arm']=='fitted_c');x=k+(j-.5)*.25
            for ax,value in [(axes[0],r['associated_percent']),(axes[1],r['position_error_km'])]:
                ax.bar(x,value,width=.23,color=f'C{j}',label=method if k==0 else None);ax.text(x,value+.1,f'{value:.2f}',ha='center',fontsize=8)
        axes[2].bar(k,ceilings[case]['percent'],color='0.6');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].legend(fontsize=8);axes[0].axhline(90,c='crimson',ls='--')
    axes[1].set(ylabel='Position error (km)');axes[1].axhline(.5,c='green',ls='--');axes[2].set(ylabel='Original graph ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(len(ceilings)),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('DBG01 iteration006 · bounded supported-mode feasibility control · fitted c\nNo new ALGO release or full-DS23 accuracy gain claimed')
    fig.savefig(OUT/'figures/iteration_summary.png',dpi=160);plt.close(fig)


def main():
    runner.configure();curves.RAW=RAW;curves.OUT=OUT;coverage_helper.RAW=RAW
    figures.OUT,figures.RAW=OUT,RAW;figures.REENTRY=RAW/'single_curve_reentry';figures.SUPPORT=RAW/'support_aware_reentry';figures.setup=runner.engine.current_setup
    for part in ['figures','tables','evidence','source/tools','source/tests']:(OUT/part).mkdir(parents=True,exist_ok=True)
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    assert read(feasible.OUT/'execution.json')['all_terminal']
    cases=read(RAW/'protocol.json')['cases'];rows=[];controls=[];families=[];residuals=[];diagnostics=[];ceilings={}
    for case in cases:
        d=runner.engine.current_setup(case);original=read(RAW/case/'inventory.json')['arms'];repair=read(feasible.OUT/(case+'.json'))['selected']
        _,arms,cov=coverage_helper.residual_and_coverage(d,repair,'support')
        n=len(d['observations']);g=n-original['fitted_c']['outside_graph_points'];ceilings[case]=dict(points=g,percent=100*g/n,minimum_outside_graph_for90=max(0,int(np.ceil(.9*n))-g))
        for method,pair,coverage,prefix in [('Published incumbent',d['arms'],original,'published'),('Supported feasibility policy',arms,cov,'feasible_policy')]:
            for arm,r in pair.items():rows.append(result_row(case,method,arm,r,coverage[arm],original[arm]))
            for associated in [True,False]:figures.glrt_figure(d,coverage['fitted_c'],prefix,associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));families.extend(figures.family_rows(case,d))
        residuals.extend(figures.residual_figures(case,d,dict(baseline_arms=d['arms'],policy_arms=arms,selected=repair),None))
        diagnostics.extend(curves.candidate_diagnostics(case,d))
        if repair:
            original_build=runner.engine.baseline.build
            runner.engine.baseline.build=lambda changed,arm,reference:runner.engine.support.build(d,changed['node'],changed['keep'],arm,reference,changed['means'])
            try:curves.recovered_curves(case,d,repair)
            finally:runner.engine.baseline.build=original_build
    overview(rows,ceilings);qualifications();constrained_trials(cases);confirmation()
    for name,records in [('position_and_association',rows),('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('following_TLE_profiles',diagnostics)]:figures.csv_write(OUT/'tables'/(name+'.csv'),records)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,graph_ceilings=ceilings,no_ALGO_release_or_full_DS23_gain_claimed=True))
    archives(cases)
    for name in ['run_ds23_dbg01_iteration_006.py','run_ds23_dbg01_iteration_002.py','ds23_current_assignment_context.py',
        'probe_ds23_supported_feasibility.py','confirm_ds23_supported_feasibility.py',
        'audit_ds23_archived_qualification.py',Path(__file__).name]:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_dbg01_iteration_006.py','test_ds23_archived_qualification.py','test_ds23_supported_feasibility.py']:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    print('Iteration006 report assets generated',flush=True)


if __name__=='__main__':main()
