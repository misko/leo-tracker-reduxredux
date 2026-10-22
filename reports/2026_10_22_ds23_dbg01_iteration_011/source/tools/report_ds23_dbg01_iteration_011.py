"""Report frozen paired evidence and bounded native-path recovery; no inference."""

from pathlib import Path
import csv
import re
import shutil
import tarfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_011 as runner
import probe_ds23_iteration011_parent_choice as parents
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_007 as diagnostics
import report_ds23_dbg01_iteration_008 as path_figures
import report_ds23_dbg01_iteration_009 as restarts
from report_ds23_dbg01_iteration_005 import result_row
from evaluate_ds23_iteration010_short_confirmation import reported_fit
from ds23_receiver_curve_consistency import shared_shape
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error

RAW=runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_011'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def gallery():
    lines=['# Iteration011 figure inventory','',
        'All figures describe frozen results; GPS appears only for evaluation.','']
    for path in sorted((OUT/'figures').glob('*.png')):
        label=path.stem.replace('_',' ')
        lines.extend([f'## {label}','',f'![{label}](figures/{path.name})',''])
    (OUT/'FIGURES.md').write_text('\n'.join(lines))


def temporal_view(case,d,cov,kind,folder):
    record=read(RAW/folder/(case+'.json'))['methods']['persistent5s']
    if not record['accepted']:return d,cov,record
    selected=read(RAW/folder/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=parents.paths.native.append_native_paths(d['scan'],d['entries'],selected,parents.paths.native.receiver_basis(d['scan']))
    return dict(d,scan=scan,entries=entries,arms=record['arms']),record['coverage'],record


def overview(rows,ceilings):
    methods=['Incumbent','Default graph','RF graph parent','Default temporal policy','RF-parent temporal policy']
    fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,method in enumerate(methods):
            r=next(r for r in rows if r['case']==case and r['method']==method and r['arm']=='fitted_c');x=k+(j-2)*.15
            axes[0].bar(x,r['associated_percent'],width=.145,color=f'C{j}',label=method if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.145,color=f'C{j}')
            axes[1].text(x,r['position_error_km']+.04,f"{r['position_error_km']:.3f}",ha='center',fontsize=7,rotation=45)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--');axes[0].legend(fontsize=7,loc='lower left')
    axes[1].set(ylabel='Position error (km)',ylim=(0,4));axes[1].axhline(.5,c='green',ls='--')
    axes[2].set(ylabel='Original graph-only ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('Iteration011 · bounded development · fitted c · no new ALGO release\nTemporal policies retain graph parent if either arm fails. Parent choice uses identical-mask RF evidence')
    save(fig,'iteration_summary.png')


def gate_rows(case,method,trial):
    rows=[]
    for arm,r in trial['arms'].items():
        for g in r['gates']['tracks']:
            q=g['conditional_residual_gate'];a=q.get('raw_diagnostics',q['diagnostics'])
            rows.append(dict(case=case,method=method,arm=arm,paired_valid=trial['paired_valid'],component=g['component'],
                norad=g['norad'],points=g['points'],compatible=g['compatible'],RMS_hz=q['rms_hz'],
                mean_z=a['mean_z'],slope_z=a['slope_z'],quadratic_BIC_gain=a['quadratic_bic_gain'],
                maximum_step_z=a['maximum_step_z'],lag1_ACF=a['lag1_acf'],ACF_limit=4/np.sqrt(g['points'])))
    return rows


def shapes(d):
    targets=read(RAW/'single_curve_reentry/DS23-0163_nominations.json')['targets']
    tracks=[d['scan'].tracks[r['target']['track_index']] for r in targets]
    comparisons={name:shared_shape(tracks,overlap_only=overlap) for name,overlap in [('whole_sources',False),('actual_overlap',True)]}
    write(OUT/'evidence/0163_shared_curvature.json',comparisons)
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained');rows=[]
    for col,(name,r) in enumerate(comparisons.items()):
        for group in [0,1]:
            ix=r['groups']==group
            # Remove each group's affine fit for a view of measured curvature.
            t=r['times'][ix];y=r['values_hz'][ix];z=(t-r['reference_s'])/r['time_scale_s']
            a=np.column_stack((np.ones(len(t)),z));v=y-a@np.linalg.lstsq(a,y,rcond=None)[0]
            axes[0,col].plot(t,v,'.-',label=f"CH{tracks[group]['channel']}: {len(t)} points")
        best=r['best'];axes[0,col].set(title=name.replace('_',' '),ylabel='RF-normalized CFO minus own affine (Hz)')
        for method in ['shared','independent']:
            fit=best[method];axes[1,col].plot(r['times'],fit['residual_hz'],'.',label=f"{method} d{fit['degree']}: {fit['RMS_hz']:.1f}Hz")
        axes[1,col].axhline(0,c='gray');axes[1,col].set(ylabel='Model residual (Hz)',title=f"BIC shared − independent = {r['BIC_shared_minus_independent']:+.2f}")
        for fit in r['rows']:rows.append(dict(population=name,points=len(r['times']),method=fit['method'],degree=fit['degree'],parameters=fit['parameters'],RMS_hz=fit['RMS_hz'],BIC=fit['BIC']))
    for ax in axes.flat:ax.set_xlabel('Scan time (s)');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('DS23-0163 · two same-RX sources nominated58629 · no GPS/TLE used in this comparison\nActual overlap favors separate curvature. A shared whole-window polynomial can hide local incompatibility')
    save(fig,'DS23-0163_shared_curvature.png');return rows


def population():
    folder=RAW/'paired_replacement_evidence';data=read(folder/'evaluation.json');frozen=read(folder/'RF_selection.json');sensitivity=read(folder/'population_sensitivity.json')
    assert read(folder/'changed_endpoint_audit.json')['all_passed']
    methods=['published_c0_positive','paired_positive','paired_2log2_margin','published_sticky_control'];names=['Published','Both gains >0','Both >2log2','Sticky control']
    fig,axes=plt.subplots(2,2,figsize=(15,10),layout='constrained')
    for k,arm in enumerate(['c0','fitted_c']):
        for j,m in enumerate(methods):
            r=next(r for r in data['summary'] if r['method']==m and r['arm']==arm)
            axes[k,0].bar(j-.16,r['mean_error_km'],width=.3,color='C0',label='Mean' if j==0 else None)
            axes[k,0].bar(j+.16,r['median_error_km'],width=.3,color='C1',label='Median' if j==0 else None)
            if j<2:
                errors=sorted(r['position_error_km'] for r in data['rows'] if r['method']==m and r['arm']==arm)
                axes[k,1].plot(errors,np.arange(1,411)/410,label=names[j])
        axes[k,0].set_xticks(range(4),names,rotation=15);axes[k,0].set(title=arm,ylabel='Position error (km)');axes[k,0].axhline(.5,c='green',ls='--');axes[k,0].legend()
        axes[k,1].set(title=arm,xlabel='Position error (km)',ylabel='Fraction of410 available scans',xlim=(0,5));axes[k,1].legend()
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('Full DS23 · matched saved410-scan decisions · no new candidates, fits or prior changes\nBoth-positive candidate improves2/410 cases; unchanged coverage and0.5km success count. Provisional only')
    save(fig,'full_DS23_paired_guard_summary.png')
    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    offered=[r for r in frozen['rows'] if r['accepted']['published_c0_positive']]
    for ax in axes:
        ax.scatter([r['RF_gains']['c0'] for r in offered],[r['RF_gains']['fitted_c'] for r in offered],s=24,c='C0',label='74 published accepted replacements')
        for r in offered:
            if not r['accepted']['paired_positive']:
                ax.scatter(r['RF_gains']['c0'],r['RF_gains']['fitted_c'],c='crimson',s=65,marker='x');ax.annotate(r['case'].replace('DS23-',''),(r['RF_gains']['c0'],r['RF_gains']['fitted_c']),xytext=(6,5),textcoords='offset points',fontsize=9)
        ax.axhline(0,c='black');ax.axvline(0,c='black');ax.axhline(2*np.log(2),c='gray',ls=':');ax.axvline(2*np.log(2),c='gray',ls=':')
        ax.set(xlabel='c=0 normalized RF evidence gain',ylabel='Fitted-c normalized RF evidence gain');ax.grid(alpha=.2)
    axes[0].set_xscale('symlog',linthresh=1);axes[0].set_yscale('symlog',linthresh=1);axes[0].legend(fontsize=8);axes[1].set(xlim=(0,2),ylim=(-2,2),title='Small evidence gains, enlarged')
    fig.suptitle('Shared candidate and endpoint budget · old minus challenger −2 bound\n0080 and0273 improve c=0 evidence but worsen fitted-c evidence; both-positive rule retains original assignment')
    save(fig,'full_DS23_RF_gain_comparison.png')
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained');boot=[]
    for col,metric in enumerate(['mean','median']):
        for k,arm in enumerate(['c0','fitted_c']):
            rr=[r for r in sensitivity['temporal_bootstrap'] if r['arm']==arm and r['method']=='paired_positive']
            for j,r in enumerate(rr):
                lo,hi=np.asarray(r[metric+'_change95_km'])*1000;y=k*4+j
                axes[col].plot([lo,hi],[y,y],c=f'C{k}',lw=4);axes[col].scatter(hi,y,c=f'C{k}',s=15)
                boot.append(dict(arm=arm,metric=metric,hours=r['hours'],blocks=r['occupied_blocks'],lower_m=lo,upper_m=hi,samples=r['samples']))
        axes[col].axvline(0,c='black');axes[col].set(title=metric+' change',xlabel='New minus published error (m; negative improves)',yticks=[0,1,2,4,5,6],yticklabels=['c0:1h','c0:3h','c0:6h','fit:1h','fit:3h','fit:6h']);axes[col].grid(alpha=.2)
    fig.suptitle('Whole UTC time-block bootstrap ·5000 draws per condition · seed2026102211\nDescriptive after extensive same-site development; intervals reach zero. No new-location/generalization claim')
    save(fig,'full_DS23_temporal_uncertainty.png')
    fig,axes=plt.subplots(2,1,figsize=(17,7),layout='constrained',sharex=True)
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        for j,m in enumerate(methods[:2]):
            rr=sorted([r for r in data['rows'] if r['method']==m and r['arm']==arm],key=lambda r:r['case'])
            ax.plot(range(410),[r['position_error_km'] for r in rr],'.-',ms=2,lw=.6,label=names[j])
        ax.set(ylabel=f'{arm} error (km)');ax.set_yscale('symlog',linthresh=1);ax.legend(fontsize=8);ax.grid(alpha=.2)
    axes[1].set_xticks(range(0,410,20),[rr[j]['case'].replace('DS23-','') for j in range(0,410,20)],rotation=60);axes[1].set_xlabel('DS23 scan; unavailable0012/0184/0286 not imputed')
    fig.suptitle('Full DS23 · all410 available scans ·2 changed endpoints and408 exact fallbacks')
    save(fig,'full_DS23_by_scan.png')
    changes=[]
    for r in data['rows']:
        if r['method'] in methods[1:3] and abs(r['error_change_km'])>1e-8:changes.append(r)
    figures.csv_write(OUT/'tables/full_DS23_positions.csv',data['rows']);figures.csv_write(OUT/'tables/full_DS23_summary.csv',data['summary']);figures.csv_write(OUT/'tables/full_DS23_changed_cases.csv',changes)
    figures.csv_write(OUT/'tables/full_DS23_format_summary.csv',sensitivity['format_summary']);figures.csv_write(OUT/'tables/full_DS23_bootstrap.csv',boot)
    for name in ['protocol.json','RF_selection.json','evaluation.json','changed_endpoint_audit.json','population_sensitivity.json']:
        shutil.copyfile(folder/name,OUT/'evidence'/('paired_guard_'+name))


def archive(cases):
    groups={}
    for p in RAW.rglob('*'):
        if not p.is_file() or p.suffix not in ['.json','.csv','.py']:continue
        name=str(p.relative_to(RAW));m=re.search(r'DS23-\d{4}',name)
        group=m.group()+('_restarts' if '/DBG01/restart_' in name else '_other') if m and m.group() in cases else 'shared'
        groups.setdefault(group,[]).append(p)
    manifest=[]
    for name,paths in groups.items():
        target=OUT/'evidence'/('raw_'+name+'.tar.gz')
        with tarfile.open(target,'w:gz') as a:
            for p in sorted(paths):a.add(p,arcname=str(p.relative_to(RAW)),recursive=False)
        if target.stat().st_size>=45*1024**2:raise ValueError('split large evidence archives')
        manifest.append(dict(file=str(target.relative_to(OUT)),bytes=target.stat().st_size,sha256=sha(target),source_files=len(paths)))
    write(OUT/'evidence/archive_manifest.json',manifest)


def main():
    runner.configure();parents.paths.runner=runner
    for f in ['figures','tables','evidence','source/tools','source/tests']:(OUT/f).mkdir(parents=True,exist_ok=True)
    for module in [figures,diagnostics,path_figures,restarts]:module.RAW=RAW;module.OUT=OUT
    figures.setup=runner.engine.current_setup
    assert read(RAW/'batch_execution.json')['all_passed'];assert read(RAW/'independent_iteration_audit.json')['all_passed']
    assert read(RAW/'temporal_endpoint_audit.json')['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];trials=[];gates=[];families=[];controls=[];residuals=[];following=[];paths=[];rounds=[];ceilings={}
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms']
        for a,s in original['arms'].items():original['arms'][a]=reported_fit(runner.engine.baseline.build(original,a,s['phase_reference']),s)
        default,dcov,dkind,dselected=parents.ORIGINAL_PARENT(case);chosen,ccov,ckind,cselected=parents.selected_parent(case)
        td,tcov,_=temporal_view(case,default,dcov,dkind,'graph_seeded_paths_v2');cd,cdcov,_=temporal_view(case,chosen,ccov,ckind,'same_mask_parent_choice/paths')
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        for label,d,cov,kind in [('Incumbent',original,initial,'default'),('Default graph',default,dcov,dkind),('RF graph parent',chosen,ccov,ckind),('Default temporal policy',td,tcov,dkind),('RF-parent temporal policy',cd,cdcov,ckind)]:
            for arm,r in d['arms'].items():
                saved=reported_fit(parents.paths.build(d,kind,arm,r['phase_reference']),r)
                rows.append(result_row(case,label,arm,saved,cov[arm],initial[arm]))
            for associated in [True,False]:figures.glrt_figure(d,cov['fitted_c'],label.lower().replace(' ','_'),associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));rounds.extend(restarts.restart_figure(case));families.extend(figures.family_rows(case,original))
        residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=chosen['arms'],selected=cselected),None))
        following.extend(diagnostics.track_diagnostics(case,original))
        parents.paths.OUT=RAW/'same_mask_parent_choice/paths';paths.extend(path_figures.path_figures(case,chosen,ckind))
        collections=[('Default graph',read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']),('Support graph',read(RAW/'support_aware_reentry'/(case+'.json'))['trials'])]
        for folder,prefix in [('graph_seeded_paths_v2','Original-parent '),('same_mask_parent_choice/paths','RF-parent ')]:
            collections.extend((prefix+m,[t]) for m,t in read(RAW/folder/(case+'.json'))['methods'].items() if 'arms' in t)
        for label,collection in collections:
            for i,t in enumerate(collection):
                gates.extend(gate_rows(case,label+':'+str(i),t))
                for arm,r in t['arms'].items():trials.append(dict(case=case,method=label,trial=i,arm=arm,paired_valid=t['paired_valid'],accepted=t.get('accepted',t['paired_valid']),new_curved_points=t.get('added_curved_points',0),new_predictive_points=t.get('new_points',0),position_error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],final_phase_change_s=r['final_phase_change_s']))
        if case=='DS23-0163':figures.csv_write(OUT/'tables/curvature_consistency.csv',shapes(original))
    # Reuse the already sealed and independently audited0209 confirmation.
    old=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_010_raw/short_confirmation20_evaluation/evaluation.json'
    reuse=[r for record in read(old)['records'] if record['case']=='DS23-0209' for r in record['rows']]
    figures.csv_write(OUT/'tables/0209_reused_short_curve_result.csv',reuse)
    write(OUT/'evidence/0209_short_reuse.json',dict(source=str(old),source_sha256=sha(old),rows=reuse,no_refit_or_new_point_search=True))
    overview(rows,ceilings);population()
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('all_curved_gates',gates),('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',paths),('restart_phase_rounds',rounds)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,local_prototypes_not_full_DS23_policy=True,no_ALGO_release=True))
    for name in ['protocol.json','batch_execution.json','independent_iteration_audit.json','RF_restart_selection.json','temporal_endpoint_audit.json']:
        shutil.copyfile(RAW/name,OUT/'evidence'/name)
    archive(cases)
    names=['run_ds23_dbg01_iteration_011.py','probe_ds23_iteration011_existing_recovery.py','ds23_exact_native_time_union.py','ds23_graph_seeded_path_recovery.py','repair_ds23_iteration011_path_times.py','probe_ds23_iteration011_parent_choice.py','probe_ds23_paired_replacement_evidence.py','audit_ds23_paired_replacement_evidence.py','analyze_ds23_paired_evidence_population.py','audit_ds23_iteration011_temporal.py',Path(__file__).name]
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    tests=['test_ds23_dbg01_iteration_011.py','test_ds23_iteration011_existing_recovery.py','test_ds23_exact_native_time_union.py','test_ds23_graph_seeded_path_recovery.py','test_ds23_iteration011_path_time_repair.py','test_ds23_paired_replacement_evidence.py','test_ds23_iteration011_parent_choice.py']
    for name in tests:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')})
    gallery()
    print('Iteration011 report assets complete',len(list((OUT/'figures').glob('*.png'))),'figures',flush=True)


if __name__=='__main__':main()
