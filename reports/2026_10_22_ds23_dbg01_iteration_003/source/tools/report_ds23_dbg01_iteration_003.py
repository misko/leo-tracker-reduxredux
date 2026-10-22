"""Report frozen iteration003 outcomes; all geographic scoring is report-only."""

import csv
from pathlib import Path
import shutil
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_003 as runner
import run_ds23_dbg01_iteration_002 as iteration
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_002 as curves
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT, read, write, sha

RAW = runner.RAW
OUT = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_003'


def result_row(case, method, arm, fit, inventory, original):
    lost = set(original['accepted_observation_ids'])-set(inventory['accepted_observation_ids'])
    used = int(fit['active_points']+fit.get('predictive_points', inventory['predictive_points']))
    return dict(case=case,method=method,arm=arm,
        associated_points=inventory['associated'],all_GLRT=inventory['total_GLRT'],
        associated_percent=inventory['percent'],
        associated_graph_fragments=inventory['associated_tracks'],
        points_per_associated_fragment=inventory['associated']/inventory['associated_tracks'],
        curved_position_points=fit['active_points'],predictive_position_points=fit.get('predictive_points',inventory['predictive_points']),
        total_points_in_position=used,associated_but_not_used=inventory['associated']-used,
        position_error_km=position_error(fit['endpoint_latlon']),RMS_hz=fit['RMS_hz'],
        original_accepted_points_lost=len(lost),selected_by_GPS=False)


def overview(rows,ceilings):
    cases=list(ceilings)
    methods=['Published incumbent','Unrestricted curve growth','Family-predictive guard']
    colors=['tab:blue','tab:orange','tab:green']
    fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
    for k,case in enumerate(cases):
        for j,(method,color) in enumerate(zip(methods,colors,strict=True)):
            r=next(r for r in rows if r['case']==case and r['method']==method and r['arm']=='fitted_c')
            x=k+(j-1)*.25
            axes[0].bar(x,r['associated_percent'],width=.23,color=color,label=method if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.23,color=color)
            axes[0].text(x,r['associated_percent']+1,f"{r['associated_percent']:.1f}",ha='center',fontsize=8)
            axes[1].text(x,r['position_error_km']+.08,f"{r['position_error_km']:.2f}",ha='center',fontsize=8)
        axes[2].bar(k,ceilings[case]['percent'],color='0.55')
        axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.1f}%",ha='center')
    axes[0].axhline(90,c='crimson',ls='--');axes[2].axhline(90,c='crimson',ls='--')
    axes[1].axhline(.5,c='green',ls='--');axes[0].legend(fontsize=7)
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100))
    axes[1].set(ylabel='Position error (km)')
    axes[2].set(ylabel='Maximum coverage using current graph (%)',ylim=(0,100))
    for ax in axes:ax.set_xticks(range(len(cases)),cases);ax.grid(axis='y',alpha=.2)
    fig.suptitle('DBG01 iteration 003 · inspected development cases · fitted c\n'
                 '0390: more passing associations worsen position; guard is an engineering hypothesis')
    fig.savefig(OUT/'figures/iteration_summary.png',dpi=160);plt.close(fig)


def predictive_figures(cases):
    rows=[]
    fig,axes=plt.subplots(len(cases),2,figsize=(14,4*len(cases)),layout='constrained',squeeze=False)
    for k,case in enumerate(cases):
        d=read(RAW/'family_predictive_guard'/(case+'_selection.json'))
        rows.extend(dict(case=case,**r) for r in d['rows'])
        for ax,arm in zip(axes[k],['c0','fitted_c'],strict=True):
            selected=[r for r in d['rows'] if r['arm']==arm];gain=[r['gain'] for r in selected]
            ax.bar(range(len(gain)),gain,color=['tab:green' if g>=0 else 'crimson' for g in gain])
            ax.set_xticks(range(len(gain)),[str(r['norad']) for r in selected],rotation=65,fontsize=8)
            s=d['summary'][arm]
            ax.axhline(0,c='black',lw=.7);ax.set_yscale('symlog',linthresh=.02)
            ax.set(title=f"{case} {arm} · {'adopt' if d['adopted'] else 'keep incumbent'}\n"
                   f"sum={s['sum_gain']:.3f}; median={s['median_gain']:+.4f}; {s['families_improved']}/{len(gain)} improve",
                   ylabel='Old minus expanded predictive score');ax.grid(axis='y',alpha=.2)
    fig.suptitle('Temporary original-family folds · original held IDs identical in both variants\n'
                 'Positive predicts that family better; new same-family curve stays in training; final fit uses all points')
    fig.savefig(OUT/'figures/family_predictive_consistency.png',dpi=160);plt.close(fig)
    return rows


def orbit_support_figures(cases):
    rows=[]
    for case in cases:
        for r in read(RAW/'orbit_support_diagnostic'/(case+'.json'))['rows']:
            rows.append(dict(case=case,component=r['component'],norad=r['norad'],points=r['points'],
                actual_curved_owners=r['actual_curved_owners'],
                original_RMS_hz=r['current_prediction']['conditional_RMS_hz'],
                counterfactual_RMS_hz=r['counterfactual_prediction']['conditional_RMS_hz'],
                maximum_curvature_information=max(r['physical_prior_curvature_information_eigenvalues']),
                prior_scaled_coefficient_norm=r['physical_coefficient_norm'],
                independently_replayed_density_difference=r['independent_density_difference']))
    fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained')
    names=[r['case'].replace('DS23-','')+' '+r['component'].split('-RF')[0].split('RX')[-1] for r in rows]
    y=np.arange(len(rows))
    axes[0].barh(y-.16,[r['original_RMS_hz'] for r in rows],height=.3,label='Original support rule')
    axes[0].barh(y+.16,[r['counterfactual_RMS_hz'] for r in rows],height=.3,label='Enable existing physical modes')
    axes[1].barh(y,[r['maximum_curvature_information'] for r in rows],color='tab:purple')
    axes[1].axvline(1,c='gray',ls='--',label='Unit prior-scale information')
    axes[0].set(xlabel='Conditional predictive RMS (Hz)');axes[0].legend(fontsize=8)
    axes[1].set(xscale='log',xlabel='Largest non-affine information eigenvalue');axes[1].legend(fontsize=8)
    for ax in axes:ax.set_yticks(y,names);ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
    fig.suptitle('Diagnostic only: existing three physical orbit modes add little measurable curvature\n'
                 'Causal catalogue, original prior scales and original receiver calibration; no final support gate relaxed')
    fig.savefig(OUT/'figures/physical_orbit_support.png',dpi=160);plt.close(fig)
    return rows


def shared_family_context(case,data,proposal):
    dd,arms=curves.baseline_or_trial(data,proposal)
    fit=arms['fitted_c'];p=iteration.baseline.build(dd,'fitted_c',fit['phase_reference'])
    residual=p.calculate(np.asarray(fit['endpoint_east_north_km']))['conditional_residual_hz']
    target=proposal['additions'][0]['norad'];added={a['component'] for a in proposal['additions']}
    fig,axes=plt.subplots(2,2,figsize=(14,8),layout='constrained')
    by_id={o['observation_id']:o for o in data['observations']};table=[]
    family_color=0
    for k,(r,sl) in enumerate(zip(p.rows,p.slices,strict=True)):
        if r['candidate_norad']!=target or not dd['keep'][sl].any():continue
        track=data['scan'].tracks[p.members[k]];times,raw=curves.raw_track_values(track,range(len(track['times'])),by_id)
        name=r['component'].split('-RF')[0].replace(case+'-','')
        color='crimson' if r['component'] in added else ['tab:blue','tab:green','tab:purple','tab:orange'][family_color%4]
        if r['component'] not in added:family_color+=1
        ax=axes[0,0] if track['channel']==4 else axes[0,1]
        ax.scatter(times,raw/1000,s=12,c=[color],label=name+(' proposed' if r['component'] in added else ' original'))
        for run in curves.native_runs(times,raw,track['values']):ax.plot(times[run],(raw-residual[sl])[run]/1000,c=color,lw=1)
        axes[1,0].plot(times,residual[sl],'.-',c=color,label=name)
        table.append(dict(case=case,component=r['component'],norad=target,proposed=r['component'] in added,
            receiver=track['receiver'],channel=track['channel'],points=len(times),start_s=min(times),end_s=max(times),
            RMS_hz=float(np.sqrt(np.mean(residual[sl]**2)))))
    axes[0,0].set(title='RX1 CH4; original + proposed curve',ylabel='Raw GLRT CFO (kHz)')
    axes[0,1].set(title='Original RX1 CH1 / CH2 evidence',ylabel='Raw GLRT CFO (kHz)')
    axes[1,0].set(title='Expanded fit; all displayed original gates pass',ylabel='Conditional residual (Hz)')
    for ax in [axes[0,0],axes[0,1],axes[1,0]]:ax.set_xlabel('Device time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    axes[1,0].axhline(0,c='black',lw=.6)
    selection=read(RAW/'family_predictive_guard'/(case+'_selection.json'))
    gain=[r for r in selection['rows'] if r['arm']=='fitted_c']
    axes[1,1].bar(range(len(gain)),[r['gain'] for r in gain],color=['tab:orange' if r['norad']==target else '0.5' for r in gain])
    axes[1,1].set_xticks(range(len(gain)),[str(r['norad']) for r in gain],rotation=65,fontsize=8)
    axes[1,1].set(ylabel='Old minus expanded predictive score',title=f'Own family improves; most other families worsen')
    axes[1,1].grid(axis='y',alpha=.2)
    fig.suptitle(f'{case} · hypothesis {target} · all displayed evidence is RX1\n'
                 'Same-family agreement can coexist with a worse position; identity is not established by these residuals')
    fig.savefig(OUT/'figures'/(case+'_shared_family_context.png'),dpi=160);plt.close(fig)
    return table


def main():
    runner.configure();curves.RAW=RAW;curves.OUT=OUT
    figures.OUT,figures.RAW=OUT,RAW
    figures.REENTRY,figures.SUPPORT=RAW/'single_curve_reentry',RAW/'support_aware_reentry'
    figures.setup=iteration.current_setup
    for name in ['figures','tables','evidence','source/tools','source/tests']:(OUT/name).mkdir(parents=True,exist_ok=True)
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    for part in ['all_curve_families/audit_execution.json','family_predictive_guard/folds_execution.json',
                 'family_predictive_guard/selection.json','curve_diagnostics/execution.json','orbit_support_diagnostic/execution.json']:
        assert read(RAW/part)['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];families=[];controls=[];diagnostics=[];failures=[];residuals=[];ceilings={};context=[]
    for case in cases:
        data=iteration.current_setup(case);baseline=read(RAW/case/'inventory.json')['arms']
        proposal=read(RAW/'all_curve_families'/(case+'_positions.json'))['selected']
        expanded=read(RAW/'all_curve_families'/(case+'_audit.json'))['coverage']
        selection=read(RAW/'family_predictive_guard'/(case+'_selection.json'))
        final=proposal if selection['adopted'] else None
        _,expanded_arms=curves.baseline_or_trial(data,proposal)
        _,guarded_arms=curves.baseline_or_trial(data,final)
        guarded=expanded if selection['adopted'] else baseline
        n=baseline['fitted_c']['total_GLRT'];graph=n-baseline['fitted_c']['outside_graph_points']
        ceilings[case]=dict(points=graph,percent=100*graph/n,
            minimum_outside_graph_points_needed_for90=max(0,int(np.ceil(.9*n))-graph))
        for label,arms,coverage,prefix in [('Published incumbent',data['arms'],baseline,'published'),
            ('Unrestricted curve growth',expanded_arms,expanded,'growth'),
            ('Family-predictive guard',guarded_arms,guarded,'guarded')]:
            for arm,fit in arms.items():rows.append(result_row(case,label,arm,fit,coverage[arm],baseline[arm]))
            for associated in [True,False]:figures.glrt_figure(data,coverage['fitted_c'],prefix,associated)
        families.extend(figures.family_rows(case,data))
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case))
        diagnostics.extend(curves.candidate_diagnostics(case,data));curves.recovered_curves(case,data,proposal)
        residuals.extend(figures.residual_figures(case,data,dict(baseline_arms=data['arms'],policy_arms=expanded_arms,selected=proposal),None))
        if case=='DS23-0390':context.extend(shared_family_context(case,data,proposal))
        for stage in ['single_curve_reentry','all_curve_families']:
            for trial in read(RAW/stage/(case+'_positions.json'))['trials']:
                for arm,fit in trial['arms'].items():
                    failures.append(dict(case=case,stage=stage,arm=arm,
                        additions=str([(a['component'],a['norad']) for a in trial['additions']]),paired_valid=trial['paired_valid'],
                        failing_curved=str([g for g in fit['gates']['tracks'] if not g['compatible']]),
                        failing_predictive=str([g for g in fit['linear_gates'] if not g['compatible']])))
    for name,records in [('position_and_association',rows),('family_ablations',families),('all_interventions',controls),
        ('residual_diagnostics',residuals),('following_TLE_profiles',diagnostics),('trial_gates',failures),
        ('family_predictive_scores',predictive_figures(cases)),('orbit_support',orbit_support_figures(cases)),
        ('shared_family_context',context)]:figures.csv_write(OUT/'tables'/(name+'.csv'),records)
    overview(rows,ceilings)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,graph_ceilings=ceilings,
        no_full_DS23_accuracy_claim=True,no_new_ALGO_release=True,geographic_scoring_after_RF_selection=True))
    for source in ['protocol.json','independent_iteration_audit.json','RF_restart_selection.json',
        'family_predictive_guard/protocol.json','family_predictive_guard/selection.json',
        'all_curve_families/protocol.json','all_curve_families/audit_execution.json']:
        shutil.copyfile(RAW/source,OUT/'evidence'/source.replace('/','_'))
    # Preserve every JSON/CSV scientific receipt, including all starts and folds,
    # compactly; generated PNGs/logs are not inference inputs and are excluded.
    with tarfile.open(OUT/'evidence/raw_scientific_receipts.tar.gz','w:gz') as archive:
        for p in sorted(RAW.rglob('*')):
            if p.is_file() and p.suffix in ['.json','.csv']:archive.add(p,arcname=str(p.relative_to(RAW)),recursive=False)
    names=['run_ds23_dbg01_iteration_003.py','run_ds23_dbg01_iteration_002.py','ds23_current_assignment_context.py',
        'probe_ds23_all_curve_families.py','probe_ds23_family_predictive_guard.py',
        'diagnose_ds23_dbg01_orbit_support.py','diagnose_ds23_iteration002_curves.py',
        'confirm_ds23_curve_predictive_guard.py',Path(__file__).name]
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_dbg01_iteration_003.py','test_ds23_all_curve_families.py','test_ds23_family_predictive_guard.py',
        'test_ds23_orbit_support_diagnostic.py','test_ds23_curve_guard_confirmation.py','test_report_ds23_dbg01_iteration_003.py']:
        shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    print('Iteration003 figures and tables generated',OUT,flush=True)


if __name__=='__main__':main()
